import os
import json
import time
import uuid
import queue
import threading
from typing import Callable, Any, Optional
import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import QObject, Slot, Signal, QThread, QTimer

FloatArray = NDArray[np.float32]

from emote_widget.default_config.default_constants import DEFAULT_CONFIG, __version__

from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.core.lipsync_thread import StreamLipSyncThread
from emote_widget.core.plugin_system import PluginAccessor, PluginLoaderWorker
from emote_widget.core.plugin_interface import IEmotePlugin
from emote_widget.core.python_api_bridge import PythonApiBridge

import emote_widget.utils.bound_params as bound_params
from emote_widget.utils.audio_utils import stream_audio_file
from emote_widget.utils.paths import resolve_resource_url
from emote_widget.utils.logger import emote_widget_logger as logger

class EmoteController(QObject):
    """
    [核心控制器] 负责业务逻辑编排。
    
    职责:
    1. 管理模型状态 (State Management)
    2. 处理音频分析线程 (LipSync Logic)
    3. 生成并分发 JS 指令 (Command Dispatch)
    4. 管理插件生命周期
    
    注意：此类不应包含任何 UI 绘图代码。
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

    lip_sync_debug_data = Signal(dict)
    """音频同步的调试信息，用于给外界组件接收"""

    def __init__(self, view_adapter: IViewAdapter, plugin_dir: str | None = None, config_override: dict[str, Any] | None = None, bound_config_override: str | None = None) -> None:
        """初始化 EmoteWidgetController 组件。"""

        super().__init__()

        self.view_adapter: IViewAdapter = view_adapter

        self.config: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
        # 如果用户提供了覆盖配置，则进行合并
        if config_override:
            for key, value in config_override.items():
                if key in self.config and isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value
        if bound_config_override:
            bound_params.load_config(bound_config_override)

        self.js_player_name: str = "emotePlayer" 
        self._command_queue: list[str] = []  # 指令队列
        self._pending_queries: dict[str, Callable[[Any], None]] = {}  # 回调挂号表

        # 插件系统
        self.plugin_dir: str
        if plugin_dir:
             self.plugin_dir = plugin_dir
        else:
             self.plugin_dir = os.path.join(os.getcwd(), 'plugins')

        self.plugins: PluginAccessor = PluginAccessor()
        self._plugin_loader_thread: QThread = QThread(self)
        self._plugin_loader_worker: PluginLoaderWorker = PluginLoaderWorker(self.plugin_dir)
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

        self.current_model_filename = None # 当前加载的模型文件名
        
        # --- 透明模式状态管理 ---
        self._is_page_transparent = False
        self._is_window_transparent = False
        self._cached_window_flags = None
        self._cached_bg_color: dict[str, int | float] = {"r": 255, "g": 255, "b": 255, "a": 1.0}

        self.variable_map = bound_params.get_default_map()

        # --- 设置通信 ---
        self._bridge = PythonApiBridge(self)
        
        # --- 连接内部信号 ---
        self._bridge.on_character_clicked_signal.connect(self.on_character_clicked)
        self._bridge.on_character_hovered_signal.connect(self.on_character_hovered)
        
        self._bridge.player_ready_signal.connect(self._on_player_ready_handler)
        self._bridge.query_result_signal.connect(self._handle_query_result)

        self.view_adapter.register_python_bridge(self._bridge, "py_api")

    @Slot(str,str)
    def _handle_query_result(self, request_id: str, result_json: str | None):
        """处理从 Bridge 回来的数据"""
        # 1. 检查是否存在挂号
        if request_id in self._pending_queries:
            # 2. 取出并移除回调 (Pop)
            callback = self._pending_queries.pop(request_id)
            
            try:
                # 3. 解析数据
                data = json.loads(result_json) if result_json is not None else None
                callback(data)
            except Exception as e:
                logger.error(f"解析 JS 回传数据失败: {e}")
                callback(None)
        else:
            # 可能是超时了或者 ID 错误，记录但不处理
            logger.debug(f"收到未知 request_id 的查询结果: {request_id[:8]}...")

    def _safe_run(self, js_code: str):
        """执行无返回值的 JS 代码 (支持队列缓存)"""
        if not self._player_is_ready:
            self._command_queue.append(js_code)
            logger.debug(f"模型未就绪，指令已缓存: {js_code[:50]}...")
            return

        full_script = f"""
        (() => {{
            try {{ {js_code} }} catch(e) {{
                if(py_api) py_api.on_js_error(e.message, e.stack);
            }}
        }})();
        """
        self.view_adapter.run_javascript(full_script)

    def _safe_query(self, expression: str, callback: Callable[[Any], None] | None) -> None:
        """
        执行有返回值的 JS 查询。
        
        不再使用 adapter 的 callback，而是通过 Bridge 异步回环。
        查询结果将通过 query_result_signal 返回。
        """
        if not self._player_is_ready:
            logger.warning("模型未就绪，无法执行查询。")
            if callback and callable(callback): 
                callback(None)
            return

        if callback is None or not callable(callback):
            logger.warning(f"查询 '{expression}' 未提供有效的 callback，已跳过。")
            return

        # 1. 生成请求 ID 并挂号
        request_id = str(uuid.uuid4())
        self._pending_queries[request_id] = callback

        # 2. 构造 JS 包装器，结果通过 py_api 回传
        js_code = f"""
        (() => {{
            const reqId = "{request_id}";
            try {{
                const res = {expression};
                const payload = (res === undefined) ? null : JSON.stringify(res);
                
                if (py_api) {{
                    py_api.receive_query_result(reqId, payload);
                }}
            }} catch(e) {{
                console.error("[Query Failed]", e);
                if (py_api) {{
                    py_api.receive_query_result(reqId, null);
                }}
            }}
        }})();
        """
        
        # 3. 发送 (Fire and Forget)
        self.view_adapter.run_javascript(js_code)


    # --- 内部事件处理器 ---
    
    def on_page_load_finished(self, ok: bool):
        logger.debug(f"--> _on_page_load_finished Signal Received. Status OK: {ok}")
        if ok:

            self.load_finished.emit()
            logger.info("内部页面加载成功，初始化启动画面并启动后台插件加载...")
            self._splash_start_time = time.time()
            
            self._update_splash_version()
            self._update_splash_main_progress(0.1, f"EmoteWidget v{__version__} 初始化...")

            self._init_default_theme()

            self._update_splash_main_progress(0.2, "正在扫描插件目录...")

            self._plugin_loader_worker.scan_for_plugin_modules()

            self._plugin_loader_thread.start()
            
            self._update_splash_main_progress(0.3, "后台插件加载已启动...")
        else:
            logger.critical("内部页面加载失败！请检查 `pyside_webview.html` 路径。")

    def _on_player_ready_handler(self, timelines: list[str]) -> None:
        """当 JS 端模型加载完成后由桥接信号调用。"""
        logger.info(f"模型 '{self.current_model_filename}' JS对象已就绪。")
        
        self._player_is_ready = True

        if self._command_queue:
            logger.info(f"正在执行 {len(self._command_queue)} 条缓存指令...")
            for js_code in self._command_queue:
                full_script = f"try {{ {js_code} }} catch(e) {{ console.error(e); }}"
                self.view_adapter.run_javascript(full_script)
            self._command_queue.clear()

        self._update_splash_main_progress(0.6, f"模型 '{self.current_model_filename}' 加载中,正在分析变量...")

        self._perform_introspection(timelines)

    # --- 辅助方法 ---

    def _init_default_theme(self):
        """预加载默认对话框主题，防止后续报错"""
        default_theme_url = resolve_resource_url("default.html", "dialogs")
        if default_theme_url:
            safe_url = json.dumps(default_theme_url)
            logger.info("预加载默认对话框主题...")
            self._safe_run(f"loadDialogTheme({safe_url});")
        else:
            logger.warning("默认对话框主题 default.html 未找到，可能导致对话框功能异常。")

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
        self.view_adapter.run_javascript(f"SplashScreenAPI.updateMainProgress({progress}, {safe_text});")

    def _update_splash_plugin_progress(self, progress: float, text: str):
        safe_text = json.dumps(text)
        self.view_adapter.run_javascript(f"SplashScreenAPI.updatePluginProgress({progress}, {safe_text});")

    def _add_splash_log(self, message: str, is_error: bool = False):
        safe_message = json.dumps(message)
        js_bool = "true" if is_error else "false"
        self.view_adapter.run_javascript(f"SplashScreenAPI.addLog({safe_message}, {js_bool});")
    
    def _update_splash_version(self):
        safe_version = json.dumps(__version__)
        self.view_adapter.run_javascript(f"SplashScreenAPI.setVersion({safe_version});")

    def _dismiss_splash_screen(self):
        if self._is_splash_dismissed: return
        self._is_splash_dismissed = True
        logger.info("所有加载步骤完成，正在隐藏启动画面...")
        self.view_adapter.run_javascript("setTimeout(() => { SplashScreenAPI.dismiss(); }, 500);")

    def _proceed_to_model_loading_step(self):
        """
        在插件加载和最小显示时间都完成后，设置状态并检查是否可以关闭启动画面。
        """
        logger.info("插件流程已就绪。")
        self._update_splash_main_progress(0.8, "插件加载完毕。正在等待模型...")
        self._update_splash_plugin_progress(1, "完成")
        
        self._plugins_are_ready = True
        self._check_if_all_ready()

    def _perform_introspection(self, timelines: list[str]) -> None:
        """
        获取变量列表，生成或加载映射表。
        """
        logger.info("正在执行模型自省...")
        
        def on_variables_received(raw_variable_list: Any) -> None:
            if not raw_variable_list:
                logger.warning("未能获取变量列表，自省失败。将使用空映射。")
                self.variable_map = {}
            else:
                if self.current_model_filename is None:
                    logger.warning("模型文件名未设置，无法使用缓存。")
                    self.variable_map = bound_params.analyze_variable_list(raw_variable_list)
                else:
                    cached_map = bound_params.get_bound_map(self.current_model_filename)
                    
                    if cached_map:
                        logger.info("使用缓存的变量映射。")
                        self.variable_map = cached_map
                    else:
                        logger.info("无缓存，正在进行语义分析...")
                        self.variable_map = bound_params.analyze_variable_list(raw_variable_list)
                        bound_params.update_cache(self.current_model_filename, self.variable_map)
            logger.info(f"自省完成，已绑定 {len(self.variable_map)} 个参数。")
            self._player_is_ready = True
            self.player_ready.emit(timelines)
            self._check_if_all_ready()

        self.get_variables(on_variables_received)

    def find_param_by_usage(self, usage_tag: str) -> dict[str, Any] | None:
        """根据特殊用途标签查找参数的完整信息。"""
        for param_info in self.variable_map.values():
            if usage_tag in param_info.get("special_usage", []):
                return param_info
        return None

    def cleanup(self):
        """
        释放 Controller 持有的所有资源。
        停止线程、停止音频流、卸载插件。
        """
        logger.info("EmoteController: 开始清理资源...")
        
        # 1. 停止口型同步
        self.stop_lip_sync()

        # 2. 停止插件加载线程（如果还在运行）
        if self._plugin_loader_thread and self._plugin_loader_thread.isRunning():
            logger.info("EmoteController: 等待插件线程退出...")
            self._plugin_loader_thread.quit()
            self._plugin_loader_thread.wait()
        
        # 3. 清理已加载的插件
        if self.plugins:
            self.plugins.cleanup_all()

        logger.info("EmoteController: 资源清理完毕。")
    
    # --- 槽函数 ---
    def _on_mouth_ratio_update(self, open_ratio: float) -> None:
        lip_sync_config = self.config['lip_sync']
        final_ratio: float = (open_ratio ** lip_sync_config['mouth_ratio_curve']) * lip_sync_config['mouth_ratio_oversaturation']
        final_ratio = max(0.0, min(final_ratio, 1.0))

        param_info = self.mouth_param_info
        param_range = param_info['range'][1] - param_info['range'][0]
        target_value = param_info['range'][0] + final_ratio * param_range
        
        self.set_variable(param_info['name'], target_value, duration_ms=lip_sync_config['set_variable_duration_ms'])

    def _reset_mouth_on_sync_finish(self):
        logger.info("同步结束，正在重置嘴型。")
        self._lip_sync_thread = None
        mouth_param = self.find_param_by_usage(bound_params.SpecialUsage.MOUTH_OPEN)
        if mouth_param:
            duration = self.config['lip_sync']['close_mouth_duration_ms']
            self.set_variable(mouth_param['name'], mouth_param['range'][0], duration_ms=duration)

    def _on_plugins_load_finished(self, instantiated_plugins: list[IEmotePlugin]) -> None:
        logger.info(f"后台插件实例化完成。共 {len(instantiated_plugins)} 个插件，现在在主线程中初始化和注册...")
        
        for plugin in instantiated_plugins:
            try:
                plugin.initialize(self)
                self.plugins.register(plugin)
            except Exception:
                error_msg = f"✗ 初始化或注册插件 '{getattr(plugin, 'get_name', lambda: 'Unknown')()}' 时出错。"
                logger.error(error_msg, exc_info=True)
                self._add_splash_log(error_msg, is_error=True)

        self.plugins_load_finished.emit()

        elapsed_s = (time.time() - self._splash_start_time)
        delay_ms = max(0, (self.config["splash"]["min_splash_duration_ms"] - elapsed_s*1000))
        logger.info(f"插件加载和初始化耗时 {elapsed_s:.2f} 秒。将延迟 {delay_ms:.0f}ms 以满足最小显示时长。")

        QTimer.singleShot(int(delay_ms), self._proceed_to_model_loading_step)

    @Slot(str)
    def load_model(self, path_or_name: str):
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
            path_or_name (str):
                模型文件的名称或路径 (例如 "chara.psb")。
        """
        self.current_model_filename = os.path.basename(path_or_name)
        
        model_url = resolve_resource_url(path_or_name, 'models')
        
        if not model_url:
            logger.error(f"无法加载模型，路径无效: {path_or_name}")
            return

        logger.info(f"加载模型 URL: {model_url}")
        safe_url = json.dumps(model_url)
        self.view_adapter.run_javascript(f"loadNewModel({safe_url});")

    @Slot()
    def save_bindings(self):
        """
        将当前在内存中的 `variable_map` (可能已被用户修改) 保存回缓存文件。

        这允许用户对参数绑定所做的更改被持久化，
        以便下次加载同一模型时自动应用。
        """
        if not self.current_model_filename:
            logger.error("没有已加载的模型，无法保存绑定。")
            return
        
        logger.info(f"正在将 '{self.current_model_filename}' 的绑定更新到缓存...")
        bound_params.update_cache(self.current_model_filename, self.variable_map)

    @Slot()
    def show(self):
        """
        显示模型（如果它被隐藏了）。
        """
        self._safe_run(f'{self.js_player_name}.hide = false;')

    @Slot()
    def hide(self):
        """
        隐藏模型，使其不可见。动画和物理效果仍在后台计算。
        """
        self._safe_run(f'{self.js_player_name}.hide = true;')

    @Slot(queue.Queue)
    def start_lip_sync(self, audio_queue: queue.Queue[Optional[FloatArray]]):
        """
        根据一个外部音频流队列启动口型同步，这玩意会自适应音量大小(大概吧？)。
        """
        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self.stop_lip_sync()

        mouth_param = self.find_param_by_usage(bound_params.SpecialUsage.MOUTH_OPEN)
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
        self._lip_sync_thread.debug_data_updated.connect(self.lip_sync_debug_data.emit)
        self._lip_sync_thread.finished.connect(self._reset_mouth_on_sync_finish)
        self._lip_sync_thread.start()


    @Slot(str)
    def start_lip_sync_from_file(self, filepath: str):
        """
        一个高级便利函数，用于从 .wav 文件启动口型同步。
        它在内部创建队列，并启动文件到流的转换器线程。
        """
        self.stop_lip_sync()
        self._streamer_stop_event.clear()
        
        audio_queue: queue.Queue[Optional[FloatArray]] = queue.Queue()
        self.start_lip_sync(audio_queue) 
        hz = self.config.get('file_streaming', {}).get('blocksize_hz', 30)
        stream_audio_file(filepath, audio_queue, self._streamer_stop_event, hz)

    @Slot()
    def stop_lip_sync(self):
        """顾名思义，停止口型同步。"""
        if self._streamer_stop_event:
            self._streamer_stop_event.set()

        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self._lip_sync_thread.stop()
    

    # --- 2. 变换与位置 (Transform) ---
    @Slot()
    def set_coord(self, x: int, y: int, duration_ms: int = 100):
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
        self._safe_run(f'{self.js_player_name}.setCoord({x}, {y}, {duration_ms});')

    @Slot(float,int)
    def set_scale(self, scale: float, duration_ms: int = 100):
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
        self._safe_run(f'{self.js_player_name}.setScale({scale}, {duration_ms});')

    @Slot(float,int)
    def set_rotation(self, angle_deg: float, duration_ms: int = 100):
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
        angle_rad = angle_deg * (3.14159 / 180.0) #何意味?
        self._safe_run(f'{self.js_player_name}.setRot({angle_rad}, {duration_ms});')

    @Slot(int)
    def auto_center(self, duration_ms: int = 300):
        """
        自动调整模型的缩放和位置，使其完美地居中于视图中。

        函数会自动查询模型的尺寸边界，计算最佳的缩放比例和坐标，
        以确保模型的任何一部分都不会被裁切，并带有一定的边距。

        参数:
            duration_ms (int, optional):
                完成居中动画所需的毫秒数。默认为 300ms。
        """
        self._safe_run(f'autoCenterPlayer({duration_ms});')

    # --- 3. 动画控制 (Animation) ---

    @Slot(str)
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
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.mainTimelineLabel = {safe_name};')

    def animation_reset(self, duration_ms: int|None =None):
        """
        重置模型的所有状态到初始默认值。

        这包括：
        - 停止所有正在播放的动画（主时间轴和差分）。
        - 重置模型的坐标、缩放和旋转。
        - 恢复默认的外观（颜色、透明度、灰度）。
        - 恢复默认的物理和风力效果。
        
        它提供了一种快速将模型恢复到“干净”状态的方法。
        """
        if duration_ms is None or duration_ms <0:
            duration_ms=int(self.config["animation"]["reset_duration_ms"])
        self.stop_all_timelines()
        self.set_coord(0, 0, duration_ms)
        self.set_scale(1.0, duration_ms)
        self.set_rotation(0, duration_ms)
        self.set_global_alpha(1.0, duration_ms)
        self.set_grayscale(0.0, duration_ms)
        self.set_vertex_color(self.config.get('animation', {}).get('reset_default_color', "#808080FF"), duration_ms)
        self.set_physics_scale(1.0, 1.0, 1.0)
        self.set_wind(0, 0, 0)
        init_anim_name=self.config["animation"]["initialization_name"]
        if init_anim_name is not None:
            logger.info(f"播放初始化动画 '{init_anim_name}'。")
            self.play(init_anim_name)
        logger.info("完成模型状态重置。")
    
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
        if not 1 <= slot <= 6: raise ValueError("Slot must be between 1 and 6.")
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.diffTimelineSlot{slot} = {safe_name};')

    def set_speed(self, speed_ratio: float=1.0):
        """
        设置所有动画的全局播放速度。

        参数:
            speed_ratio (float):
                播放速度的倍率。1.0 为正常速度，0.5 为慢放，2.0 为快进。

        示例:
            # 进入子弹时间！
            widget.set_speed(0.2)
        """
        self._safe_run(f'{self.js_player_name}.speed = {speed_ratio};')

    def stop_all_timelines(self):
        """
        停止所有正在播放的动画（包括主时间轴和所有差分动画）。
        """
        self._safe_run(f'{self.js_player_name}.stopTimeline();')

    # --- 4. 外观与特效 (Appearance & FX) ---

    def show_dialog(self, text: str, duration_ms: int = 5000, theme: str = 'default', type_speed: int = 50, anchor_marker: str = 'dialog_anchor'):
        """
        在角色头顶显示一个可更换主题的对话气泡。

        参数:
            text (str): 要显示的文本内容。
            duration_ms (int, optional): 对话框显示的时长（毫秒）。默认为 5000ms。
            theme (str, optional): 
                要使用的对话框主题。对应于 'web_frontend/dialogs/' 目录下的
                HTML文件名 (不含扩展名)。默认为 'default'。
            type_speed (int): 打字机速度（毫秒）。默认为 50ms/每字。
            anchor_marker (str): 对话框锚点位置标记。
        """
        theme_name = theme if theme.endswith('.html') else f"{theme}.html"
        theme_url = resolve_resource_url(theme_name, 'dialogs')
        
        if not theme_url and theme != 'default':
            logger.warning(f"主题 '{theme}' 未找到，回退到默认主题。")
            theme_url = resolve_resource_url("default.html", 'dialogs')

        safe_text = json.dumps(text)
        safe_theme = json.dumps(theme_url)
        safe_anchor = json.dumps(anchor_marker)
        y_offset = -20
        
        self._safe_run(f'showCharacterDialog({safe_text}, {duration_ms}, {safe_theme}, {y_offset}, {type_speed}, {safe_anchor});')

    def set_background_color(self, r: int, g: int, b: int, a: float):
        """
        设置渲染区域的背景颜色。

        这允许您将模型放置在任意颜色的背景之上，或者通过设置透明度
        为0，将其叠加在其他窗口组件之上（如果窗口本身支持透明）。

        注意：
        此函数仅控制 Web 视图内的背景色。
        如果您希望实现整窗口透明效果，
        请调用 `set_window_transparent(True)`。
        
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
        self._cached_bg_color = {"r": r, "g": g, "b": b, "a": a}
        self._safe_run(f"setBackgroundColor({r}, {g}, {b}, {a});")

    def set_window_transparent(self, enable: bool):
        """
        开启或关闭窗口的桌面透明（无边框）模式。

        开启后窗口变为无边框 (Frameless)。
        关闭后恢复之前的窗口边框和标题栏。
        """
        if enable:
            if not self._is_window_transparent:
                self.view_adapter.set_window_transparent(True)
                self._safe_run("setBackgroundColor(0,0,0,0);")
                
                self._is_window_transparent = True
                logger.info("窗口已切换为透明模式")
        else:
            if self._is_window_transparent:
                self.view_adapter.set_window_transparent(False)
                c = self._cached_bg_color
                self._safe_run(f"setBackgroundColor({c['r']}, {c['g']}, {c['b']}, {c['a']});")
                
                self._is_window_transparent = False
                logger.info("窗口已恢复普通模式")

    def set_background_image(self, path_or_name: str | None):
        """
        设置或移除视图的背景图片。

        参数:
            path_or_name (str | None):
                要显示的背景图片的文件名或路径 (例如 "scene_day.jpg")。
                如果传入 `None`，则会移除当前的背景图片，恢复为纯色背景。
        
        示例:
            # 设置背景
            widget.set_background_image("image.png")
            # 移除背景
            widget.set_background_image(None)
        """
        if path_or_name is None:
            self._safe_run("setBackgroundImage(null);")
            return

        img_url = resolve_resource_url(path_or_name, 'backgrounds')
        if img_url:
            safe_url = json.dumps(img_url)
            self._safe_run(f"setBackgroundImage({safe_url});")

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
        value = max(0.0, min(float(intensity), 1.0))
        self._safe_run(f'{self.js_player_name}.setGrayscale({value}, {duration_ms});')

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
        value = max(0.0, min(float(alpha), 1.0))
        self._safe_run(f'{self.js_player_name}.setGlobalAlpha({value}, {duration_ms});')

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
        safe_color = json.dumps(color_hex)
        self._safe_run(f'{self.js_player_name}.setVertexColor({safe_color}, {duration_ms});')

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
        self._safe_run(f'{self.js_player_name}.hairScale = {hair};')
        self._safe_run(f'{self.js_player_name}.partsScale = {parts};')
        self._safe_run(f'{self.js_player_name}.bustScale = {bust};')

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
        self._safe_run(f'{self.js_player_name}.windSpeed = {speed}; {self.js_player_name}.windPowMin = {power_min}; {self.js_player_name}.windPowMax = {power_max};')


    # --- 6. 数据查询 (Data Query) ---

    def get_main_timelines(self, callback: Callable[[Any], None]) -> None:
        """
        异步获取模型所有可用的【主时间轴动画】的名称列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[str]` 参数。
        """
        self._safe_query(f'{self.js_player_name}.mainTimelineLabels', callback)

    def get_diff_timelines(self, callback: Callable[[Any], None]) -> None:
        """
        异步获取模型所有可用的【差分（附加）动画】的名称列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[str]` 参数。
        """
        self._safe_query(f'{self.js_player_name}.diffTimelineLabels', callback)

    def get_variables(self, callback: Callable[[Any], None]) -> None:
        """
        异步获取模型所有可用的【底层变量】的详细信息列表。

        参数:
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `list[dict]` 参数。
        """
        self._safe_query(f'{self.js_player_name}.variableList', callback)

    def get_marker_position(self, marker_name: str, callback: Callable[[Any], None]) -> None:
        """
        异步获取模型上一个"标记点"的屏幕坐标。

        参数:
            marker_name (str): 在模型中定义的标记点名称。
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `dict` 或 `None` 参数。
        """
        safe_name = json.dumps(marker_name)
        self._safe_query(f'{self.js_player_name}.getMarkerPosition({safe_name})', callback)

    def get_available_special_usage_tags(self) -> list[str]:
        """
        获取所有预定义的“特殊用途”标签列表。
        
        此方法提供了一个由 SDK 规范化的标准标签列表，供上层 UI 
        (例如多选下拉框) 使用。这避免了在 UI 层硬编码这些值，
        实现了 UI 与数据模型的解耦。

        返回:
            list[str]: 所有可用特殊标签的字符串列表。
        """
        return [
            getattr(bound_params.SpecialUsage, attr) 
            for attr in dir(bound_params.SpecialUsage) 
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
        safe_name = json.dumps(name)
        self._safe_run(f'{self.js_player_name}.setVariable({safe_name}, {value}, {duration_ms});')

    def get_variable(self, name: str, callback: Callable[[Any], None]) -> None:
        """
        异步获取一个底层变量的当前值。

        参数:
            name (str): 变量的名称。
            callback (function):
                获取完成后要调用的函数。该函数会接收一个 `float` 参数。
        """
        safe_name = json.dumps(name)
        self._safe_query(f'{self.js_player_name}.getVariable({safe_name})', callback)

    # --- 8. 鼠标交互控制 ---
    def enable_drag(self, enable: bool):
        """
        开启或关闭模型的鼠标拖动功能。

        参数:
            enable (bool): True 为开启，False 为关闭。
        """
        js_bool = json.dumps(enable) 
        self.view_adapter.run_javascript(f"enablePlayerDrag({js_bool});")

    def enable_zoom(self, enable: bool):
        """
        开启或关闭模型的鼠标滚轮缩放功能。

        参数:
            enable (bool): True 为开启，False 为关闭。
        """
        js_bool = json.dumps(enable)
        self.view_adapter.run_javascript(f"enablePlayerZoom({js_bool});")

    def enable_gaze_control(self, enable: bool):
        """
        开启或关闭模型的视线跟随鼠标功能 (数据驱动版)。
        """
        head_lr_param = self.find_param_by_usage(bound_params.SpecialUsage.HEAD_LR)
        head_ud_param = self.find_param_by_usage(bound_params.SpecialUsage.HEAD_UD)
        eye_lr_param = self.find_param_by_usage(bound_params.SpecialUsage.EYE_LR)
        eye_ud_param = self.find_param_by_usage(bound_params.SpecialUsage.EYE_UD)

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
        self.view_adapter.run_javascript(js_code)