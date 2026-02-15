"""
EmoteWidget 核心控制器模块。

此模块实现了 SDK 的核心业务逻辑，遵循 MVVM (Model-View-ViewModel) 架构模式中的 ViewModel 层角色（在此项目中称为 Controller）。
它负责协调 Python 后端逻辑、Web 前端渲染器以及插件系统。

主要功能：
    - **状态管理**: 维护模型参数、变换状态、物理配置等。
    - **指令调度**: 将 Python 调用转换为 JavaScript 指令并发送给 WebEngine。
    - **异步通讯**: 处理从 Web 前端回传的数据（如变量查询、事件通知）。
    - **插件系统**: 管理插件的生命周期（加载、初始化、卸载）。
    - **音频驱动**: 处理口型同步 (LipSync) 的音频流分析。
"""

import os
import json
import time
import uuid
import queue
import threading
from typing import Callable, Any, Optional, Dict, List, Union, cast, Tuple
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
from emote_widget.utils.controller_proxy import SandboxProxy, PoisonPillProxy

import emote_widget.utils.bound_params as bound_params
from emote_widget.utils.audio_utils import stream_audio_file
from emote_widget.utils.paths import resolve_resource_url, add_resource_directory, scan_directory_for_resources, is_path_allowed
# Access private members to implement strict list_available_resources logic
from emote_widget.utils.paths import RESOURCE_SEARCH_PATHS, WEB_FRONTEND_ROOT

from emote_widget.utils.logger import emote_widget_logger as logger

