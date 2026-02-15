from typing import Dict, Sequence, TYPE_CHECKING, Optional
from PySide6.QtCore import QObject, QTimer, Slot
from emote_widget.core.plugin_interface import IEmotePlugin
import random
import time
from enum import Enum, auto

if TYPE_CHECKING:
    from emote_widget.core.controller import EmoteController
    import logging

# ==========================================
# 1. 状态定义 (State Definitions)
# ==========================================
class State(Enum):
    IDLE = auto()       # 待机
    MICRO_MOVE = auto() # 微动作
    GAZE = auto()       # 注视/跟随
    EMOTION = auto()    # 情感表达
    TIRED = auto()      # 疲劳

# ==========================================
# 2. 配置数据 (Configuration)
# ==========================================

BASE_TRANSITION_MATRIX = {
    State.IDLE:       {State.IDLE: 80, State.MICRO_MOVE: 10, State.GAZE: 5, State.EMOTION: 5, State.TIRED: 0},
    State.MICRO_MOVE: {State.IDLE: 60, State.MICRO_MOVE: 20, State.GAZE: 10, State.EMOTION: 5, State.TIRED: 5},
    State.GAZE:       {State.IDLE: 50, State.MICRO_MOVE: 10, State.GAZE: 30, State.EMOTION: 10, State.TIRED: 0},
    State.EMOTION:    {State.IDLE: 70, State.MICRO_MOVE: 10, State.GAZE: 10, State.EMOTION: 10, State.TIRED: 0},
    State.TIRED:      {State.IDLE: 40, State.MICRO_MOVE: 0,  State.GAZE: 0,  State.EMOTION: 0,  State.TIRED: 60},
}

# -----------------------------------------------------------------------------
# 分层动画配置 (Layered Animation Configuration)
# -----------------------------------------------------------------------------
# Layer 0 (Main): 基础状态 (Base)
# Layer 1 (Diff Slot 1): 身体循环 (Body Loop) - 持续动作
# Layer 2 (Diff Slot 2): 表情/微动作 (Face/Action) - 短暂动作

# 身体循环列表 (用于 IDLE 和大多数状态的底层律动)
BODY_LOOPS = [
    '待機ループ00', '待機ループ01', '待機ループ02',
    '差分用_waiting_loop', '差分用_waiting_loop2', '差分用_waiting_loop3'
]

# 状态分层配置
# 每个状态定义其在各个层级上的候选动画列表
# 使用 Sequence[Optional[str]] 以允许 list[str] (协变)
STATE_LAYERS_CONFIG: Dict[State, Dict[str, Sequence[Optional[str]]]] = {
    State.IDLE: {
        "main": ['平常'],
        "layer1": BODY_LOOPS,  # 保持身体律动
        "layer2": [None]       # 清空表情层
    },
    State.MICRO_MOVE: {
        "main": ['平常'],
        "layer1": BODY_LOOPS,  # 保持身体律动
        "layer2": [
            'うん', 'うんうん', 'ok',           # 点头/肯定
            'いやいや', 'いやいや2',             # 摇头/否定
            '首横振り', '耳動かす',             # 原始微动作
            '右向き', '左向き', '仰ぎ',         # 头部动作
            'sample_00', 'sample_01'            # 其他微动
        ]
    },
    State.GAZE: {
        "main": ['平常'],
        "layer1": BODY_LOOPS,
        "layer2": ['疑問', '戸惑い', '真顔', 'じとー'] # 配合眼神跟随的表情
    },
    State.EMOTION: {
        "main": ['平常'],
        "layer1": BODY_LOOPS,
        "layer2": [
            'にっこり', 'にっこり2', '笑い',    # 开心
            'わくわく', 'ごきげん', 'ぶりっこ',  # 兴奋/可爱
            'びっくり1', 'びっくり2',           # 惊讶
            'はじらい', 'はじらい2',            # 害羞
            'ぷんぷん',                        # 生气
        ]
    },
    State.TIRED: {
        "main": ['平常'],
        "layer1": BODY_LOOPS,
        "layer2": [
            'ためいき', 'がっかり',             # 叹气
            'うつむき', '悩み',                 # 低头
            'ひく', 'わなわな',                 # 负面
            '哀しい00'                         # 原始负面
        ]
    }
}

