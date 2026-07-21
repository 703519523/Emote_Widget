from typing import Dict, List, Sequence, TYPE_CHECKING, Optional, Any
from PySide6.QtCore import QObject, QTimer, Slot
from emote_widget.core.plugin_interface import IEmotePlugin
import random
import time
import json
import os
from .noise_utils import EmotionalWalker

if TYPE_CHECKING:
    from emote_widget.core.controller import EmoteController
    import logging

# ==========================================
# 默认配置 (Fallback Configuration)
# ==========================================
DEFAULT_CONFIG = {
    "system": {
        "heartbeat_interval_ms": 100,
        "decision_interval_min_s": 2.0,
        "decision_interval_max_s": 5.0,
        "idle_threshold_s": 30.0
    },
    "emotional_walker": {
        "speed": 0.2,
        "smooth_factor": 0.95,
        "decay_rate": 0.05
    },
    "interaction": {
        "click": {
            "arousal_impulse": 0.8,
            "valence_impulse_positive_min": 0.2,
            "valence_impulse_positive_max": 0.8,
            "valence_impulse_neutral_range": 0.2,
            "positive_prob": 0.7
        },
        "hover": {
            "arousal_boost": 0.05,
            "valence_boost": 0.05
        }
    },
    "body_loops": [
        "待機ループ00", "待機ループ01", "待機ループ02",
        "差分用_waiting_loop", "差分用_waiting_loop2", "差分用_waiting_loop3"
    ],
    "animation_pool": {
        "nod": ["うん", "うんうん", "ok"],
        "shake": ["いやいや", "いやいや2", "首横振り"],
        "happy": ["にっこり", "にっこり2", "笑い"],
        "excited": ["わくわく", "ごきげん", "ぶりっこ"],
        "surprised": ["びっくり1", "びっくり2", "右向き", "左向き"],
        "shy": ["はじらい", "はじらい2"],
        "angry": ["ぷんぷん"],
        "sigh": ["ためいき", "がっかり"],
        "sad": ["うつむき", "悩み", "哀しい00"],
        "tired": ["ひく", "わなわな"],
        "gaze": ["疑問", "戸惑い", "真顔", "じとー"]
    },
    "mapping_thresholds": {
        "arousal_low": -0.4,
        "arousal_high": 0.4,
        "valence_positive": 0.3,
        "valence_negative": -0.3,
        "gaze_min_arousal": -0.2,
        "gaze_min_valence": -0.5
    },
    "probabilities": {
        "layer1_switch_prob": 0.2,
        "layer2_none_prob": 0.5
    }
}

# 动作标签常量 (保持不变，用于代码引用)
TAG_NOD = 'nod'
TAG_SHAKE = 'shake'
TAG_HAPPY = 'happy'
TAG_EXCITED = 'excited'
TAG_SURPRISED = 'surprised'
TAG_SHY = 'shy'
TAG_ANGRY = 'angry'
TAG_SIGH = 'sigh'
TAG_SAD = 'sad'
TAG_TIRED = 'tired'
TAG_GAZE = 'gaze'

