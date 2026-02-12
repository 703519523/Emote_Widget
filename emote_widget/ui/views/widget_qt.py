import os
#import warnings
from typing import Any, cast, Protocol
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QWidget

# 核心模块
from emote_widget.core.controller import EmoteController
from emote_widget.utils.controller_proxy import ControllerProxy
from emote_widget.core.scheme_handler import EmoteSchemeHandler
from emote_widget.core.resource_manager import ResourceManager
from emote_widget.ui.adapters.qt_adapter import WidgetAdapter
from emote_widget.ui.common.lip_sync_monitor_widget import LipSyncMonitorWidget

class WindowProtocol(Protocol):
    """定义窗口对象需要实现的接口"""
    def close(self) -> None:
        """关闭窗口的方法"""
        ...

class WindowAdapter:
    """适配器类，用于将QWidget的close方法适配为WindowProtocol要求的接口"""
    def __init__(self, widget: Any) -> None:
        self._widget = widget
    
    def close(self) -> None:
        """符合WindowProtocol的close方法"""
        self._widget.close()
        return None



class EmoteWidget(QWebEngineView):
    """
    [Qt Widget Facade] PySide6 专用的 WebEngine 容器。
    
    它负责初始化 Web 环境、适配器和控制器，但不直接包含业务逻辑。
    所有业务操作请通过 `.api` (即 controller) 进行调用。
    
    使用示例:
        widget = EmoteWidget()
        widget.show()
        
        # 通过 .api 调用功能
        widget.api.load_model("chara.psb")
        widget.api.play("hello")
        
        # 信号依然可以直接连接（为了方便）
        widget.api.player_ready.connect(print)
    """
    
    def __init__(self, parent: QWidget | None = None, plugin_path: str | None = None, config_override: dict[str, Any] | None = None, **kwargs: Any):
        super().__init__(parent)

        self.resources = ResourceManager()
        
        # 1. 配置 WebEngine 环境 (透明背景支持)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background:transparent;") 
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        # 2. 安装协议处理器 (Scheme Handler)
        # 注意：Scheme 必须在 __init__.py 中已全局注册
        self._scheme_handler = EmoteSchemeHandler()
        self.page().profile().installUrlSchemeHandler(b"emote", self._scheme_handler)

        self.adapter = WidgetAdapter(self)
        
        self.controller = EmoteController(
            view_adapter=self.adapter, 
            plugin_dir=plugin_path, 
            config_override=config_override
        )
        
        self.resources.register_cleanup_task(self.controller.cleanup)
        
        self.loadFinished.connect(self.controller.on_page_load_finished)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        url = QUrl.fromLocalFile(html_path)
        url.setScheme("emote")
        self.setUrl(url)

        self._monitor_widget: LipSyncMonitorWidget | None = None

    @property
    def api(self) -> EmoteController:
        """
        获取核心控制器实例。
        所有对模型的控制 (load_model, play, set_scale 等) 都应通过此属性调用。
        """
        return ControllerProxy(self.controller)
    
    def __getattr__(self, name: str) -> Any:
        """
        [黑魔法] 属性转发。
        
        当用户调用 widget.play() 时，因为 widget 本身没有 play 方法，
        Python 会调用此函数。我们将请求转发给 controller。
        这样可以完美兼容旧代码，同时不再需要在 Widget 里写重复的包装函数。
        """
        # 1. 检查 controller 是否有这个属性
        if self.controller and hasattr(self.controller, name):
            # 2. 发出弃用警告，提醒开发者改用 .api
            # 只有在开发调试时才会显示，生产环境通常会被忽略
            #warnings.warn(f"直接调用 'widget.{name}' 已过时，请改用 'widget.api.{name}'。", DeprecationWarning, stacklevel=2)
            
            # 3. 返回 controller 的属性（方法、信号或变量）
            return getattr(self.controller, name)
        
        # 4. 如果 controller 也没有，那就真的报错了
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def show_lip_sync_monitor(self, show: bool = True) -> None:
        """
        显示/隐藏口型同步监视器窗口 (Qt Widget 特有功能)
        
        Args:
            show (bool): 是否显示监视器窗口，默认为True
        """
        if not self._monitor_widget:
            self._monitor_widget = LipSyncMonitorWidget()
            # 使用适配器包装QWidget使其符合WindowProtocol
            self.resources.register_window(WindowAdapter(self._monitor_widget))
            # 连接 Controller 的数据信号 -> Monitor UI
            self.controller.lip_sync_debug_data.connect(self._monitor_widget.update_data)
        
        if show:
            self._monitor_widget.show()
        else:
            self._monitor_widget.hide()

    def get_monitor_widget(self) -> LipSyncMonitorWidget:
        """
        获取监视器控件实例
        
        Returns:
            LipSyncMonitorWidget: 监视器控件实例。如果之前未创建，会自动创建一个新实例。
        """
        if not self._monitor_widget:
            self.show_lip_sync_monitor(False)
        # show_lip_sync_monitor会确保_monitor_widget不为None
        return cast(LipSyncMonitorWidget, self._monitor_widget)

    def closeEvent(self, event: Any) -> None:
        """窗口关闭事件，统一清理资源"""
        self.resources.shutdown()
        super().closeEvent(event)