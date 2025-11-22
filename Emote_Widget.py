
#版本号这一块
__version__ = "0.0.1-A"

import os
import json
import time
import queue
import logging
import threading
import collections
import numpy as np
import soundfile as sf
import sounddevice as sd
from PySide6.QtCore import Qt, QObject, Slot, Signal, QUrl, QThread, QPointF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QPolygonF
from PySide6.QtWidgets import QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel

import importlib
import pkgutil
from plugins.plugin_interface import IEmotePlugin

import BoundParams
from BoundParams import SpecialUsage
from logger_config import emote_widget_logger as logger


DEFAULT_CONFIG = {
    "animation": {
        "initialization_name": "初期化",
        "reset_duration_ms": 300,
    },
    "lip_sync": {
        "update_fps": 30,
        "mean_decay_time_s": 0.8,
        "peak_decay_time_s": 0.15,
        "activation_ratio": 0.3,
        "mouth_ratio_curve": 0.35,
        "mouth_ratio_oversaturation": 1.1,
        "close_mouth_duration_ms": 200,
        "set_variable_duration_ms": 5,
    },
    "file_streaming": {
        "blocksize_hz": 30,
    }
}

# ------------------------------------------------------------------------------
#  插件系统
# ------------------------------------------------------------------------------

class PluginAccessor:
    """
    一个灵活的访问器类，允许使用属性风格访问已注册的插件。
    例如: widget.plugins.tts.speak()
    """
    def __init__(self, widget):
        self._plugins = {}
        self._widget = widget

    def register(self, plugin: IEmotePlugin):
        """注册一个插件实例。"""
        name = plugin.get_name()
        if not name.isidentifier():
            logger.error(f"插件错误: 插件名称 '{name}' 不是一个有效的Python标识符，已跳过。")
            return
        if name in self._plugins:
            logger.warning(f"插件警告: 名为 '{name}' 的插件已被注册，旧插件将被覆盖。")
        
        self._plugins[name] = plugin
        plugin.initialize(self._widget)

    def get(self, name: str) -> IEmotePlugin | None:
        """通过名称获取插件实例。"""
        return self._plugins.get(name)

    def __getattr__(self, name: str) -> IEmotePlugin:
        """
        实现属性风格访问的魔法方法。
        当访问 widget.plugins.tts 时，此方法会被调用。
        """
        plugin = self.get(name)
        if plugin is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'. No plugin with this name is registered.")
        return plugin
    
    def get_all(self):
        """返回所有已加载的插件实例。"""
        return self._plugins.values()
    
class PluginLoaderWorker(QObject):
    """
    一个专用的 Worker 对象，其代码将在后台线程中执行。
    它只通过信号与主线程通信，完全解耦。
    """
    # 信号1: 报告插件加载进度
    progress_updated = Signal(float, str)
    # 信号2: 报告单条日志/错误
    log_message = Signal(str, bool)
    # 信号3: 所有插件实例化完成，并携带实例列表
    finished = Signal(list)

    def __init__(self):
        super().__init__()
        self._modules_to_load = []

    def scan_for_plugin_modules(self):
        """快速扫描插件，这个方法在主线程中被调用。"""
        import plugins
        logger.info("开始扫描插件目录...")
        for _, module_name, is_pkg in pkgutil.walk_packages(path=plugins.__path__, prefix=plugins.__name__ + '.'):
            if not module_name.endswith('.plugin_interface') and not is_pkg:
                self._modules_to_load.append(module_name)

    @Slot()
    def run_loading(self):
        """
        这是将在后台线程中执行的核心加载逻辑。
        """
        logger.info("后台 Worker 开始执行插件实例化...")
        total_plugins = len(self._modules_to_load)
        successfully_instantiated_plugins = []

        if total_plugins == 0:
            self.log_message.emit("在 'plugins' 目录中未发现任何插件。", False)
            self.finished.emit(successfully_instantiated_plugins)
            return
            
        for i, module_name in enumerate(self._modules_to_load):
            progress = (i + 1) / total_plugins
            self.progress_updated.emit(progress, f"正在实例化: {module_name}")

            try:

                module = importlib.import_module(module_name)
                found = False
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if isinstance(item, type) and issubclass(item, IEmotePlugin) and item is not IEmotePlugin:
                        plugin_instance = item()
                        successfully_instantiated_plugins.append(plugin_instance)
                        self.log_message.emit(f"✓ 成功实例化插件: {plugin_instance.get_name()}", False)
                        found = True
                if not found: raise RuntimeError("模块中未找到 IEmotePlugin 实现。")
            except Exception as e:
                msg = f"✗ 插件 '{module_name}' 实例化失败: {e}"
                self.log_message.emit(msg, True)
                logger.error(msg, exc_info=True)
                
        self.finished.emit(successfully_instantiated_plugins)
        logger.info("后台 Worker 完成插件实例化。")


# ------------------------------------------------------------------------------
#  内部通信桥梁
# ------------------------------------------------------------------------------
class _PythonApiBridge(QObject):
    """一个私有类，作为从 JavaScript 到 Python 的通信桥梁。"""
    # 当 JS 调用 on_player_ready 时，它会携带动画列表并被发射
    player_ready_signal = Signal(list)

    def __init__(self,widget):
        super().__init__()
        self.widget=widget

    @Slot(list)
    def on_player_ready(self, timelines):
        """这个 @Slot 装饰器使该方法可以被 JavaScript 调用。"""
        logger.debug(f"--> _PythonApiBridge.on_player_ready Slot CALLED by JS. Timelines count: {len(timelines)}")
        self.player_ready_signal.emit(timelines)
        
    @Slot()
    def js_on_character_click(self):
        """当 JS 检测到 canvas 被点击时调用此函数。"""
        if self.widget:
            self.widget.on_character_clicked.emit()

    @Slot()
    def js_on_character_hover(self):
        """当 JS 检测到 canvas 被长悬停时调用此函数。"""
        if self.widget:
            self.widget.on_character_hovered.emit()

    @Slot(str, str)
    def on_js_error(self, message, stack):
        """接收来自 JavaScript 的错误并记录。"""
        logger.error(f"[JavaScript Error]\n  Message: {message}\n  Stack: {stack}")

