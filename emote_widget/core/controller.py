import os
import json
import time
import queue
import threading
from PySide6.QtCore import QObject, Slot, Signal, QUrl, QThread, QTimer

from emote_widget.default_config.default_constants import DEFAULT_CONFIG, __version__

from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.core.lipsync_thread import StreamLipSyncThread
from emote_widget.core.plugin_system import PluginAccessor, PluginLoaderWorker
from emote_widget.core.python_api_bridge import _PythonApiBridge

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

    def __init__(self, view_adapter: IViewAdapter, plugin_dir=None, config_override=None):
        """初始化 EmoteWidgetController 组件。"""

        super().__init__()

        self.view_adapter=view_adapter

        self.config = json.loads(json.dumps(DEFAULT_CONFIG))
        # 如果用户提供了覆盖配置，则进行合并
        if config_override:
            for key, value in config_override.items():
                if key in self.config and isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value

        self.js_player_name = "emotePlayer" 
        self._command_queue = []          # 指令队列

        # 插件系统
        if plugin_dir:
             self.plugin_dir = plugin_dir
        else:
             self.plugin_dir = os.path.join(os.getcwd(), 'plugins')

        self.plugins=PluginAccessor()
        self._plugin_loader_thread = QThread(self)
        self._plugin_loader_worker = PluginLoaderWorker(self.plugin_dir)
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
        self._cached_bg_color = {"r": 255, "g": 255, "b": 255, "a": 1.0}

        self.variable_map = bound_params.get_default_map()

        # --- 设置通信 ---
        self._bridge = _PythonApiBridge(self)
        
        # --- 连接内部信号 ---
        self._bridge.player_ready_signal.connect(self._on_player_ready_handler)

    def _safe_run(self, js_code: str):
        """执行无返回值的 JS 代码 (支持队列缓存)"""
        # [关键修改] 如果模型还没准备好，先存入队列
        if not self._player_is_ready:
            self._command_queue.append(js_code)
            logger.debug(f"模型未就绪，指令已缓存: {js_code[:50]}...")
            return

        # 包装 try-catch，并通过 adapter 执行
        full_script = f"""
        (() => {{
            try {{ {js_code} }} catch(e) {{
                if(window.py_api) window.py_api.on_js_error(e.message, e.stack);
            }}
        }})();
        """
        self.view_adapter.run_javascript(full_script)

    def _safe_query(self, expression: str, callback):
        """执行有返回值的 JS 查询 (异步回调，带空值检查)"""
        if not self._player_is_ready:
            logger.warning("模型未就绪，无法执行查询。")
            if callback and callable(callback): 
                callback(None)
            return

        if callback is None or not callable(callback):
            logger.warning(f"查询 '{expression}' 未提供有效的 callback，已跳过。")
            return

        code = f"""
        (() => {{
            try {{
                const res = {expression};
                return JSON.stringify(res);
            }} catch(e) {{
                return null;
            }}
        }})()
        """

        def _json_wrapper(result):
            if not callback: return

            if result is None:
                callback(None)
                return
            try:
                data = json.loads(result)
                callback(data)
            except Exception as e:
                logger.error(f"解析 JS 返回数据失败: {e}")
                callback(None)

        self.view_adapter.run_javascript_with_callback(code, _json_wrapper)


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

    def _perform_introspection(self, timelines):
        """
        获取变量列表，生成或加载映射表。
        """
        logger.info("正在执行模型自省...")
        
        def on_variables_received(raw_variable_list):
            if not raw_variable_list:
                logger.warning("未能获取变量列表，自省失败。将使用空映射。")
                self.variable_map = {}
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

    def find_param_by_usage(self, usage_tag: str) -> dict | None:
        """根据特殊用途标签查找参数的完整信息。"""
        for param_info in self.variable_map.values():
            if isinstance(param_info, dict) and usage_tag in param_info.get("special_usage", []):
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
    @Slot(float)
    def _on_mouth_ratio_update(self, open_ratio):
        lip_sync_config = self.config['lip_sync']
        final_ratio = (open_ratio ** lip_sync_config['mouth_ratio_curve']) * lip_sync_config['mouth_ratio_oversaturation']
        final_ratio = max(0.0, min(final_ratio, 1.0))

        param_info = self.mouth_param_info
        param_range = param_info['range'][1] - param_info['range'][0]
        target_value = param_info['range'][0] + final_ratio * param_range
        
        self.set_variable(param_info['name'], target_value, duration_ms=lip_sync_config['set_variable_duration_ms'])

    @Slot()
    def _reset_mouth_on_sync_finish(self):
        logger.info("同步结束，正在重置嘴型。")
        self._lip_sync_thread = None
        mouth_param = self.find_param_by_usage(bound_params.SpecialUsage.MOUTH_OPEN)
        if mouth_param:
            duration = self.config['lip_sync']['close_mouth_duration_ms']
            self.set_variable(mouth_param['name'], mouth_param['range'][0], duration_ms=duration)

    @Slot(list)
    def _on_plugins_load_finished(self, instantiated_plugins: list):
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

    def load_model(self, path_or_name: str):
        self.current_model_filename = os.path.basename(path_or_name)
        
        model_url = resolve_resource_url(path_or_name, 'models')
        
        if not model_url:
            logger.error(f"无法加载模型，路径无效: {path_or_name}")
            return

        logger.info(f"加载模型 URL: {model_url}")
        safe_url = json.dumps(model_url)
        self.view_adapter.run_javascript(f"loadNewModel({safe_url});")

    def save_bindings(self):
        if not self.current_model_filename:
            logger.error("没有已加载的模型，无法保存绑定。")
            return
        
        logger.info(f"正在将 '{self.current_model_filename}' 的绑定更新到缓存...")
        bound_params.update_cache(self.current_model_filename, self.variable_map)

    def show(self):
        self._safe_run(f'{self.js_player_name}.hide = false;')

    def hide(self):
        self._safe_run(f'{self.js_player_name}.hide = true;')

    def start_lip_sync(self, audio_queue: queue.Queue):
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
        self._lip_sync_thread.debug_data_updated.connect(self._monitor_widget.update_data)
        self._lip_sync_thread.finished.connect(self._reset_mouth_on_sync_finish)
        self._lip_sync_thread.start()


    def start_lip_sync_from_file(self, filepath: str):
        self.stop_lip_sync()
        self._streamer_stop_event.clear()
        
        audio_queue = queue.Queue()
        self.start_lip_sync(audio_queue) 
        hz = self.config.get('file_streaming', {}).get('blocksize_hz', 30)
        stream_audio_file(filepath, audio_queue, self._streamer_stop_event, hz)

    def stop_lip_sync(self):
        """停止口型同步。"""
        if self._streamer_stop_event:
            self._streamer_stop_event.set()

        if self._lip_sync_thread and self._lip_sync_thread.isRunning():
            self._lip_sync_thread.stop()
    

    # --- 2. 变换与位置 (Transform) ---
    def set_coord(self, x, y, duration_ms):
        self._safe_run(f'{self.js_player_name}.setCoord({x}, {y}, {duration_ms});')

    def set_scale(self, scale, duration_ms):
        self._safe_run(f'{self.js_player_name}.setScale({scale}, {duration_ms});')

    def set_rotation(self, angle_deg, duration_ms):
        angle_rad = angle_deg * (3.14159 / 180.0)
        self._safe_run(f'{self.js_player_name}.setRot({angle_rad}, {duration_ms});')

    def auto_center(self, duration_ms):
        self._safe_run(f'autoCenterPlayer({duration_ms});')

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
        self.set_vertex_color(self.config.get('animation', {}).get('reset_default_color', "#808080FF"), duration_ms)
        self.set_physics_scale(1.0, 1.0, 1.0)
        self.set_wind(0, 0, 0)
        if init_anim_name:
            logger.info(f"播放初始化动画 '{init_anim_name}'。")
            self.play(init_anim_name)
        logger.info("完成模型状态重置。")

    def set_diff_timeline(self, slot, timeline_name):
        if not 1 <= slot <= 6: raise ValueError("Slot must be between 1 and 6.")
        safe_name = json.dumps(timeline_name)
        self._safe_run(f'{self.js_player_name}.diffTimelineSlot{slot} = {safe_name};')

    def set_speed(self, speed_ratio):
        self._safe_run(f'{self.js_player_name}.speed = {speed_ratio};')

    def stop_all_timelines(self):
        self._safe_run(f'{self.js_player_name}.stopTimeline();')

    # --- 4. 外观与特效 (Appearance & FX) ---

    def show_dialog(self, text: str, duration_ms: int = 5000, theme: str = 'default', type_speed: int = 50, anchor_marker: str = 'dialog_anchor'):
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
        self._cached_bg_color = {"r": r, "g": g, "b": b, "a": a}
        self._safe_run(f"setBackgroundColor({r}, {g}, {b}, {a});")

    def set_window_transparent(self, enable: bool):
        if enable:
            if not self._is_window_transparent:
                # 1. 物理层：设置窗口属性
                self.view_adapter.set_window_transparent(True)
                
                # 2. 渲染层：强制全透
                self._safe_run("setBackgroundColor(0,0,0,0);")
                
                self._is_window_transparent = True
                logger.info("窗口已切换为透明模式")
        else:
            if self._is_window_transparent:
                # 1. 物理层：恢复
                self.view_adapter.set_window_transparent(False)
                
                # 2. 渲染层：恢复用户设定的背景
                c = self._cached_bg_color
                self._safe_run(f"setBackgroundColor({c['r']}, {c['g']}, {c['b']}, {c['a']});")
                
                self._is_window_transparent = False
                logger.info("窗口已恢复普通模式")

    def set_background_image(self, path_or_name: str | None):
        if path_or_name is None:
            self._safe_run("setBackgroundImage(null);")
            return

        img_url = resolve_resource_url(path_or_name, 'backgrounds')
        if img_url:
            safe_url = json.dumps(img_url)
            self._safe_run(f"setBackgroundImage({safe_url});")

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

    def get_available_special_usage_tags(self) -> list[str]:
        return [
            getattr(bound_params.SpecialUsage, attr) 
            for attr in dir(bound_params.SpecialUsage) 
            if not attr.startswith('__')
        ]

    # --- 7. 底层参数控制 (Advanced) ---

    def set_variable(self, name, value, duration_ms):
        safe_name = json.dumps(name)
        self._safe_run(f'{self.js_player_name}.setVariable({safe_name}, {value}, {duration_ms});')

    def get_variable(self, name, callback):
        safe_name = json.dumps(name)
        self._safe_query(f'{self.js_player_name}.getVariable({safe_name})', callback)

    # --- 8. 鼠标交互控制 ---
    def enable_drag(self, enable: bool):
        js_bool = json.dumps(enable) 
        self.view_adapter.run_javascript(f"enablePlayerDrag({js_bool});")

    def enable_zoom(self, enable: bool):
        js_bool = json.dumps(enable)
        self.view_adapter.run_javascript(f"enablePlayerZoom({js_bool});")

    def enable_gaze_control(self, enable: bool):
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