DIALOG_LINES = {
    State.IDLE: ["发呆中...", "今天天气真好", "嗯...", "（放空）"],
    State.MICRO_MOVE: ["动动脖子", "伸个懒腰", "活动一下"],
    State.GAZE: ["你在看我吗？", "盯——", "怎么了？", "嗯？"],
    State.EMOTION: ["嘿嘿", "好开心！", "啦啦啦~", "心情不错"],
    State.TIRED: ["好累啊...", "想睡觉了", "哈欠...", "Zzz..."],
}

# ==========================================
# 3. 工作线程 (Worker)
# ==========================================
class BehaviorWorker(QObject):
    """
    负责处理 Qt 信号和定时器的 Worker 类。
    """
    
    def __init__(self, controller: "EmoteController", logger: Optional["logging.Logger"]):
        super().__init__()
        self.controller = controller
        self.logger = logger
        
        self.current_state = State.IDLE
        self.last_interaction_time = time.time()
        self.last_hover_time = 0.0
        
        # 记录当前播放的动画，避免重复播放
        self._current_main_anim: Optional[str] = None
        self._current_layer1_anim: Optional[str] = None
        self._current_layer2_anim: Optional[str] = None
        
        # 心跳计时器
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setSingleShot(True)
        self.heartbeat_timer.timeout.connect(self._on_heartbeat)
        
        # 连接信号
        self.controller.on_character_clicked.connect(self._on_clicked)
        self.controller.on_character_hovered.connect(self._on_hovered)
        
        # 启动
        self._schedule_next_heartbeat()

    def cleanup(self):
        """清理资源"""
        self.heartbeat_timer.stop()
        try:
            self.controller.on_character_clicked.disconnect(self._on_clicked)
            self.controller.on_character_hovered.disconnect(self._on_hovered)
        except Exception:
            pass

    def _schedule_next_heartbeat(self):
        interval = random.randint(2000, 5000)
        self.heartbeat_timer.start(interval)

    @Slot()
    def _on_heartbeat(self):
        next_state = self._decide_next_state()
        self._transition_to(next_state)
        self._schedule_next_heartbeat()

    def _decide_next_state(self) -> State:
        base_weights = BASE_TRANSITION_MATRIX.get(self.current_state, BASE_TRANSITION_MATRIX[State.IDLE])
        weights = base_weights.copy()
        
        now = time.time()
        
        if now - self.last_interaction_time > 30:
            weights[State.TIRED] = weights.get(State.TIRED, 0) + 100
            
        if now - self.last_hover_time < 2.0:
            weights[State.GAZE] = weights.get(State.GAZE, 0) + 200
            
        states = list(weights.keys())
        weight_values = list(weights.values())
        
        try:
            return random.choices(states, weights=weight_values, k=1)[0]
        except (IndexError, ValueError):
            return State.IDLE

    def _transition_to(self, new_state: State):
        prev_state = self.current_state
        self.current_state = new_state
        
        if self.logger:
            self.logger.debug(f"State Transition: {prev_state.name} -> {new_state.name}")
        
        # Gaze Control Logic
        if prev_state == State.GAZE and new_state != State.GAZE:
            self.controller.enable_gaze_control(False)
        elif new_state == State.GAZE:
            self.controller.enable_gaze_control(True)
            
        # Execute Layered Animation
        self._execute_layered_animation(new_state)
        
        # Dialog Logic
        if random.random() < 0.2:
            self._try_show_dialog(new_state)

    def _execute_layered_animation(self, state: State):
        """
        根据状态配置，分层播放动画。
        智能跳过未变化的层级，实现平滑过渡。
        """
        config = STATE_LAYERS_CONFIG.get(state)
        if not config:
            return

        # 1. Main Layer (Layer 0)
        main_candidates = config.get("main", [])
        if main_candidates:
            # Filter out None from main candidates as play doesn't accept None
            valid_main = [m for m in main_candidates if m is not None]
            if valid_main:
                target_main = random.choice(valid_main)
                if target_main != self._current_main_anim:
                    self.controller.play(target_main)
                    self._current_main_anim = target_main
                    if self.logger: self.logger.debug(f"  [Main] -> {target_main}")
        
        # 2. Body Loop Layer (Layer 1 - Slot 1)
        # 策略：如果目标包含当前正在播放的 loop，则大概率保持不变，实现无缝衔接
        # 除非是 IDLE 状态下为了丰富性而随机切换
        layer1_candidates = config.get("layer1", [])
        target_layer1 = None
        
        if layer1_candidates:
            # 基础切换概率 5%
            switch_prob = 0.05
            
            # 如果是 IDLE 状态，大幅提高身体律动的切换概率 (例如 30%)
            # 让角色在发呆时也会偶尔换个站姿，显得更生动
            if state == State.IDLE:
                switch_prob = 0.3
            
            force_change = (random.random() < switch_prob)
            
            # Remove None from candidates for comparison
            valid_candidates = [c for c in layer1_candidates if c is not None]
            
            if self._current_layer1_anim in valid_candidates and not force_change:
                target_layer1 = self._current_layer1_anim # Keep current
            elif valid_candidates:
                target_layer1 = random.choice(valid_candidates)
        else:
            target_layer1 = None # Clear

        if target_layer1 != self._current_layer1_anim:
            if target_layer1:
                self.controller.set_diff_timeline(1, target_layer1)
            else:
                self.controller.set_diff_timeline(1, "") # Clear
            self._current_layer1_anim = target_layer1
            if self.logger: self.logger.debug(f"  [Layer1] -> {target_layer1}")

        # 3. Face/Action Layer (Layer 2 - Slot 2)
        # 策略：表情层通常是瞬态的，每次都重新触发
        layer2_candidates = config.get("layer2", [])
        target_layer2 = None
        
        if layer2_candidates:
            target_layer2 = random.choice(layer2_candidates)
        
        # 即使是 None 也要执行，意味着清空表情
        if target_layer2 != self._current_layer2_anim or target_layer2 is not None:
             if target_layer2:
                 self.controller.set_diff_timeline(2, target_layer2)
             else:
                 # 只有当之前有表情时才清空，避免频繁调用清空
                 if self._current_layer2_anim is not None:
                     self.controller.set_diff_timeline(2, "")
             
             self._current_layer2_anim = target_layer2
             if self.logger: self.logger.debug(f"  [Layer2] -> {target_layer2}")


    def _try_show_dialog(self, state: State):
        lines = DIALOG_LINES.get(state, [])
        if lines:
            text = random.choice(lines)
            self.controller.show_dialog(text)

    @Slot()
    def _on_clicked(self):
        self.last_interaction_time = time.time()
        if self.logger:
            self.logger.debug("Interaction: Clicked")
            
        # 点击交互逻辑：
        # 1. 立即打断当前状态，强制进入互动状态
        # 2. 70% 概率开心 (EMOTION)，30% 概率微动作 (MICRO_MOVE)
        # 3. 如果当前已经是 EMOTION，则尝试切换到不同的 EMOTION 动作
        
        target_state = State.EMOTION if random.random() < 0.7 else State.MICRO_MOVE
        
        # 强制重置心跳计时器，立即执行一次决策
        self.heartbeat_timer.stop()
        
        # 直接执行状态转移，跳过 _decide_next_state 的常规逻辑
        self.current_state = target_state
        self._transition_to(target_state)
        
        # 重新启动心跳（延迟一点，给互动动画留出时间）
        interval = random.randint(3000, 6000)
        self.heartbeat_timer.start(interval)

    @Slot()
    def _on_hovered(self):
        self.last_interaction_time = time.time()
        self.last_hover_time = time.time()
        if self.logger:
            self.logger.debug("Interaction: Hovered")


# ==========================================
# 4. 插件入口 (Plugin Entry)
# ==========================================
class BehaviorEnginePlugin(IEmotePlugin):
    """
    自主行为引擎插件入口。
    """

    def __init__(self) -> None:
        super().__init__()
        self.worker = None

    def get_name(self) -> str:
        return "behavior_engine"

    def get_description(self) -> str:
        return "基于马尔可夫链的分层自主行为引擎。"

    def initialize(self, widget: "EmoteController"):
        super().initialize(widget)
        
        # 实例化 Worker 并保留引用
        self.worker = BehaviorWorker(self.widget, getattr(self, 'logger', None))
        
        if hasattr(self, 'logger'):
            self.logger.info("Behavior Engine Plugin initialized (Layered Animation Mode).")

    def cleanup(self):
        if self.worker:
            self.worker.cleanup()
            self.worker = None
            
        if hasattr(self, 'logger'):
            self.logger.info("Behavior Engine Plugin cleaned up.")