# ------------------------------------------------------------------------------
# 口型同步处理线程
# ------------------------------------------------------------------------------
class StreamLipSyncThread(QThread):
    """
    (双EMA衰减版) 使用两个指数移动平均来追踪音频的基线和峰值，
    实现高度自适应的口型同步。
    """
    mouth_open_ratio_updated = Signal(float)

    debug_data_updated = Signal(dict)

    def __init__(self, audio_queue: queue.Queue, 
                 mean_decay_time=0.8,   # 基线平均值衰减到约36%所需的时间(秒)
                 peak_decay_time=0.15,  # 峰值平均值衰减到约36%所需的时间(秒)
                 update_fps=30,
                 activation_ratio=0.3):
        super().__init__()
        self.audio_queue = audio_queue
        self.is_running = False

        if update_fps <= 0: update_fps = 1

        # 根据衰减时间计算出每帧的平滑因子 (alpha)
        # alpha = exp(-delta_time / decay_time)
        self.mean_smoothing = np.exp(-1 / (mean_decay_time * update_fps))
        self.peak_smoothing = np.exp(-1 / (peak_decay_time * update_fps))
        
        # EMA状态变量
        self.mean_rms = 0.0
        self.peak_rms = 0.0

        # 激活阈值：当前音量需要在基线和峰值之间达到什么比例才算有效声音
        self.activation_ratio = activation_ratio

    def run(self):
        self.is_running = True
        logger.info(f"StreamLipSync (EMA Decay): 线程启动，正在等待音频流...")
        while self.is_running:
            try:
                audio_chunk = self.audio_queue.get(timeout=1)
                if audio_chunk is None: break

                current_rms = np.sqrt(np.mean(audio_chunk**2))

                # 双EMA衰减
                # 1. 更新慢速EMA (基线)，它总是趋向于当前音量
                self.mean_rms = self.mean_rms * self.mean_smoothing + current_rms * (1 - self.mean_smoothing)
                
                # 2. 更新快速EMA (峰值)
                #    如果当前音量大于峰值，峰值立刻跳到当前音量
                #    否则，峰值按自己的速率衰减
                self.peak_rms = max(current_rms, self.peak_rms * self.peak_smoothing)

                # 3. 计算动态范围和激活阈值
                dynamic_range = self.peak_rms - self.mean_rms
                activation_threshold = self.mean_rms + self.activation_ratio * dynamic_range
                
                mouth_open_ratio = 0.0
                if current_rms > activation_threshold and dynamic_range > 0.001: # 避免在静音时抖动
                    # 计算开合度：当前音量在 (阈值 ~ 峰值) 这个区间中所占的比例
                    effective_range = self.peak_rms - activation_threshold
                    mouth_open_ratio = (current_rms - activation_threshold) / (effective_range + 1e-6)
                    mouth_open_ratio = max(0.0, min(mouth_open_ratio, 1.0))
                
                logger.debug(
                    f"LIP_SYNC_DEBUG -- "
                    f"RMS: {current_rms:.4f} | "
                    f"Mean(floor): {self.mean_rms:.4f} | "
                    f"Peak(ceil): {self.peak_rms:.4f} | "
                    f"Threshold: {activation_threshold:.4f} | "
                    f"==> Ratio: {mouth_open_ratio:.2f}"
                )
                self.debug_data_updated.emit({
                    "rms": current_rms,
                    "mean": self.mean_rms,
                    "peak": self.peak_rms,
                    "threshold": activation_threshold
                })
                
                self.mouth_open_ratio_updated.emit(mouth_open_ratio)

            except queue.Empty:
                # 如果超时，让峰值继续自然衰减
                self.peak_rms *= self.peak_smoothing
                self.mouth_open_ratio_updated.emit(0.0)
                self.debug_data_updated.emit({
                    "rms": 0.0, "mean": self.mean_rms,
                    "peak": self.peak_rms, "threshold": self.mean_rms
                })
                continue
            except Exception as e:
                logger.error(f"StreamLipSync (EMA Decay): 处理音频块时出错: ", exc_info=True)
        
        logger.info("StreamLipSync (EMA Decay): 线程已停止。")

    def stop(self):
        self.is_running = False
        while not self.audio_queue.empty():
            try: self.audio_queue.get_nowait()
            except queue.Empty: break
        self.audio_queue.put(None)


# ------------------------------------------------------------------------------
#  一个音频监视器
# ------------------------------------------------------------------------------
class LipSyncMonitorWidget(QWidget):
    """一个用于实时可视化口型同步调试数据的自定义控件。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.history_len = 200
        self.rms_history = collections.deque(maxlen=self.history_len)
        self.threshold_history = collections.deque(maxlen=self.history_len)
        self.current_peak = 0.0
        self.current_mean = 0.0
        self.max_val_seen = 0.1
        self.bg_color = QColor("#1E1E1E")
        self.mean_color = QColor("#4A90E2")
        self.peak_color = QColor("#F5A623")
        self.rms_color = QColor("#7ED321")
        self.threshold_color = QColor("#D0021B")
        self.text_color = QColor("#DDDDDD")
        self.grid_color = QColor("#444444")
        self.font = QFont("Arial", 10)
    @Slot(dict)
    def update_data(self, data: dict):
        rms = data.get("rms", 0.0)
        mean = data.get("mean", 0.0)
        peak = data.get("peak", 0.0)
        threshold = data.get("threshold", 0.0)
        self.rms_history.append(rms)
        self.threshold_history.append(threshold)
        self.current_mean = mean
        self.current_peak = peak
        self.max_val_seen = max(self.max_val_seen, peak, rms) * 0.995
        self.update()
    def paintEvent(self, event):
        """在这里执行所有自定义绘制。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.bg_color)
        
        w, h = self.width(), self.height()
        padding = 10
        label_area_height = 20
        chart_height = h - padding - label_area_height
        if chart_height <= 0:
            painter.end()
            return

        y_scale = chart_height / (self.max_val_seen + 1e-6)

        painter.setPen(self.grid_color)
        for i in range(1, 4):
            y = padding + chart_height * (i / 4.0)
            painter.drawLine(padding, y, w - padding, y)
        
        chart_y_origin = padding + chart_height

        bar_width = 30
        mean_h = self.current_mean * y_scale
        peak_h = self.current_peak * y_scale
        
        painter.fillRect(padding + 10, int(chart_y_origin - mean_h), bar_width, int(mean_h), self.mean_color)
        painter.fillRect(padding + 50, int(chart_y_origin - peak_h), bar_width, int(peak_h), self.peak_color)

        if not self.rms_history:
            painter.end()
            return
        painter.setPen(QPen(self.rms_color, 2))
        rms_points = QPolygonF()
        for i, val in enumerate(self.rms_history):
            x = padding + (w - 2*padding) * (i / (self.history_len - 1))
            y = chart_y_origin - val * y_scale
            rms_points.append(QPointF(x, y))
        painter.drawPolyline(rms_points)
        
        painter.setPen(QPen(self.threshold_color, 2, Qt.DashLine))
        threshold_points = QPolygonF()
        for i, val in enumerate(self.threshold_history):
            x = padding + (w - 2*padding) * (i / (self.history_len - 1))
            y = chart_y_origin - val * y_scale
            threshold_points.append(QPointF(x, y))
        painter.drawPolyline(threshold_points)
        painter.setFont(self.font)
        painter.setPen(self.text_color)
        painter.drawText(padding + 10, h - 5, f"Mean: {self.current_mean:.3f}")
        painter.drawText(padding + 90, h - 5, f"Peak: {self.current_peak:.3f}")
        legend_y = padding + 10
        rms_text = f"RMS: {self.rms_history[-1]:.3f}"
        threshold_text = f"Threshold: {self.threshold_history[-1]:.3f}"
        
        painter.setBrush(self.rms_color); painter.drawRect(w - 120, legend_y - 10, 10, 10)
        painter.drawText(w - 105, legend_y, rms_text)
        painter.setBrush(self.threshold_color); painter.drawRect(w - 120, legend_y + 15, 10, 10)
        painter.drawText(w - 105, legend_y + 20, threshold_text)

        painter.end()