class EmoteController(QObject):
    """
    [核心控制器] EmoteWidget 的大脑，负责业务逻辑编排与状态管理。
    
    设计理念 (Design Philosophy):
        本类作为 MVVM 架构中的 **ViewModel/Controller**，充当 Python 业务代码与 Web 渲染视图之间的桥梁。
        它不包含任何特定 GUI 框架（如 Qt/PySide）的绘图代码，而是通过 `IViewAdapter` 接口与视图层交互。
        这种解耦设计使得 SDK 可以轻松移植到不同的 GUI 框架（如 PySide6, PyQt5, 甚至未来的 CEF Python）。

    核心职责 (Core Responsibilities):
        1.  **指令缓冲与调度 (Command Dispatch)**: 解决 Python 初始化与 WebEngine 启动之间的时序竞争问题。
        2.  **异步查询回环 (Async Query Loop)**: 通过 UUID 机制实现跨语言（Python -> JS -> Python）的异步函数调用。
        3.  **状态同步 (State Sync)**: 维护模型的内部状态（如变量映射表 `variable_map`）。
        4.  **插件编排 (Plugin Orchestration)**: 管理插件的加载、生命周期挂钩。

    Attributes:
        view_adapter (IViewAdapter): 视图适配器实例，用于执行 JS 代码。
        config (Dict[str, Any]): 运行时配置字典。
        variable_map (BoundMap): 模型参数绑定映射表，用于解析语义化名称（如 "mouth_open"）到底层 ID。
    """
    
    player_ready = Signal(list)
    """
    Signal(list): 当模型成功加载并完成参数自省时发射。
    
    参数:
        timelines (list[str]): 该模型所有可用的主时间轴动画名称列表。
    """

    load_finished = Signal()
    """Signal(): 当底层 HTML 容器页面完全加载完毕，准备好接收模型加载指令时发射。"""

    plugins_load_finished = Signal()
    """Signal(): 当插件目录下的所有插件模块实例化完毕时发射。"""

    on_character_clicked = Signal()
    """Signal(): 当用户点击角色区域（非透明区域）时发射。"""

    on_character_hovered = Signal()
    """Signal(): 当用户鼠标悬停在角色上超过阈值（通常为1秒）时发射。"""

    lip_sync_debug_data = Signal(dict)
    """
    Signal(dict): 音频同步线程产生的实时调试数据。
    包含: RMS 振幅, 原始嘴型系数, 平滑后的嘴型系数等。
    """

    render_mask_visual_data = Signal(list, int, int)
    """
    Signal(list, int, int): 渲染遮罩调试数据，用于可视化当前点击穿透区域。
    参数: (rects, canvas_width, canvas_height)
    """

    def __init__(self, view_adapter: IViewAdapter, plugin_dir: Optional[str] = None, config_override: Optional[Dict[str, Any]] = None, bound_config_override: Optional[str] = None) -> None:
        """
        初始化控制器。

        Args:
            view_adapter (IViewAdapter): 具体的视图适配器实现（如 QtAdapter）。
            plugin_dir (Optional[str]): 插件目录路径。默认为当前工作目录下的 'plugins'。
            config_override (Optional[Dict[str, Any]]): 覆盖默认配置的字典。
            bound_config_override (Optional[str]): 参数绑定配置文件的路径覆盖。
        """
        super().__init__()

        self.view_adapter: IViewAdapter = view_adapter

        self.config: Dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
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
        
        # --- 关键机制: 指令队列 ---
        # 背景: WebEngine 的初始化通常比 Python 对象慢。
        # 解决: 在 _player_is_ready 为 False 期间，所有调用 JS 的指令都会被暂存到此队列。
        #       一旦 JS 端通过 player_ready 信号通知 Python，队列中的指令将按顺序执行。
        self._command_queue: List[str] = []

        # --- 关键机制: 异步查询挂号表 ---
        # 结构: { request_id (uuid): callback_function }
        # 作用: 存储发出的 JS 查询请求及其对应的回调函数。
        # 流程: 
        #   1. Python 生成 UUID，存入此表。
        #   2. 发送 JS 代码 `result = func(); py_api.receive(uuid, result)`。
        #   3. JS 执行并回调 Python。
        #   4. Python 根据 UUID 从此表中取出回调并执行。
        self._pending_queries: Dict[str, Callable[[Any], None]] = {}

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

        self._splash_start_time: float = 0.0

        # 启动加载状态位
        self._is_splash_dismissed: bool = False
        self._plugins_are_ready: bool = False
        self._player_is_ready: bool = False

        # 音频同步
        self._lip_sync_thread: Optional[StreamLipSyncThread] = None
        self._last_mouth_ratio: float = 0.0
        self._streamer_stop_event: threading.Event = threading.Event()

        self.current_model_filename: Optional[str] = None # 当前加载的模型文件名
        
        # --- 透明模式状态管理 ---
        self._is_window_transparent: bool = False
        self._is_click_through_enabled: bool = False
        self._cached_bg_color: Dict[str, Union[int, float]] = {"r": 255, "g": 255, "b": 255, "a": 1.0}

        self.variable_map: bound_params.BoundMap = bound_params.get_default_map()
        self.mouth_param_info: Optional[bound_params.BoundMapItem] = None

        # --- 设置通信桥接 ---
        # PythonApiBridge 是暴露给 JS 环境的 QObject
        self._bridge: PythonApiBridge = PythonApiBridge(self)
        
        # --- 连接内部信号 ---
        self._bridge.on_character_clicked_signal.connect(self.on_character_clicked)
        self._bridge.on_character_hovered_signal.connect(self.on_character_hovered)
        
        self._bridge.player_ready_signal.connect(self._on_player_ready_handler)
        self._bridge.query_result_signal.connect(self._handle_query_result)
        self._bridge.render_mask_updated_signal.connect(self._handle_render_mask_update)

        # 将桥接对象注入到 JS 环境中，对象名为 "py_api"
        self.view_adapter.register_python_bridge(self._bridge, "py_api")

    @Slot(str)
    def _handle_render_mask_update(self, mask_json: str) -> None:
        """
        处理来自 JS 的渲染掩码数据，并将其传递给 View Adapter 以应用窗口异形遮罩。
        
        内部逻辑:
            1. JS 端的 MaskSampler 算法计算出当前帧非透明区域的矩形集合。
            2. 通过 Bridge 发送 JSON 字符串到此函数。
            3. 此函数解析 JSON，提取 rects 列表。
            4. 将 rects 传递给 Qt 层的 setMask 或 setRegion，实现点击穿透。
        
        Args:
            mask_json (str): 包含 rects, width, height 的 JSON 字符串。
        """
        if not self._is_window_transparent or not self._is_click_through_enabled:
            return # 非透明或非穿透模式不需要应用 Mask
            
        try:
            payload: Any = json.loads(mask_json)
            
            rects: List[Any] = []
            width: int = 0
            height: int = 0

            # 兼容旧格式（纯列表）和新格式（对象）
            if isinstance(payload, list):
                rects = cast(List[Any], payload)
            elif isinstance(payload, dict):
                payload_dict = cast(Dict[str, Any], payload)
                rects = payload_dict.get('rects', [])
                width = int(payload_dict.get('width', 0))
                height = int(payload_dict.get('height', 0))
                
            # 发射用于 MaskMonitorWidget 的可视化数据
            self.render_mask_visual_data.emit(rects, width, height)
            
            if hasattr(self.view_adapter, 'set_render_mask'):
                self.view_adapter.set_render_mask(rects)
                
        except Exception as e:
            logger.error(f"处理渲染掩码失败: {e}")

    @Slot(str,str)
    def _handle_query_result(self, request_id: str, result_json: Optional[str]) -> None:
        """
        [内部回调] 处理 JS 异步查询的返回结果。

        这是异步查询回环的终点。
        
        逻辑:
            1. 检查 request_id 是否在 _pending_queries 挂号表中。
            2. 如果存在，取出对应的回调函数 (pop，确保一次性使用)。
            3. 解析 JSON 结果并执行回调。
        
        Args:
            request_id (str): 原始请求的 UUID。
            result_json (str): JS 执行结果的 JSON 字符串。如果是 undefined 则为 None。
        """
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

    def _safe_run(self, js_code: str) -> None:
        """
        安全执行无返回值的 JS 代码。

        特性:
            - **自动排队**: 如果 WebEngine 未就绪，指令会自动进入 `_command_queue` 等待。
            - **异常捕获**: 会在 JS 端包裹 try-catch，将错误传回 Python 日志。

        Args:
            js_code (str): 要执行的 JavaScript 代码片段。
        """
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

    def _safe_query(self, expression: str, callback: Optional[Callable[[Any], None]]) -> None:
        """
        安全执行有返回值的 JS 查询（异步回环模式）。

        不再使用 adapter 原生的同步 callback，而是构建一个异步闭环：
        Python -> JS -> (Bridge) -> Python -> Callback。

        流程:
            1. 生成 UUID `request_id`。
            2. 将 `callback` 存入 `_pending_queries[request_id]`。
            3. 构造 JS 代码，执行 `expression`，并将结果和 `request_id` 传回 `py_api.receive_query_result`。
            4. `receive_query_result` 触发信号，调用 `_handle_query_result` 完成闭环。

        Args:
            expression (str): 返回值的 JS 表达式 (例如 "player.scale")。
            callback (Callable): 接收结果的回调函数。
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
        # 注意: undefined 转换为 null，否则 JSON.stringify 会丢失
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
    
    def on_page_load_finished(self, ok: bool) -> None:
        """WebEngine 页面加载完成的回调。初始化启动画面流程。"""
        logger.debug(f"--> _on_page_load_finished Signal Received. Status OK: {ok}")
        if ok:

            self.load_finished.emit()
            logger.info("内部页面加载成功，初始化启动画面并启动后台插件加载...")
            self._splash_start_time = time.time()
            
            self._update_splash_version()
            self._update_splash_main_progress(0.1, f"EmoteWidget v{__version__} 初始化...")

            # 初始化渲染画质
            initial_quality = self.config.get('render', {}).get('quality', 'auto')
            self.set_render_quality(initial_quality)

            self._init_default_theme()

            self._update_splash_main_progress(0.2, "正在扫描插件目录...")

            self._plugin_loader_worker.scan_for_plugin_modules()

            self._plugin_loader_thread.start()
            
            self._update_splash_main_progress(0.3, "后台插件加载已启动...")
        else:
            logger.critical("内部页面加载失败！请检查 `pyside_webview.html` 路径。")

    def _on_player_ready_handler(self, timelines: list[str]) -> None:
        """
        [内部槽] 当 JS 端模型加载完成时触发。
        
        职责:
            1. 标记 `_player_is_ready = True`。
            2. 冲刷并执行 `_command_queue` 中积压的指令。
            3. 开始模型自省（Introspection）流程。
        """
        logger.info(f"模型 '{self.current_model_filename}' JS对象已就绪。")
        
        self._player_is_ready = True

        if self._command_queue:
            logger.info(f"正在执行 {len(self._command_queue)} 条缓存指令...")
            for js_code in self._command_queue:
                # 这里的指令在入队前未包裹 try-catch，因此再次包裹
                full_script = f"try {{ {js_code} }} catch(e) {{ console.error(e); }}"
                self.view_adapter.run_javascript(full_script)
            self._command_queue.clear()

        self._update_splash_main_progress(0.6, f"模型 '{self.current_model_filename}' 加载中,正在分析变量...")

        self._perform_introspection(timelines)

    # --- 辅助方法 ---

    def _init_default_theme(self) -> None:
        """预加载默认对话框主题，防止后续使用时因加载延迟导致报错。"""
        default_theme_url = resolve_resource_url("default.html", "dialogs")
        if default_theme_url:
            safe_url = json.dumps(default_theme_url)
            logger.info("预加载默认对话框主题...")
            self._safe_run(f"loadDialogTheme({safe_url});")
        else:
            logger.warning("默认对话框主题 default.html 未找到，可能导致对话框功能异常。")

    def _check_if_all_ready(self) -> None:
        """检查所有并行加载任务（插件、模型）是否都已完成，若是则关闭启动画面。"""
        if self._plugins_are_ready and self._player_is_ready:
            logger.info("所有加载任务均已完成，准备关闭启动画面。")
            self._update_splash_main_progress(1.0, "所有加载步骤完成！")
            self._dismiss_splash_screen()

    def _update_splash_main_progress(self, progress: float, text: str) -> None:
        safe_text = json.dumps(text)
        self.view_adapter.run_javascript(f"SplashScreenAPI.updateMainProgress({progress}, {safe_text});")

    def _update_splash_plugin_progress(self, progress: float, text: str) -> None:
        safe_text = json.dumps(text)
        self.view_adapter.run_javascript(f"SplashScreenAPI.updatePluginProgress({progress}, {safe_text});")

    def _add_splash_log(self, message: str, is_error: bool = False) -> None:
        safe_message = json.dumps(message)
        js_bool = "true" if is_error else "false"
        self.view_adapter.run_javascript(f"SplashScreenAPI.addLog({safe_message}, {js_bool});")
    
    def _update_splash_version(self) -> None:
        safe_version = json.dumps(__version__)
        self.view_adapter.run_javascript(f"SplashScreenAPI.setVersion({safe_version});")

    def _dismiss_splash_screen(self) -> None:
        if self._is_splash_dismissed: return
        self._is_splash_dismissed = True
        logger.info("所有加载步骤完成，正在隐藏启动画面...")
        self.view_adapter.run_javascript("setTimeout(() => { SplashScreenAPI.dismiss(); }, 500);")

    def _proceed_to_model_loading_step(self) -> None:
        """在插件加载完成且满足最小启动画面时长后，推进状态机。"""
        logger.info("插件流程已就绪。")
        self._update_splash_main_progress(0.8, "插件加载完毕。正在等待模型...")
        self._update_splash_plugin_progress(1.0, "完成")
        
        self._plugins_are_ready = True
        self._check_if_all_ready()

    def _perform_introspection(self, timelines: list[str]) -> None:
        """
        执行模型自省流程。
        
        获取模型的所有底层变量，并建立语义化的映射关系（BoundMap）。
        优先尝试从缓存加载映射，如果失败则进行实时分析。
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

    def find_param_by_usage(self, usage_tag: str) -> Optional[bound_params.BoundMapItem]:
        """
        根据特殊用途标签查找参数的完整信息。
        
        Args:
            usage_tag (str): 用途标签，建议使用 bound_params.SpecialUsage 枚举。
            
        Returns:
            Optional[BoundMapItem]: 包含参数名、范围等信息的字典，未找到返回 None。
        """
        for param_info in self.variable_map.values():
            special_usage = param_info.get("special_usage", [])
            if isinstance(special_usage, list) and usage_tag in special_usage:
                return param_info
        return None

    def cleanup(self) -> None:
        """
        [生命周期] 释放 Controller 持有的所有资源。
        
        操作:
            1. 停止 LipSync 线程。
            2. 停止并等待插件加载线程。
            3. 调用所有已加载插件的 cleanup 方法。
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
        """LipSync 线程的回调，根据计算出的张开度驱动模型嘴部参数。"""
        if not self.mouth_param_info:
            return

        lip_sync_config = self.config['lip_sync']
        curve = float(lip_sync_config['mouth_ratio_curve'])
        oversaturation = float(lip_sync_config['mouth_ratio_oversaturation'])

        # 应用非线性曲线和过饱和增强
        final_ratio: float = (open_ratio ** curve) * oversaturation
        final_ratio = max(0.0, min(final_ratio, 1.0))

        param_info = self.mouth_param_info
        param_range = cast(Tuple[float, float], param_info['range'])
        range_span = param_range[1] - param_range[0]
        target_value = param_range[0] + final_ratio * range_span
        
        duration = int(lip_sync_config['set_variable_duration_ms'])
        param_name = cast(str, param_info['name'])
        self.set_variable(param_name, target_value, duration_ms=duration)

    def _reset_mouth_on_sync_finish(self) -> None:
        """LipSync 结束后复位嘴型。"""
        logger.info("同步结束，正在重置嘴型。")
        self._lip_sync_thread = None
        mouth_param = self.find_param_by_usage(bound_params.SpecialUsage.MOUTH_OPEN)
        if mouth_param:
            duration = int(self.config['lip_sync']['close_mouth_duration_ms'])
            name = cast(str, mouth_param['name'])
            rng = cast(Tuple[float, float], mouth_param['range'])
            self.set_variable(name, rng[0], duration_ms=duration)

    def _on_plugins_load_finished(self, instantiated_plugins: list[IEmotePlugin]) -> None:
        """插件后台加载完成后的主线程回调，执行初始化和注册。"""
        logger.info(f"后台插件实例化完成。共 {len(instantiated_plugins)} 个插件，现在在主线程中初始化和注册...")
        
        for plugin in instantiated_plugins:
            try:
                # 1. 创建沙盒代理
                sandbox = SandboxProxy(self)
                plugin.controller = cast("EmoteController", sandbox) # Type hint hack
                
                # 2. 尝试初始化 (此时操作被拦截进队列)
                plugin.initialize()
                
                # 3. 验证成功：提交事务并替换为真实控制器
                sandbox.commit()
                # 替换回真实的控制器（或常规的安全代理），解除沙盒限制
                # 这里我们直接给 self，或者如果需要保护私有成员，也可以给 ControllerProxy(self)
                # 为了保持一致性，且之前的 plugin.controller 可能是 Proxy，这里给 self 最直接。
                # 但根据 Prompt 要求 "keep access restriction to private members"，
                # 我们可能应该给 ControllerProxy(self) 或者就给 self 如果插件被认为是受信的。
                # 任务说明 C.3 "将 plugin.controller 替换为真实的控制器实例"。
                plugin.controller = self 
                
                self.plugins.register(plugin)
                
            except Exception:
                plugin_name = getattr(plugin, 'get_name', lambda: 'Unknown')()
                error_msg = f"✗ 初始化插件 '{plugin_name}' 失败，已隔离。"
                logger.error(error_msg, exc_info=True)
                self._add_splash_log(error_msg, is_error=True)
                
                # 4. 验证失败：隔离插件
                plugin.controller = cast("EmoteController", PoisonPillProxy(plugin_name))

        self.plugins_load_finished.emit()

        elapsed_s = (time.time() - self._splash_start_time)
        splash_min_ms = float(self.config["splash"]["min_splash_duration_ms"])
        delay_ms = max(0.0, (splash_min_ms - elapsed_s*1000))
        logger.info(f"插件加载和初始化耗时 {elapsed_s:.2f} 秒。将延迟 {delay_ms:.0f}ms 以满足最小显示时长。")

        QTimer.singleShot(int(delay_ms), self._proceed_to_model_loading_step)

    @Slot(str)
    def load_model(self, path_or_name: str) -> None:
        """
        加载指定路径的模型。

        此方法是与模型交互的起点。它会：
        1. 调用 `BoundParams.get_bound_map` 尝试从缓存加载变量映射。
        2. 发送 JS 指令加载 `.psb` 文件。
        3. 加载完成后触发 `player_ready`。

        Args:
            path_or_name (str): 模型文件的名称或路径 (例如 "chara.psb")。
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
    def save_bindings(self) -> None:
        """
        将当前内存中的变量映射表 (`variable_map`) 保存到磁盘缓存。
        
        用于持久化用户在运行时对参数绑定的修改。
        """
        if not self.current_model_filename:
            logger.error("没有已加载的模型，无法保存绑定。")
            return
        
        logger.info(f"正在将 '{self.current_model_filename}' 的绑定更新到缓存...")
        bound_params.update_cache(self.current_model_filename, self.variable_map)

    @Slot()
    def show(self) -> None:
        """显示模型（如果被隐藏）。"""
        self._safe_run(f'{self.js_player_name}.hide = false;')

    @Slot()
    def hide(self) -> None:
        """隐藏模型，使其不可见。动画和物理效果仍在后台计算。"""
        self._safe_run(f'{self.js_player_name}.hide = true;')

    @Slot(queue.Queue)
    def start_lip_sync(self, audio_queue: queue.Queue[Optional[FloatArray]]) -> None:
        """
        启动基于音频流的口型同步。
        
        Args:
            audio_queue (queue.Queue): 包含音频数据块 (FloatArray) 的队列。
                                     放入 None 可作为结束信号。
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
            mean_decay_time=float(lip_sync_config['mean_decay_time_s']),
            peak_decay_time=float(lip_sync_config['peak_decay_time_s']),
            update_fps=int(lip_sync_config['update_fps']),
            activation_ratio=float(lip_sync_config['activation_ratio'])
        )
        self._lip_sync_thread.mouth_open_ratio_updated.connect(self._on_mouth_ratio_update)
        self._lip_sync_thread.debug_data_updated.connect(self.lip_sync_debug_data.emit)
        self._lip_sync_thread.finished.connect(self._reset_mouth_on_sync_finish)
        self._lip_sync_thread.start()


    @Slot(str)
    def start_lip_sync_from_file(self, filepath: str) -> None:
        """
        从音频文件启动口型同步（便捷方法）。
        
        内部会启动一个辅助线程将文件读取为流。
        
        Args:
            filepath (str): 音频文件路径 (.wav, .mp3 等)。
        """
        self.stop_lip_sync()
        self._streamer_stop_event.clear()
        
        audio_queue: queue.Queue[Optional[FloatArray]] = queue.Queue()
        self.start_lip_sync(audio_queue) 
        hz = int(self.config.get('file_streaming', {}).get('blocksize_hz', 30))
        stream_audio_file(filepath, audio_queue, self._streamer_stop_event, hz)

    @Slot()
    def stop_lip_sync(self) -> None:
        """停止当前正在进行的口型同步。"""
        if self._streamer_stop_event:
            self._streamer_stop_event.set()

        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self._lip_sync_thread.stop()
    

    # --- 2. 变换与位置 (Transform) ---
    @Slot()
    @Slot(int, int) 
    @Slot(int, int, int)
    def set_coord(self, x: int, y: int, duration_ms: int = 100) -> None:
        """
        设置模型在画布上的坐标。

        坐标系原点(0, 0)位于画布中心。
        
        Args:
            x (int): 横坐标。正值向右。
            y (int): 纵坐标。正值向下。
            duration_ms (int, optional): 动画时长。默认为 100ms。
        """
        self._safe_run(f'{self.js_player_name}.setCoord({x}, {y}, {duration_ms});')

    @Slot(float,int)
    def set_scale(self, scale: float, duration_ms: int = 100) -> None:
        """
        设置模型的缩放比例。

        Args:
            scale (float): 缩放倍数。1.0 为原始大小。
            duration_ms (int, optional): 动画时长。
        """
        self._safe_run(f'{self.js_player_name}.setScale({scale}, {duration_ms});')

    @Slot(float,int)
    def set_rotation(self, angle_deg: float, duration_ms: int = 100) -> None:
        """
        设置模型的旋转角度。

        Args:
            angle_deg (float): 角度(度)。正值为顺时针。
            duration_ms (int, optional): 动画时长。
        """
        angle_rad = angle_deg * (3.14159 / 180.0)
        self._safe_run(f'{self.js_player_name}.setRot({angle_rad}, {duration_ms});')

    @Slot(int)
    def auto_center(self, duration_ms: int = 300) -> None:
        """
        自动缩放和平移模型以适应视图大小。

        Args:
            duration_ms (int, optional): 动画时长。
        """
        self._safe_run(f'autoCenterPlayer({duration_ms});')

    # --- 3. 动画控制 (Animation) ---

    @Slot(str)
    def play(self, timeline_name: str) -> None:
        """
        播放主时间轴动画。
        
        Args:
            timeline_name (str): 动画名称。
        """
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.mainTimelineLabel = {safe_name};')

    @Slot(int)
    def animation_reset(self, duration_ms: Optional[int] = None) -> None:
        """
        重置模型到初始状态。

        停止动画，重置变换、颜色、物理效果等。
        
        Args:
            duration_ms (int, optional): 重置动画的时长。
        """
        if duration_ms is None or duration_ms < 0:
            duration_ms = int(self.config["animation"]["reset_duration_ms"])
        
        self.stop_all_timelines()
        self.set_coord(0, 0, duration_ms)
        self.set_scale(1.0, duration_ms)
        self.set_rotation(0.0, duration_ms)
        self.set_global_alpha(1.0, duration_ms)
        self.set_grayscale(0.0, duration_ms)
        self.set_vertex_color(self.config.get('animation', {}).get('reset_default_color', "#808080FF"), duration_ms)
        self.set_physics_scale(1.0, 1.0, 1.0)
        self.set_wind(0.0, 0.0, 0.0)
        
        init_anim_name = self.config["animation"]["initialization_name"]
        if init_anim_name is not None:
            logger.info(f"播放初始化动画 '{init_anim_name}'。")
            self.play(init_anim_name)
        logger.info("完成模型状态重置。")
    
    @Slot(str)
    def set_diff_timeline(self, slot: int, timeline_name: str) -> None:
        """
        设置差分（附加）动画。

        Args:
            slot (int): 槽位 (1-6)。
            timeline_name (str): 动画名称。空字符串表示清空槽位。
        """
        if not 1 <= slot <= 6: raise ValueError("Slot must be between 1 and 6.")
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.diffTimelineSlot{slot} = {safe_name};')

    @Slot(float)
    @Slot(float)
    def set_speed(self, speed_ratio: float=1.0) -> None:
        """
        设置全局播放速度。

        Args:
            speed_ratio (float): 速度倍率。1.0 为正常。
        """
        self._safe_run(f'{self.js_player_name}.speed = {speed_ratio};')

    @Slot()
    @Slot()
    def stop_all_timelines(self) -> None:
        """停止所有正在播放的动画（主时间轴和差分）。"""
        self._safe_run(f'{self.js_player_name}.stopTimeline();')

    # --- 4. 外观与特效 (Appearance & FX) ---

    @Slot(str, int, str, int, str)
    def show_dialog(self, text: str, duration_ms: int = 5000, theme: str = 'default', type_speed: int = 50, anchor_marker: str = 'dialog_anchor') -> None:
        """
        在角色旁显示气泡对话框。

        Args:
            text (str): 文本内容。
            duration_ms (int): 显示时长。
            theme (str): 主题名称 (无需 .html 后缀)。
            type_speed (int): 打字机速度 (ms/char)。
            anchor_marker (str): 模型上的锚点名称。
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

    @Slot(int, int, int, float)
    def set_background_color(self, r: int, g: int, b: int, a: float) -> None:
        """
        设置 Web 视图的背景颜色。

        Args:
            r (int): 红 (0-255)
            g (int): 绿 (0-255)
            b (int): 蓝 (0-255)
            a (float): 透明度 (0.0-1.0)
        """
        self._cached_bg_color = {"r": r, "g": g, "b": b, "a": a}
        self._safe_run(f"setBackgroundColor({r}, {g}, {b}, {a});")

    @Slot(int, int)
    def set_mask_grid_size(self, width: int, height: int) -> None:
        """
        设置遮罩采样的网格分辨率。
        
        Args:
            width (int): 网格列数。
            height (int): 网格行数。
        """
        self._safe_run(f"if(typeof setMaskGridSize === 'function') setMaskGridSize({width}, {height});")

    @Slot(bool, bool)
    def set_window_transparent(self, enable: bool, click_through: bool = False) -> None:
        """
        切换窗口的透明（无边框）模式。

        Args:
            enable (bool): 是否开启。
            click_through (bool): 是否开启点击穿透（需要 JS 配合进行 Alpha 采样）。
        """
        self._is_click_through_enabled = click_through
        
        # 通知 JS 开启/关闭采样
        js_sampling = "true" if (enable and click_through) else "false"
        self._safe_run(f"if(typeof setClickThroughMode === 'function') setClickThroughMode({js_sampling});")

        if enable:
            if not self._is_window_transparent:
                self.view_adapter.set_window_transparent(True)
                self._safe_run("setBackgroundColor(0,0,0,0);")
                
                self._is_window_transparent = True
                logger.info(f"窗口已切换为透明模式 (穿透={click_through})")
            
            # 如果已经开启透明，但改变了穿透状态
            elif self._is_window_transparent:
                 if not click_through:
                     if hasattr(self.view_adapter, 'set_render_mask'):
                         self.view_adapter.set_render_mask([]) 
        else:
            if self._is_window_transparent:
                self.view_adapter.set_window_transparent(False)
                c = self._cached_bg_color
                self._safe_run(f"setBackgroundColor({c['r']}, {c['g']}, {c['b']}, {c['a']});")
                
                if hasattr(self.view_adapter, 'set_render_mask'):
                     self.view_adapter.set_render_mask([]) # 清除遮罩

                self._is_window_transparent = False
                logger.info("窗口已恢复普通模式")

    @Slot("QVariant")
    def set_background_image(self, path_or_name: Optional[str]) -> None:
        """
        设置背景图片。

        Args:
            path_or_name (Optional[str]): 图片路径或名称。None 表示移除。
        """
        if not path_or_name: # Handle None or empty string
            self._safe_run("setBackgroundImage(null);")
            return

        img_url = resolve_resource_url(path_or_name, 'backgrounds')
        if img_url:
            safe_url = json.dumps(img_url)
            self._safe_run(f"setBackgroundImage({safe_url});")

    @Slot(float, int)
    def set_grayscale(self, intensity: float, duration_ms: int = 0) -> None:
        """
        设置灰度效果。

        Args:
            intensity (float): 强度 (0.0 - 1.0)。
            duration_ms (int): 过渡时长。
        """
        value = max(0.0, min(float(intensity), 1.0))
        self._safe_run(f'{self.js_player_name}.setGrayscale({value}, {duration_ms});')

    @Slot(float, int)
    def set_global_alpha(self, alpha: float, duration_ms: int = 0) -> None:
        """
        设置全局透明度。

        Args:
            alpha (float): 透明度 (0.0 - 1.0)。
            duration_ms (int): 过渡时长。
        """
        value = max(0.0, min(float(alpha), 1.0))
        self._safe_run(f'{self.js_player_name}.setGlobalAlpha({value}, {duration_ms});')

    @Slot(str, int)
    def set_vertex_color(self, color_hex: str, duration_ms: int = 0) -> None:
        """
        设置顶点叠加颜色。

        Args:
            color_hex (str): Hex 颜色码 (例如 "#FF0000")。
            duration_ms (int): 过渡时长。
        """
        safe_color = json.dumps(color_hex)
        self._safe_run(f'{self.js_player_name}.setVertexColor({safe_color}, {duration_ms});')

    # --- 5. 物理与环境 (Physics & Environment) ---

    @Slot(float, float, float)
    def set_physics_scale(self, hair: float = 1.0, parts: float = 1.0, bust: float = 1.0) -> None:
        """
        设置物理摆动幅度。

        Args:
            hair (float): 头发幅度。
            parts (float): 配件幅度。
            bust (float): 胸部幅度。
        """
        self._safe_run(f'{self.js_player_name}.hairScale = {hair};')
        self._safe_run(f'{self.js_player_name}.partsScale = {parts};')
        self._safe_run(f'{self.js_player_name}.bustScale = {bust};')

    @Slot(float, float, float)
    def set_wind(self, speed: float, power_min: float = 0.0, power_max: float = 2.0) -> None:
        """
        设置风力参数。

        Args:
            speed (float): 风速。
            power_min (float): 最小强度。
            power_max (float): 最大强度。
        """
        self._safe_run(f'{self.js_player_name}.windSpeed = {speed}; {self.js_player_name}.windPowMin = {power_min}; {self.js_player_name}.windPowMax = {power_max};')

    @Slot(str)
    def set_render_quality(self, mode: str) -> None:
        """
        设置渲染质量模式。

        Args:
            mode (str): "low", "high", "ultra", "auto"。
        """
        valid_modes = ["low", "high", "ultra", "auto"]
        if mode not in valid_modes:
            logger.warning(f"set_render_quality: 未知的模式 '{mode}'，将回退到 'auto'。")
            mode = "auto"
        
        self.config.setdefault('render', {})['quality'] = mode
        safe_mode = json.dumps(mode)
        logger.info(f"设置渲染画质为: {mode}")
        self._safe_run(f"setRenderQuality({safe_mode});")


    # --- 6. 数据查询 (Data Query) ---

    @Slot("QVariant")
    def get_main_timelines(self, callback: Callable[[Any], None]) -> None:
        """异步获取所有主时间轴名称。"""
        self._safe_query(f'{self.js_player_name}.mainTimelineLabels', callback)

    @Slot("QVariant")
    def get_diff_timelines(self, callback: Callable[[Any], None]) -> None:
        """异步获取所有差分时间轴名称。"""
        self._safe_query(f'{self.js_player_name}.diffTimelineLabels', callback)

    @Slot("QVariant")
    def get_variables(self, callback: Callable[[Any], None]) -> None:
        """异步获取模型变量列表。"""
        self._safe_query(f'{self.js_player_name}.variableList', callback)

    @Slot(str,"QVariant")
    def get_marker_position(self, marker_name: str, callback: Callable[[Any], None]) -> None:
        """异步获取模型标记点位置。"""
        safe_name = json.dumps(marker_name)
        self._safe_query(f'{self.js_player_name}.getMarkerPosition({safe_name})', callback)
    
    @Slot()
    def get_available_special_usage_tags(self) -> list[str]:
        """获取所有可用的特殊用途标签列表。"""
        return [
            getattr(bound_params.SpecialUsage, attr) 
            for attr in dir(bound_params.SpecialUsage) 
            if not attr.startswith('__')
        ]

    @Slot(str, str)
    def add_resource_path(self, category: str, path: str) -> None:
        """
        注册额外的资源搜索路径。
        
        Args:
            category (str): 资源类别 ('models', 'backgrounds', 'dialogs')
            path (str): 文件夹的绝对路径或相对路径
        """
        add_resource_directory(category, path)

    @Slot(result=dict)
    def list_available_resources(self) -> Dict[str, Dict[str, str]]:
        """
        扫描并列出所有可用资源。

        Returns:
            Dict: 格式为 { 'models': {name: path}, ... }
        """
        resources: Dict[str, Dict[str, str]] = {
            "models": {},
            "backgrounds": {},
            "dialogs": {}
        }
        
        category_extensions: Dict[str, Tuple[str, ...]] = {
            "models": (".psb",),
            "backgrounds": (".png", ".jpg", ".jpeg", ".gif"),
            "dialogs": (".html",)
        }
        
        for cat, exts in category_extensions.items():
            # 1. 扫描默认目录
            default_path = os.path.join(WEB_FRONTEND_ROOT, cat)
            scanned = scan_directory_for_resources(default_path, exts, recursive=True)
            
            for name, path in scanned.items():
                if is_path_allowed(path):
                    resources[cat][name] = path
            
            # 2. 扫描自定义目录 (从旧到新, 后面的覆盖前面的)
            if cat in RESOURCE_SEARCH_PATHS:
                for path in reversed(RESOURCE_SEARCH_PATHS[cat]):
                    # 递归扫描自定义目录，以支持 modellist 这种包含子文件夹的结构
                    custom_scanned = scan_directory_for_resources(path, exts, recursive=True)
                    for name, abs_path in custom_scanned.items():
                         # [Security] 二次校验：确保路径在白名单内
                        if is_path_allowed(abs_path):
                            resources[cat][name] = abs_path

        return resources

    # --- 7. 底层参数控制 (Advanced) ---

    @Slot(str, float, int)
    def set_variable(self, name: str, value: float, duration_ms: int = 0) -> None:
        """
        直接设置底层变量的值。

        Args:
            name (str): 变量名。
            value (float): 目标值。
            duration_ms (int): 过渡时长。
        """
        safe_name = json.dumps(name)
        self._safe_run(f'{self.js_player_name}.setVariable({safe_name}, {value}, {duration_ms});')

    def get_variable(self, name: str, callback: Callable[[Any], None]) -> None:
        """
        异步获取底层变量的当前值。

        Args:
            name (str): 变量名。
            callback (function): 回调函数。
        """
        safe_name = json.dumps(name)
        self._safe_query(f'{self.js_player_name}.getVariable({safe_name})', callback)

    # --- 8. 鼠标交互控制 ---
    @Slot(bool)
    def enable_drag(self, enable: bool) -> None:
        """开启或关闭模型的鼠标拖动功能。"""
        js_bool = json.dumps(enable) 
        self.view_adapter.run_javascript(f"enablePlayerDrag({js_bool});")

    @Slot(bool)
    def enable_zoom(self, enable: bool) -> None:
        """开启或关闭模型的鼠标滚轮缩放功能。"""
        js_bool = json.dumps(enable)
        self.view_adapter.run_javascript(f"enablePlayerZoom({js_bool});")

    @Slot(bool)
    def enable_gaze_control(self, enable: bool) -> None:
        """
        开启或关闭数据驱动的视线跟随功能。
        
        该功能会自动寻找标记为 HEAD_LR, HEAD_UD, EYE_LR, EYE_UD 的参数并进行驱动。
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
