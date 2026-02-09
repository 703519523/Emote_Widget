import os
import queue
from PySide6.QtWidgets import QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtCore import QUrl, Signal, Qt

from emote_widget.core.controller import EmoteController
from emote_widget.core.scheme_handler import EmoteSchemeHandler
from emote_widget.ui.adapters.widget_adapter import WidgetAdapter
from emote_widget.ui.common.lip_sync_monitor_widget import LipSyncMonitorWidget
from emote_widget.core.resource_manager import ResourceManager
from emote_widget.utils.logger import emote_widget_logger as logger

class EmoteWidget(QWebEngineView):
    """
    [Facade] 对外的主 Widget 类。
    它继承自 QWebEngineView 以便直接嵌入 Qt 布局。
    它持有 EmoteController，并将所有操作委托给 Controller 处理。
    """
    
    # 转发 Controller 的信号，保持对外 API 一致
    load_finished = Signal()
    player_ready = Signal(list)
    plugins_load_finished = Signal()
    on_character_clicked = Signal()
    on_character_hovered = Signal()
    
    def __init__(self, parent=None, plugin_path: str = None, config_override: dict = None, **kwargs):
        super().__init__(parent)

        self.resources = ResourceManager()
        
        # 1. 配置 WebEngine 环境 (Handler, 透明背景等)
        self.setAttribute(Qt.WA_TranslucentBackground, True) # 允许网页透明
        self.setStyleSheet("background:transparent;") 
        self.page().setBackgroundColor(Qt.transparent)
        
        # 安装 Scheme Handler (必须在加载页面前)
        self._scheme_handler = EmoteSchemeHandler()
        self.page().profile().installUrlSchemeHandler(b"emote", self._scheme_handler)

        # 2. 初始化 Adapter
        self.adapter = WidgetAdapter(self)

        # 3. 初始化 Controller (传入 adapter 和 plugin_path)
        # 这里 plugin_path 默认为 None，Controller 内部会处理为 os.getcwd()/plugins
        self.controller = EmoteController(
            view_adapter=self.adapter, 
            plugin_dir=plugin_path, 
            config_override=config_override
        )
        self.resources.register_cleanup_task(self.controller.cleanup)
        
        # 4. 连接信号转发
        self.controller.load_finished.connect(self.load_finished)
        self.controller.player_ready.connect(self.player_ready)
        self.controller.plugins_load_finished.connect(self.plugins_load_finished)
        self.controller.on_character_clicked.connect(self.on_character_clicked)
        self.controller.on_character_hovered.connect(self.on_character_hovered)
        
        # 内部：连接页面加载信号通知 Controller
        self.loadFinished.connect(self.controller._on_page_load_finished) # 假设Controller有这个槽
        # 注意：上面的 controller 代码中是 _on_page_load_finished，建议在 Controller 里公开为 on_webview_load_finished，或者改 Controller
        # 修正：Controller 之前重构时叫 _on_page_load_finished，我们保持一致即可
        
        # 5. 加载 HTML 页面 (通过 emote:// 协议)
        # 计算 pyside_webview.html 的路径
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        
        url = QUrl.fromLocalFile(html_path)
        url.setScheme("emote") # 关键：使用自定义协议加载主页
        self.setUrl(url)

        # UI 独有组件
        self._monitor_widget = None

    # --------------------------------------------------------------------------
    #  UI 独有功能
    # --------------------------------------------------------------------------
    def show_lip_sync_monitor(self, show: bool = True):
        """显示/隐藏口型同步监视器窗口"""
        if not self._monitor_widget:
            self._monitor_widget = LipSyncMonitorWidget()
            self.resources.register_window(self._monitor_widget)
            self.controller.lip_sync_debug_data.connect(self._monitor_widget.update_data)
        
        if show:
            self._monitor_widget.show()
        else:
            self._monitor_widget.hide()

    def get_monitor_widget(self):
        """获取监视器控件实例 (以便嵌入其他布局)"""
        if not self._monitor_widget:
            # 即使不显示，也先实例化并连接信号
            self.show_lip_sync_monitor(False)
        return self._monitor_widget

    # --------------------------------------------------------------------------
    #  API 代理 (Delegation)
    #  为了保持 run_tests.py 不需要修改，我们将 Controller 的方法暴露出来
    # --------------------------------------------------------------------------
    
    @property
    def plugins(self):
        return self.controller.plugins

    def load_model(self, *args, **kwargs): self.controller.load_model(*args, **kwargs)
    def save_bindings(self): self.controller.save_bindings()
    
    # 显式控制
    def show(self): 
        super().show()
        self.controller.show()
        
    def hide(self): 
        super().hide()
        self.controller.hide()

    def start_lip_sync(self, q: queue.Queue): self.controller.start_lip_sync(q)
    def start_lip_sync_from_file(self, f: str): self.controller.start_lip_sync_from_file(f)
    def stop_lip_sync(self): self.controller.stop_lip_sync()
    
    def set_coord(self, x, y, t=0): self.controller.set_coord(x, y, t)
    def set_scale(self, s, t=0): self.controller.set_scale(s, t)
    def set_rotation(self, r, t=0): self.controller.set_rotation(r, t)
    def auto_center(self, t=300): self.controller.auto_center(t)
    
    def play(self, name): self.controller.play(name)
    def animation_reset(self, t=300, name=None): self.controller.animation_reset(t, name)
    def set_diff_timeline(self, slot, name): self.controller.set_diff_timeline(slot, name)
    def set_speed(self, s): self.controller.set_speed(s)
    def stop_all_timelines(self): self.controller.stop_all_timelines()
    
    def show_dialog(self, *args, **kwargs): self.controller.show_dialog(*args, **kwargs)
    def set_background_color(self, r, g, b, a): self.controller.set_background_color(r, g, b, a)
    def set_window_transparent(self, e): self.controller.set_window_transparent(e)
    def set_background_image(self, f): self.controller.set_background_image(f)
    
    def set_grayscale(self, v, t=0): self.controller.set_grayscale(v, t)
    def set_global_alpha(self, v, t=0): self.controller.set_global_alpha(v, t)
    def set_vertex_color(self, c, t=0): self.controller.set_vertex_color(c, t)
    
    def set_physics_scale(self, h=1, p=1, b=1): self.controller.set_physics_scale(h, p, b)
    def set_wind(self, s, min_p=0, max_p=2): self.controller.set_wind(s, min_p, max_p)
    
    def get_main_timelines(self, cb): self.controller.get_main_timelines(cb)
    def get_diff_timelines(self, cb): self.controller.get_diff_timelines(cb)
    def get_variables(self, cb): self.controller.get_variables(cb)
    def get_marker_position(self, name, cb): self.controller.get_marker_position(name, cb)
    def get_available_special_usage_tags(self): return self.controller.get_available_special_usage_tags()
    
    def set_variable(self, n, v, t=0): self.controller.set_variable(n, v, t)
    def get_variable(self, n, cb): self.controller.get_variable(n, cb)
    
    def enable_drag(self, e): self.controller.enable_drag(e)
    def enable_zoom(self, e): self.controller.enable_zoom(e)
    def enable_gaze_control(self, e): self.controller.enable_gaze_control(e)

    def closeEvent(self, event):
        """窗口关闭事件，清理资源"""
        self.resources.shutdown()
        super().closeEvent(event)