# ------------------------------------------------------------------------------
#  EmoteWidget 主类 (SDK Widget)
# ------------------------------------------------------------------------------
class EmoteWidget(QWebEngineView):
    """
    FreeMote 动态角色显示组件 (EmoteWidget)

    这是一个功能完备、开箱即用的 PySide6 组件，用于加载和控制 FreeMote 
    (E-mote) 模型。它封装了所有与底层网页和 JavaScript 的复杂交互，
    为 Python 开发者提供了一套纯粹、面向对象且文档齐全的 API。

    核心功能:
    - 加载和动态更换模型。
    - 控制模型的变换（位置、缩放、旋转），并支持平滑过渡。
    - 播放主动画和差分动画（如表情）。
    - 调整模型外观（透明度、灰度、染色）和物理效果（风、摆动）。
    - 查询模型内部信息（可用的动画、变量、标记点等）。
    - 开启或关闭实时的鼠标拖动和滚轮缩放交互。

    使用方法:
    1. 在您的 UI 中实例化 EmoteWidget: `self.emote_view = EmoteWidget()`
    2. 连接信号以响应事件: `self.emote_view.load_finished.connect(self.on_page_loaded)`
    3. 在页面加载完成后，调用 `load_model` 来显示角色。
    4. 之后，便可直接调用实例上的各种方法来控制模型，例如: `self.emote_view.set_scale(0.5)`
    """
    
    player_ready = Signal(list)
    """
    当一个模型成功加载并准备好接收指令时，会发射此信号。
    
    携带参数:
        list[str]: 该模型所有可用的主时间轴动画的名称列表。
    """

    load_finished = Signal()
    """当内部的 HTML 页面完全加载并准备好加载模型时，会发射此信号。"""

    plugins_load_finished = Signal()
    """当/plugin目录下所有插件加载完毕，会发射此信号。"""

    on_character_clicked = Signal()
    """当用户点击角色时发射此信号。"""

    on_character_hovered = Signal()
    """当用户在角色上悬停超过1秒时发射此信号。"""

    @property
    def _controller(self):
        """
        一个智能代理属性，用于与内部控制器交互。
        如果控制器已就绪，它会直接返回控制器实例，允许立即执行方法。
        如果控制器未就绪，它会返回一个“指令记录器”，将所有方法调用
        暂存到队列中，以便稍后执行。
        """
        if self._instance_controller:
            return self._instance_controller
        
        class CommandRecorder:
            def __init__(self, queue):
                self.queue = queue

            def __getattr__(self, name):
                def record_command(*args, **kwargs):
                    self.queue.append((name, args, kwargs))
                    logger.debug(f"控制器未就绪，指令 '{name}' 已被缓存。")
                return record_command

        return CommandRecorder(self._command_queue)

    def __init__(self, parent: QWidget = None, config_override: dict = None):
        """初始化 EmoteWidget 组件。"""

        super().__init__(parent)
        logger.debug("EmoteWidget.__init__: super().__init__() 已调用。")

        self.config = json.loads(json.dumps(DEFAULT_CONFIG))
        # 如果用户提供了覆盖配置，则进行合并
        if config_override:
            for key, value in config_override.items():
                if key in self.config and isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value

        self._instance_controller = None  # FreeMoteController
        self._command_queue = []          # 指令队列

        # 插件系统
        self.plugins=PluginAccessor(self)
        self._plugin_loader_thread = QThread(self)
        self._plugin_loader_worker = PluginLoaderWorker()
        self._plugin_loader_worker.moveToThread(self._plugin_loader_thread)
        self._plugin_loader_worker.progress_updated.connect(self._update_splash_plugin_progress)
        self._plugin_loader_worker.log_message.connect(self._add_splash_log)
        self._plugin_loader_worker.finished.connect(self._on_plugins_load_finished)
        self._plugin_loader_thread.started.connect(self._plugin_loader_worker.run_loading)

        self._splash_start_time = 0

        # 启动加载
        self._is_splash_dismissed = False
        self._plugins_are_ready = False
        self._player_is_ready = False

        # 音频同步
        self._lip_sync_thread = None
        self._last_mouth_ratio = 0.0
        self._streamer_stop_event = threading.Event()

        self._monitor_widget = LipSyncMonitorWidget()
        self._monitor_widget.setWindowTitle("音频同步监视器")
        self._monitor_widget.setVisible(False)


        self.current_model_filename = None # 当前加载的模型文件名

        """
        self.variable_map = {
            # 位移与旋转
            "move_lr": "move_LR",
            "move_ud": "move_UD",
            "head_lr": "head_LR",
            "head_ud": "head_UD",
            "head_slant": "head_slant",
            "body_lr": "body_LR",
            "body_ud": "body_UD",
            "body_slant": "body_slant",

            # 眼睛
            "eye_lr": "face_eye_LR",
            "eye_ud": "face_eye_UD",
            "eye_open": "face_eye_open",
            "eye_special": "face_eye_sp",
            "pupil_special": "face_hitomi_sp",

            # 眉毛
            "eyebrow_shape": "face_eyebrow",
            "eyebrow_special": "face_eyebrow_sp",

            # 嘴部
            "mouth_shape": "face_mouth",
            "mouth_special": "face_mouth_sp",
            "mouth_talk": "face_talk",

            # 表情配件
            "tears": "face_tears",
            "cheek_blush": "face_cheek",
            "action_special": "act_sp",

            # 胸部物理
            "bust_lr": "bust_LR",
            "bust_ud": "bust_UD",
            "bust_lr_spare": "bust_LR_spare",
            "bust_ud_spare": "bust_UD_spare",

            # 头发物理
            "hair_front_lr": "hair_LR_front",
            "hair_front_middle_lr": "hair_LR_M_front",
            "hair_front_ud": "hair_UD_front",
            "hair_sidel_lr": "hair_LR_sideL",
            "hair_sidel_middle_lr": "hair_LR_M_sideL",
            "hair_sidel_ud": "hair_UD_sideL",
            "hair_sider_lr": "hair_LR_sideR",
            "hair_sider_middle_lr": "hair_LR_M_sideR",
            "hair_sider_ud": "hair_UD_sideR",
            "hair_back_lr": "hair_LR",
            "hair_back_middle_lr": "hair_LR_M",
            "hair_back_ud": "hair_UD",

            # 其他物理部件
            "quake_lr": "quake_LR",
            "quake_middle_lr": "quake_LR_M",
            "quake_ud": "quake_UD",
            "quake_lr_spare": "quake_LR_spare",
            "quake_middle_lr_spare": "quake_LR_M_spare",
            "quake_ud_spare": "quake_UD_spare",

            # 部件显隐控制
            "part_a_fade": "fade_a",
            "part_b_fade": "fade_b",
            "part_c_fade": "fade_c",
            "part_d_fade": "fade_d",
            "part_e_fade": "fade_e",
            "part_x_fade": "fade_x",
            "part_y_fade": "fade_y",
            "part_z_fade": "fade_z",

            # 选择器变量
            "arm_selector": "arm_type",
        }"""
        #↑历史遗留物品

        self.variable_map = BoundParams.get_default_map()

        # --- 设置 QWebEngineView 和通信 ---
        self._bridge = _PythonApiBridge(self)
        self._channel = QWebChannel(self.page())
        self.page().setWebChannel(self._channel)
        self._channel.registerObject("py_api", self._bridge)
        logger.debug("EmoteWidget.__init__: QWebChannel bridge 'py_api' registered.")
        
        # --- 连接内部信号 ---
        self._bridge.player_ready_signal.connect(self._on_player_ready_handler)
        self.page().loadFinished.connect(self._on_page_load_finished)
        logger.debug("EmoteWidget.__init__: Internal signals connected.")

        # --- 加载前端页面 ---
        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'web_frontend'))
        html_path = os.path.join(frontend_dir, 'pyside_webview.html')
        logger.debug(f"EmoteWidget.__init__: Loading frontend URL: {html_path}")
        self.setUrl(QUrl.fromLocalFile(html_path))
        logger.debug("EmoteWidget.__init__: setUrl() called.")

    # --- 内部事件处理器 ---
    
    def _on_page_load_finished(self, ok: bool):
        logger.debug(f"--> _on_page_load_finished Signal Received. Status OK: {ok}")
        if ok:

            self.load_finished.emit()
            logger.info("内部页面加载成功，初始化启动画面并启动后台插件加载...")
            self._splash_start_time = time.time()
            
            self._update_splash_version()
            self._update_splash_main_progress(0.1, f"EmoteWidget v{__version__} 初始化...")
            self._update_splash_main_progress(0.2, "正在扫描插件目录...")

            self._plugin_loader_worker.scan_for_plugin_modules()

            self._plugin_loader_thread.start()
            
            self._update_splash_main_progress(0.3, "后台插件加载已启动...")
        else:
            logger.critical("内部页面加载失败！请检查 `pyside_webview.html` 路径。")

    def _on_player_ready_handler(self, timelines: list):
        """当 JS 端模型加载完成后由桥接信号调用。"""
        logger.debug(f"--> _on_player_ready_handler Signal Received. Timelines: {timelines}")
        
        if not self._instance_controller:
            logger.debug("_on_player_ready_handler: _instance_controller is None, creating new instance.")
            self._instance_controller = _FreeMoteInternalController(self.page().runJavaScript)
            
            if self._command_queue:
                logger.info(f"控制器已就绪，正在执行 {len(self._command_queue)} 条缓存的指令...")
                for name, args, kwargs in self._command_queue:
                    try:
                        method = getattr(self._instance_controller, name)
                        method(*args, **kwargs)
                    except Exception:
                        logger.exception(f"执行缓存指令 '{name}' 时出错。")
                self._command_queue.clear()

        self._update_splash_main_progress(0.95, f"模型 '{self.current_model_filename}' 已就绪！正在等待插件...")

        self._player_is_ready = True
        self.player_ready.emit(timelines)
        self._check_if_all_ready()
        logger.debug("_on_player_ready_handler: player_ready signal emitted.")

    # --- 辅助方法 ---

    def _check_if_all_ready(self):
        """
        检查所有并行加载任务是否都已完成。
        """
        if self._plugins_are_ready and self._player_is_ready:
            logger.info("所有加载任务均已完成，准备关闭启动画面。")
            self._update_splash_main_progress(1.0, "所有加载步骤完成！")
            self._dismiss_splash_screen()

    def _update_splash_main_progress(self, progress: float, text: str):
        safe_text = json.dumps(text)
        self.page().runJavaScript(f"SplashScreenAPI.updateMainProgress({progress}, {safe_text});")

    def _update_splash_plugin_progress(self, progress: float, text: str):
        safe_text = json.dumps(text)
        self.page().runJavaScript(f"SplashScreenAPI.updatePluginProgress({progress}, {safe_text});")

    def _add_splash_log(self, message: str, is_error: bool = False):
        safe_message = json.dumps(message)
        js_bool = "true" if is_error else "false"
        self.page().runJavaScript(f"SplashScreenAPI.addLog({safe_message}, {js_bool});")
    
    def _update_splash_version(self):
        safe_version = json.dumps(__version__)
        self.page().runJavaScript(f"SplashScreenAPI.setVersion({safe_version});")

    def _dismiss_splash_screen(self):
        if self._is_splash_dismissed: return
        self._is_splash_dismissed = True
        logger.info("所有加载步骤完成，正在隐藏启动画面...")
        self.page().runJavaScript("setTimeout(() => { SplashScreenAPI.dismiss(); }, 500);")

    def _proceed_to_model_loading_step(self):
        """
        在插件加载和最小显示时间都完成后，设置状态并检查是否可以关闭启动画面。
        """
        logger.info("插件流程已就绪。")
        self._update_splash_main_progress(0.9, "插件加载完毕。正在等待模型加载...")
        self._update_splash_plugin_progress(1.0, "完成")
        
        self._plugins_are_ready = True
        self._check_if_all_ready()

    def find_param_by_usage(self, usage_tag: str) -> dict | None:
        """根据特殊用途标签查找参数的完整信息。"""
        for param_info in self.variable_map.values():
            if isinstance(param_info, dict) and usage_tag in param_info.get("special_usage", []):
                return param_info
        return None

    def closeEvent(self, event):
        """
        重写 closeEvent 以确保所有后台资源被正确清理。
        """
        logger.info("EmoteWidget 正在关闭，开始清理资源...")
        
        self.stop_lip_sync()

        if self._plugin_loader_thread and self._plugin_loader_thread.isRunning():
            logger.info("正在请求插件加载线程退出...")
            self._plugin_loader_thread.terminate()
            self._plugin_loader_thread.deleteLater()
        
        if self.plugins:
            for plugin in self.plugins.get_all():
                try:
                    logger.info(f"正在清理插件: '{plugin.get_name()}'")
                    plugin.cleanup()
                except Exception:
                    logger.exception(f"清理插件 '{plugin.get_name()}' 时发生错误。")

        super().closeEvent(event)
        logger.info("EmoteWidget 清理完毕。")
    
    # --- 槽函数 ---
    @Slot(float)
    def _on_mouth_ratio_update(self, open_ratio):
        """
        (非线性映射+过饱和处理) 接收开合度，并将其通过曲线放大,支持乘比例系数达到过饱和效果。
        """
        # --- 非线性重映射 + 过饱和处理 ---
        # 对 open_ratio 取平方根 (或一个指数)。
        # 这会产生一个曲线，使得小的值被显著放大(系数小于0)/大的值被缩小(系数大于0)。
        # 例如: 0.1 -> 0.31, 0.2 -> 0.45, 0.5 -> 0.71

        # 过饱和将结果乘以一个略大于1的系数。
        # 使得曲线的末端可以超过1.0，从而增加最终停留在1.0的时间。
        # 在self.lip_sync_curve处自定义指数 , 在这里自定义系数(我感觉1.1够用，嘻嘻)

        lip_sync_config = self.config['lip_sync']
        final_ratio = (open_ratio ** lip_sync_config['mouth_ratio_curve']) * lip_sync_config['mouth_ratio_oversaturation']
        final_ratio = max(0.0, min(final_ratio, 1.0))

        param_info = self.mouth_param_info
        param_range = param_info['range'][1] - param_info['range'][0]
        target_value = param_info['range'][0] + final_ratio * param_range
        
        self.set_variable(param_info['name'], target_value, duration_ms=lip_sync_config['set_variable_duration_ms'])

    @Slot()
    def _reset_mouth_on_sync_finish(self):
        """当同步线程结束时，平滑地关闭嘴巴。"""
        logger.info("同步结束，正在重置嘴型。")
        self._lip_sync_thread = None
        mouth_param = self.find_param_by_usage(SpecialUsage.MOUTH_OPEN)
        if mouth_param:
            # 设置为值域的最小值（大概是闭嘴）
            duration = self.config['lip_sync']['close_mouth_duration_ms']
            self.set_variable(mouth_param['name'], mouth_param['range'][0], duration_ms=duration)

    @Slot(list)
    def _on_plugins_load_finished(self, instantiated_plugins: list):
        """
        当后台 Worker 完成插件实例化后，此槽函数在主线程中被调用。
        """
        logger.info(f"后台插件实例化完成。共 {len(instantiated_plugins)} 个插件，现在在主线程中初始化和注册...")
        
        for plugin in instantiated_plugins:
            try:
                self.plugins.register(plugin)
            except Exception:
                error_msg = f"✗ 初始化或注册插件 '{getattr(plugin, 'get_name', lambda: 'Unknown')()}' 时出错。"
                logger.error(error_msg, exc_info=True)
                self._add_splash_log(error_msg, is_error=True)

        self.plugins_load_finished.emit()
        
        MIN_SPLASH_DURATION_S = 1.0

        elapsed_s = time.time() - self._splash_start_time
        delay_ms = max(0, (MIN_SPLASH_DURATION_S - elapsed_s) * 1000)
        logger.info(f"插件加载和初始化耗时 {elapsed_s:.2f} 秒。将延迟 {delay_ms:.0f}ms 以满足最小显示时长。")

        QTimer.singleShot(int(delay_ms), self._proceed_to_model_loading_step)

    # ==========================================================================
    # FreeMote SDK 公共方法
    # ==========================================================================

    # --- 1. 基本模型操作 ---

    def load_model(self, model_filename: str):
        """
        动态加载或更换模型，并自动从缓存或解包获取其变量映射表。

        此方法是与模型交互的起点。它会：
        1. 调用 `BoundParams.get_bound_map`，该函数会优先从缓存 (`.emote_cache`)
           加载此模型的 `.map.json` 文件。
        2. 如果缓存不存在，`BoundParams` 会自动执行沙盒解包，通过正则匹配生成
           一个新的映射表，并将其存入缓存。
        3. 将获取到的映射表应用到当前 `EmoteWidget` 实例。
        4. 最后，向网页发送指令以加载 `.psb` 模型文件。

        参数:
            model_filename (str):
                模型文件的名称 (例如 "chara.psb")。
                文件必须位于 `web_frontend/models/` 目录下。
        """
        self.current_model_filename = model_filename
        logger.info(f"开始加载模型 '{model_filename}'...")
        frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'web_frontend'))
        model_path = os.path.join(frontend_dir, 'models', model_filename)
        self.variable_map = BoundParams.get_bound_map(model_path)
        self.page().runJavaScript(f"loadNewModel('{model_filename}');")

    def save_bindings(self):
        """
        将当前在内存中的 `variable_map` (可能已被用户修改) 保存回缓存文件。

        这允许用户在 Tester UI 中对参数绑定所做的更改被持久化，
        以便下次加载同一模型时自动应用。
        """
        if not self.current_model_filename:
            logger.error("没有已加载的模型，无法保存绑定。")
            return
        
        logger.info(f"正在将 '{self.current_model_filename}' 的绑定更新到缓存...")
        BoundParams.update_cache(self.current_model_filename, self.variable_map)

    def show(self):
        """
        显示模型（如果它被隐藏了）。
        """
        if self._controller: self._controller.show()

    def hide(self):
        """
        隐藏模型，使其不可见。动画和物理效果仍在后台计算。
        """
        if self._controller: self._controller.hide()

    def start_lip_sync(self, audio_queue: queue.Queue):
        """
        根据一个外部音频流队列启动口型同步，这玩意会自适应音量大小(大概)。
        """
        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self.stop_lip_sync()

        mouth_param = self.find_param_by_usage(SpecialUsage.MOUTH_OPEN)
        if not mouth_param:
            logger.error("口型同步错误 - 未在 variable_map 中找到标有 'MOUTH_OPEN' 的参数。")
            return
        
        self.mouth_param_info = mouth_param

        lip_sync_config = self.config['lip_sync']
        self._lip_sync_thread = StreamLipSyncThread(
            audio_queue,
            mean_decay_time=lip_sync_config['mean_decay_time_s'],
            peak_decay_time=lip_sync_config['peak_decay_time_s'],
            update_fps=lip_sync_config['update_fps'],
            activation_ratio=lip_sync_config['activation_ratio']
        )
        self._lip_sync_thread.mouth_open_ratio_updated.connect(self._on_mouth_ratio_update)
        self._lip_sync_thread.debug_data_updated.connect(self._monitor_widget.update_data)
        self._lip_sync_thread.finished.connect(self._reset_mouth_on_sync_finish)
        self._lip_sync_thread.start()


    def start_lip_sync_from_file(self, filepath: str):
        """
        一个高级便利函数，用于从 .wav 文件启动口型同步。

        它在内部创建队列，并启动文件到流的转换器线程。
        """
        self.stop_lip_sync()
        self._streamer_stop_event.clear()
        audio_stream_queue = queue.Queue()
        self.start_lip_sync(audio_stream_queue)
        logger.info(f"{filepath}启动同步，{audio_stream_queue}")
        self.stream_audio_file(filepath, audio_stream_queue)

    def stop_lip_sync(self):
        """停止口型同步。"""
        if self._streamer_stop_event:
            self._streamer_stop_event.set()

        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self._lip_sync_thread.stop()
    

    # --- 2. 变换与位置 (Transform) ---

    def set_coord(self, x: int, y: int, duration_ms: int = 0):
        """
        设置模型在画布上的坐标。

        坐标系的原点(0, 0)位于画布的正中心。
        
        参数:
            x (int): 横坐标。正值向右，负值向左。
            y (int): 纵坐标。正值向下，负值向上。
            duration_ms (int, optional):
                完成移动所需的毫秒数。默认为0，表示立即移动。
                大于0的值会产生平滑的移动动画。
        
        示例:
            # 立即移动到画布右下角
            widget.set_coord(200, 150)
            # 在 1 秒内平滑移动回中心
            widget.set_coord(0, 0, duration_ms=1000)
        """
        if self._controller: self._controller.set_coord(x, y, duration_ms)

    def set_scale(self, scale: float, duration_ms: int = 0):
        """
        设置模型的缩放比例。

        参数:
            scale (float):
                缩放倍数。1.0 为原始大小，0.5 为一半大小，2.0 为两倍大小。
            duration_ms (int, optional):
                完成缩放所需的毫秒数。默认为0，表示立即缩放。
        
        示例:
            # 在 500 毫秒内放大到 1.2 倍
            widget.set_scale(1.2, duration_ms=500)
        """
        if self._controller: self._controller.set_scale(scale, duration_ms)

    def set_rotation(self, angle_deg: float, duration_ms: int = 0):
        """
        设置模型的旋转角度。

        参数:
            angle_deg (float): 旋转角度，单位为度(°)。正值为顺时针旋转。
            duration_ms (int, optional):
                完成旋转所需的毫秒数。默认为0，表示立即旋转。

        示例:
            # 立即顺时针旋转 30 度
            widget.set_rotation(30)
        """
        if self._controller: self._controller.set_rotation(angle_deg, duration_ms)
        
    def auto_center(self, duration_ms: int = 300):
        """
        自动调整模型的缩放和位置，使其完美地居中于视图中。

        函数会自动查询模型的尺寸边界，计算最佳的缩放比例和坐标，
        以确保模型的任何一部分都不会被裁切，并带有一定的边距。

        参数:
            duration_ms (int, optional):
                完成居中动画所需的毫秒数。默认为 300ms。
        """
        if self._controller: self._controller.auto_center(duration_ms)

    # --- 3. 动画控制 (Animation) ---

    def play(self, timeline_name: str):
        """
        播放一个主时间轴动画。

        主时间轴动画通常是角色的核心动作，例如“站立”、“走路”、“挥手”等。
        播放一个新的主时间轴动画会自动停止上一个。

        参数:
            timeline_name (str):
                要播放的动画名称，需要与模型文件中定义的名称完全一致。
                可以通过 `player_ready` 信号返回的列表或 `get_main_timelines()` 获取。

        示例:
            widget.play("idle_01")
        """
        if self._controller: self._controller.play(timeline_name)

    def animation_reset(self):
        """
        重置模型的所有状态到初始默认值。

        这包括：
        - 停止所有正在播放的动画（主时间轴和差分）。
        - 重置模型的坐标、缩放和旋转。
        - 恢复默认的外观（颜色、透明度、灰度）。
        - 恢复默认的物理和风力效果。
        
        它提供了一种快速将模型恢复到“干净”状态的方法。
        """
        
        if self._controller:
            anim_config = self.config['animation']
            self._controller.animation_reset(
                duration_ms=anim_config['reset_duration_ms'],
                init_anim_name=anim_config['initialization_name']
            )
    
    def set_diff_timeline(self, slot: int, timeline_name: str):
        """
        在指定槽位上播放一个差分（附加）动画。

        差分动画可以与主时间轴动画叠加播放，通常用于实现表情变化、
        穿戴配件、特效等。例如，在“站立”动画之上，叠加一个“脸红”的差分动画。
        
        参数:
            slot (int):
                要使用的槽位，范围是 1 到 6。
            timeline_name (str):
                要播放的差分动画名称。可以通过 `get_diff_timelines()` 获取。
                传入一个空字符串 "" 可以清空该槽位的动画。

        示例:
            # 让角色脸红
            widget.set_diff_timeline(1, "blush")
            # 停止脸红
            widget.set_diff_timeline(1, "")
        """
        if self._controller: self._controller.set_diff_timeline(slot, timeline_name)

    def set_speed(self, speed_ratio: float):
        """
        设置所有动画的全局播放速度。

        参数:
            speed_ratio (float):
                播放速度的倍率。1.0 为正常速度，0.5 为慢放，2.0 为快进。

        示例:
            # 进入子弹时间！
            widget.set_speed(0.2)
        """
        if self._controller: self._controller.set_speed(speed_ratio)

    def stop_all_timelines(self):
        """
        停止所有正在播放的动画（包括主时间轴和所有差分动画）。
        """
        if self._controller: self._controller.stop_all_timelines()

    # --- 4. 外观与特效 (Appearance & FX) ---

    def show_dialog(self, text: str, duration_ms: int = 5000, theme: str = 'default',type_speed: int =50, anchor_marker: str = 'dialog_anchor'):
        """
        在角色头顶显示一个可更换主题的对话气泡。

        参数:
            text (str): 要显示的文本内容。
            duration_ms (int, optional): 对话框显示的时长（毫秒）。默认为 5000ms。
            theme (str, optional): 
                要使用的对话框主题。对应于 'web_frontend/dialogs/' 目录下的
                HTML文件名 (不含扩展名)。默认为 'default'。
        """
        if self._controller:
            y_offset = -20  # 垂直偏移量，可以根据需要调整
            
            self._controller.show_character_dialog(text, duration_ms, theme, y_offset, type_speed, anchor_marker)

    def set_background_color(self, r: int, g: int, b: int, a: float):
        """
        设置渲染区域的背景颜色。

        这允许您将模型放置在任意颜色的背景之上，或者通过设置透明度
        为0，将其叠加在其他窗口组件之上（如果窗口本身支持透明）。

        参数:
            r (int): 红色分量 (0-255)。
            g (int): 绿色分量 (0-255)。
            b (int): 蓝色分量 (0-255)。
            a (float): 透明度 (0.0 - 1.0)。
        
        示例:
            # 设置为半透明的蓝色背景
            widget.set_background_color(0, 0, 255, 0.5)
            # 设置为完全透明的背景
            widget.set_background_color(0, 0, 0, 0.0)
        """
        if self._controller: self._controller.set_background_color(r, g, b, a)
    
    def set_background_image(self, image_filename: str | None):
        """
        设置或移除视图的背景图片。

        图片文件应该存放在 `web_frontend/backgrounds/` 目录下。

        参数:
            image_filename (str | None):
                要显示的背景图片的文件名 (例如 "scene_day.jpg")。
                如果传入 `None`，则会移除当前的背景图片，恢复为纯色背景。
        
        示例:
            # 设置背景
            widget.set_background_image("image.png")
            # 移除背景
            widget.set_background_image(None)
        """
        if not self._controller:
            return
        if image_filename is None:
            image_url = None
        else:
            base_dir = os.path.dirname(__file__)
            bg_path = os.path.abspath(os.path.join(
                base_dir, 'web_frontend', 'backgrounds', image_filename
            ))

            if not os.path.exists(bg_path):
                logger.warning(f"背景图片未找到: {bg_path}")
                return
            image_url = QUrl.fromLocalFile(bg_path).toString()
        
        # 将最终的 URL (或 None) 传递给控制器
        self._controller.set_background_image(image_url)

    def set_grayscale(self, intensity: float, duration_ms: int = 0):
        """
        设置模型的灰度（黑白）效果。

        参数:
            intensity (float):
                灰度强度，范围从 0.0 (完全彩色) 到 1.0 (完全黑白)。
            duration_ms (int, optional):
                完成效果过渡所需的毫秒数。

        示例:
            # 在2秒内变成黑白
            widget.set_grayscale(1.0, duration_ms=2000)
        """
        if self._controller: self._controller.set_grayscale(intensity, duration_ms)

    def set_global_alpha(self, alpha: float, duration_ms: int = 0):
        """
        设置模型的全局透明度。

        参数:
            alpha (float): 透明度，范围从 0.0 (完全透明) 到 1.0 (完全不透明)。
            duration_ms (int, optional): 完成效果过渡所需的毫秒数。

        示例:
            # 在1.5秒内隐身
            widget.set_global_alpha(0.0, duration_ms=1500)
        """
        if self._controller: self._controller.set_global_alpha(alpha, duration_ms)

    def set_vertex_color(self, color_hex: str, duration_ms: int = 0):
        """
        为模型叠加一层顶点颜色。

        这可以用来给模型整体染色，例如在黑暗中发出蓝光等效果。

        参数:
            color_hex (str):
                颜色的十六进制字符串，格式为 "#RRGGBB"，例如 "#FF0000" 代表红色。
                传入 "#808080" (中性灰) 或 "#FFFFFF" (白色) 通常可以恢复原始颜色。
            duration_ms (int, optional): 完成颜色过渡所需的毫秒数。

        示例:
            # 让角色变成红色
            widget.set_vertex_color("#FF0000")
        """
        if self._controller: self._controller.set_vertex_color(color_hex, duration_ms)

    # --- 5. 物理与环境 (Physics & Environment) ---

    def set_physics_scale(self, hair: float = 1.0, parts: float = 1.0, bust: float = 1.0):
        """
        分别设置不同部位的物理摆动幅度。

        参数:
            hair (float, optional): 头发的摆动幅度倍率。
            parts (float, optional): 配件（如裙子、丝带）的摆动幅度倍率。
            bust (float, optional): 胸部的摆动幅度倍率。

        示例:
            # 让头发飘动得更厉害
            widget.set_physics_scale(hair=2.5)
            # 冻结所有物理效果
            widget.set_physics_scale(0, 0, 0)
        """
        if self._controller: self._controller.set_physics_scale(hair, parts, bust)

    def set_wind(self, speed: float, power_min: float = 0.0, power_max: float = 2.0):
        """
        开启并设置全局风力效果。

        这会让所有对风有响应的部件（通常是头发和衣物）持续飘动。

        参数:
            speed (float): 风速。设置为 0 可以停止风。
            power_min (float, optional): 最小风力强度。
            power_max (float, optional): 最大风力强度。

        示例:
            # 吹起一阵大风
            widget.set_wind(10.0, 1.0, 3.0)
            # 风停了
            widget.set_wind(0)
        """
        if self._controller: self._controller.set_wind(speed, power_min, power_max)

    # --- 6. 数据查询 (Data Query) ---

    def get_main_timelines(self, callback):
        """
        异步获取模型所有可用的【主时间轴动画】的名称列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[str]` 参数。
        """
        if self._controller: self._controller.get_main_timelines(callback)

    def get_diff_timelines(self, callback):
        """
        异步获取模型所有可用的【差分（附加）动画】的名称列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[str]` 参数。
        """
        if self._controller: self._controller.get_diff_timelines(callback)

    def get_variables(self, callback):
        """
        异步获取模型所有可用的【底层变量】的详细信息列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[dict]` 参数。
        """
        if self._controller: self._controller.get_variables(callback)

    def get_marker_position(self, marker_name: str, callback):
        """
        异步获取模型上一个“标记点”的屏幕坐标。

        参数:
            marker_name (str): 在模型中定义的标记点名称。
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `dict` 或 `None` 参数。
        """
        if self._controller: self._controller.get_marker_position(marker_name, callback)

    def get_available_special_usage_tags(self) -> list[str]:
        """
        获取所有预定义的“特殊用途”标签列表。
        
        此方法提供了一个由 SDK 规范化的标准标签列表，供上层 UI 
        (例如多选下拉框) 使用。这避免了在 UI 层硬编码这些值，
        实现了 UI 与数据模型的解耦。

        返回:
            list[str]: 所有可用特殊标签的字符串列表。
        """
        # 使用 Python 的内省机制动态地从 BoundParams.SpecialUsage 类获取所有标签
        return [
            getattr(BoundParams.SpecialUsage, attr) 
            for attr in dir(BoundParams.SpecialUsage) 
            if not attr.startswith('__')
        ]

    # --- 7. 底层参数控制 (Advanced) ---

    def set_variable(self, name: str, value: float, duration_ms: int = 0):
        """
        直接设置模型的一个底层变量的值。

        这是最精细的控制方式，可以让你脱离预设动画，直接通过代码
        来驱动模型的部件，例如手动控制眼睛的开合度、嘴巴的形状等。

        参数:
            name (str): 变量的名称，可以通过 get_variables() 获取。
            value (float): 要设置的目标值。
            duration_ms (int, optional): 完成值改变所需的毫秒数，以实现平滑过渡。
        """
        if self._controller: self._controller.set_variable(name, value, duration_ms)
        
    def get_variable(self, name: str, callback):
        """
        异步获取一个底层变量的当前值。

        参数:
            name (str): 变量的名称。
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `float` 参数。
        """
        if self._controller: self._controller.get_variable(name, callback)

    # --- 8. 鼠标交互控制 ---
    def enable_drag(self, enable: bool):
        """
        开启或关闭模型的鼠标拖动功能。

        参数:
            enable (bool): True 为开启，False 为关闭。
        """
        # 此方法直接操作 JS，无需等待控制器就绪
        js_bool = json.dumps(enable) 
        self.page().runJavaScript(f"enablePlayerDrag({js_bool});")

    def enable_zoom(self, enable: bool):
        """
        开启或关闭模型的鼠标滚轮缩放功能。

        参数:
            enable (bool): True 为开启，False 为关闭。
        """
        # 此方法直接操作 JS，无需等待控制器就绪
        js_bool = json.dumps(enable)
        self.page().runJavaScript(f"enablePlayerZoom({js_bool});")

    def enable_gaze_control(self, enable: bool):
        """
        开启或关闭模型的视线跟随鼠标功能 (数据驱动版)。
        """
        
        head_lr_param = self.find_param_by_usage(SpecialUsage.HEAD_LR)
        head_ud_param = self.find_param_by_usage(SpecialUsage.HEAD_UD)
        eye_lr_param = self.find_param_by_usage(SpecialUsage.EYE_LR)
        eye_ud_param = self.find_param_by_usage(SpecialUsage.EYE_UD)

        if not all([head_lr_param, head_ud_param, eye_lr_param, eye_ud_param]):
            logger.warning("视线跟随警告 - 缺少必要的 HEAD_LR/UD 或 EYE_LR/UD 特殊标签。")
            return
            
        gaze_params = {
            "head_lr": head_lr_param,
            "head_ud": head_ud_param,
            "eye_lr": eye_lr_param,
            "eye_ud": eye_ud_param,
        }
        
        params_json = json.dumps(gaze_params)
        js_code = f"enableGazeControl({str(enable).lower()}, {params_json});"
        self.page().runJavaScript(js_code)
    
    # --- 工具函数 ---
    def stream_audio_file(self, filepath: str, audio_queue: queue.Queue):
        """
        在一个新的可中止的线程中读取 .wav 文件，同时播放它并将其数据块放入队列。
        """
        blocksize_hz = self.config['file_streaming']['blocksize_hz']
        def thread_target():
            logger.info(f"文件流: 开始读取和播放 '{os.path.basename(filepath)}'...")
            try:
                with sf.SoundFile(filepath, 'r') as audio_file:
                    samplerate, channels = audio_file.samplerate, audio_file.channels
                    blocksize = int(samplerate / blocksize_hz)
                    
                    with sd.OutputStream(samplerate=samplerate, channels=channels) as stream:
                        while not self._streamer_stop_event.is_set():
                            audio_chunk = audio_file.read(blocksize, dtype='float32')
                            if len(audio_chunk) == 0:
                                break # 文件结束
                            
                            stream.write(audio_chunk)
                            mono_chunk = audio_chunk.mean(axis=1) if channels > 1 else audio_chunk
                            audio_queue.put(mono_chunk)
            except Exception as e:
                logger.error(f"文件流错误", exc_info=True)
            finally:
                audio_queue.put(None) # 确保消费者线程也能结束
                if self._streamer_stop_event.is_set():
                    logger.info("文件流被外部指令中止。")
                else:
                    logger.info("文件流正常结束。")

        threading.Thread(target=thread_target, daemon=True).start()

    def show_lip_sync_monitor(self, show: bool, as_window: bool = True):
        """
        显示或隐藏口型同步监视器。

        参数:
            show (bool): True to show, False to hide.
            as_window (bool, optional):
                如果为 True (默认)，监视器将作为一个独立的子窗口弹出。
                如果为 False，您需要自己获取这个控件并将其添加到您的布局中。
                See `get_monitor_widget()`.
        """
        if as_window:
            if show:
                self._monitor_widget.setWindowFlag(Qt.Window, True)
            self._monitor_widget.setVisible(show)
        else:
            self.get_monitor_widget().setVisible(show)

    def get_monitor_widget(self) -> LipSyncMonitorWidget:
        """
        返回内部的监视器控件实例。
        
        这允许上层UI将监视器嵌入到自己的布局中，
        而不是作为一个独立的窗口弹出。
        
        返回:
            LipSyncMonitorWidget: 监视器控件实例。
        """
        return self._monitor_widget