# ==========================================
# 核心逻辑 (Behavior Worker)
# ==========================================
class BehaviorWorker(QObject):
    """
    基于情感空间游走的自主行为逻辑。
    """
    
    def __init__(self, plugin: "BehaviorEnginePlugin", config: Dict[str, Any]):
        super().__init__()
        self.plugin = plugin
        self.config = config
        
        # 情感游走器
        self.walker = EmotionalWalker()
        self.current_valence = 0.0 # -1.0 ~ 1.0 (负面 -> 正面)
        self.current_arousal = 0.0 # -1.0 ~ 1.0 (低能 -> 高能)
        
        self.last_interaction_time = time.time()
        self.last_update_time = time.time()
        
        # 状态记忆
        self._current_main_anim: Optional[str] = None
        self._current_layer1_anim: Optional[str] = None
        self._current_layer2_anim: Optional[str] = None
        
        # 心跳计时器
        interval = self.config["system"]["heartbeat_interval_ms"]
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self._on_heartbeat)
        
        # 连接信号
        self.controller.on_character_clicked.connect(self._on_clicked)
        self.controller.on_character_hovered.connect(self._on_hovered)
        
        # 启动心跳
        self.heartbeat_timer.start(interval) 
        self._next_decision_time = time.time() + self.config["system"]["decision_interval_min_s"]

    @property
    def controller(self) -> "EmoteController":
        return self.plugin.controller

    @property
    def logger(self) -> Optional["logging.Logger"]:
        return getattr(self.plugin, 'logger', None)

    def cleanup(self):
        """清理资源"""
        self.heartbeat_timer.stop()
        try:
            self.controller.on_character_clicked.disconnect(self._on_clicked)
            self.controller.on_character_hovered.disconnect(self._on_hovered)
        except Exception:
            pass

    @Slot()
    def _on_heartbeat(self):
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now
        
        # 1. 步进情感空间
        walker_cfg = self.config["emotional_walker"]
        
        # 如果很久没交互，Arousal 会倾向于降低
        idle_threshold = self.config["system"]["idle_threshold_s"]
        decay_rate = walker_cfg["decay_rate"]
        
        idle_duration = now - self.last_interaction_time
        if idle_duration > idle_threshold:
            self.current_arousal -= decay_rate * dt
        
        # 获取噪声增量
        delta_v, delta_a = self.walker.step(dt, speed=walker_cfg["speed"])
        
        # 混合噪声和当前值 (平滑)
        smooth = walker_cfg["smooth_factor"]
        self.current_valence = self.current_valence * smooth + delta_v * (1 - smooth)
        self.current_arousal = self.current_arousal * smooth + delta_a * (1 - smooth)
        
        # 钳制范围
        self.current_valence = max(-1.0, min(1.0, self.current_valence))
        self.current_arousal = max(-1.0, min(1.0, self.current_arousal))
        
        # 2. 决策动作
        if now >= self._next_decision_time:
            self._make_decision()
            # 下次决策时间随机浮动
            min_s = self.config["system"]["decision_interval_min_s"]
            max_s = self.config["system"]["decision_interval_max_s"]
            self._next_decision_time = now + random.uniform(min_s, max_s)

    def _make_decision(self):
        """
        根据当前 (Valence, Arousal) 坐标决定动作。
        """
        v = self.current_valence
        a = self.current_arousal
        
        if self.logger:
            self.logger.debug(f"Decision Tick: V={v:.2f}, A={a:.2f}")

        # 获取配置
        body_loops = self.config["body_loops"]
        anim_pool = self.config["animation_pool"]
        thresholds = self.config["mapping_thresholds"]
        probs = self.config["probabilities"]
        
        # --- 基础层 (Main) ---
        if self._current_main_anim != '平常':
            self.controller.play('平常')
            self._current_main_anim = '平常'
            
        # --- 身体层 (Layer 1) ---
        if random.random() < probs["layer1_switch_prob"]:
            if body_loops:
                target_loop = random.choice(body_loops)
                if target_loop != self._current_layer1_anim:
                    self.controller.set_diff_timeline(1, target_loop)
                    self._current_layer1_anim = target_loop
                
        # --- 表情/动作层 (Layer 2) ---
        target_tags: List[Optional[str]] = []
        
        if a < thresholds["arousal_low"]: # 低唤醒
            target_tags.append(TAG_TIRED)
            target_tags.append(TAG_SIGH)
            if v < thresholds["valence_negative"]: target_tags.append(TAG_SAD)
            
        elif a > thresholds["arousal_high"]: # 高唤醒
            if v > thresholds["valence_positive"]: # 正面
                target_tags.append(TAG_HAPPY)
                target_tags.append(TAG_EXCITED)
            elif v < thresholds["valence_negative"]: # 负面
                target_tags.append(TAG_ANGRY)
                target_tags.append(TAG_SHAKE)
            else: # 中性
                target_tags.append(TAG_SURPRISED)
                
        else: # 中等唤醒
            target_tags.append(TAG_NOD)
            target_tags.append(TAG_GAZE)
            if v > 0.5: target_tags.append(TAG_HAPPY)
            if random.random() < probs["layer2_none_prob"]: target_tags.append(None)
            
        # 执行 Layer 2
        if target_tags:
            chosen_tag = random.choice(target_tags)
            if chosen_tag is None:
                if self._current_layer2_anim is not None:
                    self.controller.set_diff_timeline(2, "")
                    self._current_layer2_anim = None
            else:
                candidates = anim_pool.get(chosen_tag, [])
                if candidates:
                    anim = random.choice(candidates)
                    self.controller.set_diff_timeline(2, anim)
                    self._current_layer2_anim = anim
                    
                    if self.logger:
                        self.logger.debug(f"Action: {chosen_tag} ({anim}) [V={v:.2f}, A={a:.2f}]")
                        
        # 视线控制联动
        should_gaze = (a > thresholds["gaze_min_arousal"] and v > thresholds["gaze_min_valence"])
        self.controller.enable_gaze_control(should_gaze)


    @Slot()
    def _on_clicked(self):
        """点击产生激烈的冲量"""
        self.last_interaction_time = time.time()
        
        cfg = self.config["interaction"]["click"]
        
        # 瞬间提升唤醒度
        self.current_arousal += cfg["arousal_impulse"]
        
        # 情绪效价随机变化
        if random.random() < cfg["positive_prob"]:
            impulse_v = random.uniform(cfg["valence_impulse_positive_min"], cfg["valence_impulse_positive_max"])
        else:
            rng = cfg["valence_impulse_neutral_range"]
            impulse_v = random.uniform(-rng, rng)
            
        self.current_valence += impulse_v
        
        # 立即触发决策
        self._make_decision()
        
        if self.logger:
            self.logger.debug("Interaction: Clicked (Impulse Added)")

    @Slot()
    def _on_hovered(self):
        """悬停产生温和的冲量"""
        self.last_interaction_time = time.time()
        cfg = self.config["interaction"]["hover"]
        
        self.current_arousal += cfg["arousal_boost"]
        self.current_valence += cfg["valence_boost"]
        
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
        self.worker: Optional[BehaviorWorker] = None
        self.config = DEFAULT_CONFIG

    def get_name(self) -> str:
        return "behavior_engine"

    def get_description(self) -> str:
        return "基于柏林噪声和情感空间的自主行为引擎。"

    def initialize(self):
        # 注意: 基类 IEmotePlugin.initialize 是无参的 abstractmethod
        # self.controller 属性已经在调用此方法前由 EmoteController 注入
        
        # 尝试加载配置文件
        try:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                    # 简单合并 (Deep merge is better but simple update works for top-level keys if structure matches)
                    # 这里为了安全，我们假设用户配置是完整的，或者只覆盖顶层
                    # 更好的做法是递归合并，这里简化处理，直接用 DEFAULT 作为底板
                    # TODO: Implement recursive merge if needed
                    self.config = user_config
                if hasattr(self, 'logger'):
                    self.logger.info(f"已加载配置文件: {config_path}")
            else:
                if hasattr(self, 'logger'):
                    self.logger.warning("未找到 config.json，使用默认配置。")
        except Exception as e:
            if hasattr(self, 'logger'):
                self.logger.error(f"加载配置文件失败: {e}，将使用默认配置。")

        # 实例化 Worker 并保留引用
        self.worker = BehaviorWorker(self, self.config)
        
        if hasattr(self, 'logger'):
            self.logger.info("Behavior Engine Plugin initialized (Noise Driven Mode).")

    def cleanup(self):
        if self.worker:
            self.worker.cleanup()
            self.worker = None
        if hasattr(self, 'logger'):
            self.logger.info("Behavior Engine Plugin cleaned up.")