# ==========================================================================
# 内部控制器
# ==========================================================================
class _FreeMoteInternalController:
    """这是一个私有类，作为 EmoteWidget 的内部实现细节，请不要直接使用。"""
    def __init__(self, js_executor):
        self._execute_js = js_executor
        self.js_player_name = "emotePlayer"

    def _safe_run(self, js_code):
        js_to_execute = f"""
        (() => {{
            const player = {self.js_player_name};
            if (player && player.initialized) {{
                try {{
                    {js_code}
                }} catch (e) {{
                    // 将错误信息发送回 Python
                    if (window.py_api && window.py_api.on_js_error) {{
                        const message = e.message || 'Unknown error in _safe_run.';
                        const stack = e.stack || 'No stack trace.';
                        window.py_api.on_js_error(message, stack);
                    }}
                }}
            }}
        }})();
    """
        self._execute_js(js_to_execute)

    def _safe_query(self, js_code, callback):
        js_to_execute = f"""
            (() => {{
                const player = {self.js_player_name};
                if (!player || !player.initialized || !player.playerId) {{
                    return null;
                }}
                try {{
                    const complexResult = {js_code};
                    return JSON.stringify(complexResult);
                }} catch (e) {{
                    console.error("[Python Query] 执行查询或JSON化时出错:", e);
                    return null;
                }}
            }})()
        """
        def json_parsing_wrapper(json_string):
            if json_string is None:
                callback(None)
                return
            try:
                data = json.loads(json_string)
                callback(data)
            except json.JSONDecodeError:
                logger.error(f"无法解析从JS返回的JSON: {json_string[:200]}...")
                callback(None)
        self._execute_js(js_to_execute, json_parsing_wrapper)

    # --- 1. 基本模型操作 ---
    def show(self):
        self._safe_run(f'{self.js_player_name}.hide = false;')
    def hide(self):
        self._safe_run(f'{self.js_player_name}.hide = true;')
    def auto_center(self, duration_ms):
        self._safe_run(f'autoCenterPlayer({duration_ms});')

    # --- 2. 变换与位置 (Transform) ---
    def set_coord(self, x, y, duration_ms):
        self._safe_run(f'{self.js_player_name}.setCoord({x}, {y}, {duration_ms});')
    def set_scale(self, scale, duration_ms):
        self._safe_run(f'{self.js_player_name}.setScale({scale}, {duration_ms});')
    def set_rotation(self, angle_deg, duration_ms):
        angle_rad = angle_deg * (3.14159 / 180.0)
        self._safe_run(f'{self.js_player_name}.setRot({angle_rad}, {duration_ms});')

    # --- 3. 动画控制 (Animation) ---
    def play(self, timeline_name):
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.mainTimelineLabel = {safe_name};')
    def animation_reset(self, duration_ms: int, init_anim_name: str | None):
        self.stop_all_timelines()
        self.set_coord(0, 0, duration_ms)
        self.set_scale(1.0, duration_ms)
        self.set_rotation(0, duration_ms)
        self.set_global_alpha(1.0, duration_ms)
        self.set_grayscale(0.0, duration_ms)
        self.set_vertex_color("#808080FF", 300)
        self.set_physics_scale(1.0, 1.0, 1.0)
        self.set_wind(0, 0, 0)
        if init_anim_name:
            logger.info(f"Python 指令: 播放初始化动画 '{init_anim_name}'。")
            self.play(init_anim_name)
        logger.info("Python 指令: 完成模型状态重置。")
    def set_diff_timeline(self, slot, timeline_name):
        if not 1 <= slot <= 6: raise ValueError("Slot must be between 1 and 6.")
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.diffTimelineSlot{slot} = {safe_name};')
    def set_speed(self, speed_ratio):
        self._safe_run(f'{self.js_player_name}.speed = {speed_ratio};')
    def stop_all_timelines(self):
        self._safe_run(f'{self.js_player_name}.stopTimeline();')

    # --- 4. 外观与特效 (Appearance & FX) ---
    def set_background_color(self, r, g, b, a):
        self._execute_js(f"setBackgroundColor({r}, {g}, {b}, {a});")
    def set_background_image(self, image_url: str | None):
        safe_url = json.dumps(image_url)
        self._execute_js(f"setBackgroundImage({safe_url});")
    def show_character_dialog(self, text, duration_ms, theme, y_offset, type_speed, anchor_marker):
        safe_text = json.dumps(text)
        safe_theme = json.dumps(theme)
        safe_anchor = json.dumps(anchor_marker)
        js_code = f'showCharacterDialog({safe_text}, {duration_ms}, {safe_theme}, {y_offset}, {type_speed}, {safe_anchor});'

        logger.debug("已触发show_character_dialog")

        self._safe_run(js_code)
    def set_grayscale(self, intensity, duration_ms):
        value = max(0.0, min(float(intensity), 1.0))
        self._safe_run(f'{self.js_player_name}.setGrayscale({value}, {duration_ms});')
    def set_global_alpha(self, alpha, duration_ms):
        value = max(0.0, min(float(alpha), 1.0))
        self._safe_run(f'{self.js_player_name}.setGlobalAlpha({value}, {duration_ms});')
    def set_vertex_color(self, color_hex, duration_ms):
        safe_color = json.dumps(color_hex)
        self._safe_run(f'{self.js_player_name}.setVertexColor({safe_color}, {duration_ms});')

    # --- 5. 物理与环境 (Physics & Environment) ---
    def set_physics_scale(self, hair, parts, bust):
        self._safe_run(f'{self.js_player_name}.hairScale = {hair};')
        self._safe_run(f'{self.js_player_name}.partsScale = {parts};')
        self._safe_run(f'{self.js_player_name}.bustScale = {bust};')
    def set_wind(self, speed, power_min, power_max):
        self._safe_run(f'{self.js_player_name}.windSpeed = {speed}; {self.js_player_name}.windPowMin = {power_min}; {self.js_player_name}.windPowMax = {power_max};')

    # --- 6. 数据查询 (Data Query) ---
    def get_main_timelines(self, callback):
        self._safe_query(f'{self.js_player_name}.mainTimelineLabels', callback)
    def get_diff_timelines(self, callback):
        self._safe_query(f'{self.js_player_name}.diffTimelineLabels', callback)
    def get_variables(self, callback):
        self._safe_query(f'{self.js_player_name}.variableList', callback)
    def get_marker_position(self, marker_name, callback):
        safe_name = json.dumps(marker_name)
        self._safe_query(f'{self.js_player_name}.getMarkerPosition({safe_name})', callback)

    # --- 7. 底层参数控制 (Advanced) ---
    def set_variable(self, name, value, duration_ms):
        safe_name = json.dumps(name)
        self._safe_run(f'{self.js_player_name}.setVariable({safe_name}, {value}, {duration_ms});')
    def get_variable(self, name, callback):
        safe_name = json.dumps(name)
        self._safe_query(f'{self.js_player_name}.getVariable({safe_name})', callback)