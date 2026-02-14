"""
EmoteWidget Qt 视图组件模块。

本模块提供了一个基于 `PySide6.QtWebEngineWidgets.QWebEngineView` 的高级封装组件 `EmoteWidget`。
它是用户在传统的 Qt (QtWidgets) 应用程序中集成 EmoteWidget SDK 的主要入口。

主要特性：
    - **开箱即用**: 内置了 WebView 环境配置、SchemeHandler 和资源管理。
    - **透明窗口支持**: 默认开启背景透明，支持创建异形桌面挂件。
    - **API 代理**: 通过 `.api` 属性直接暴露核心控制器功能。
    - **调试工具**: 集成了 LipSync 和 Mask 监视器窗口。
"""

import os
#import warnings
from typing import Any, cast, Protocol, Optional, Dict
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QCloseEvent

# 核心模块
from emote_widget.core.controller import EmoteController
from emote_widget.utils.controller_proxy import ControllerProxy
from emote_widget.core.scheme_handler import EmoteSchemeHandler
from emote_widget.core.resource_manager import ResourceManager
from emote_widget.ui.adapters.qt_adapter import WidgetAdapter
from emote_widget.ui.common.lip_sync_monitor_widget import LipSyncMonitorWidget
from emote_widget.ui.common.mask_monitor_widget import MaskMonitorWidget
from emote_widget.utils.logger import emote_widget_logger as logger

# --- 协议定义 ---

class WindowProtocol(Protocol):
    """
    定义窗口对象需要实现的接口协议。
    
    ResourceManager 使用此协议来统一管理不同类型的窗口资源（QWidget, QWindow 等），
    确保在程序退出时能正确关闭它们。
    """
    def close(self) -> bool:
        """关闭窗口的方法。"""
        ...

class WindowAdapter:
    """
    适配器类，用于将任意 QWidget 包装为符合 WindowProtocol 协议的对象。
    
    这是适配器模式 (Adapter Pattern) 的应用，解决了 QWidget.close() 
    返回值签名可能与协议不完全匹配（虽然在 Python 中是动态类型，但为了类型检查严格性）的问题。
    """
    def __init__(self, widget: Any) -> None:
        self._widget = widget
    
    def close(self) -> bool:
        """调用被包装控件的 close 方法。"""
        return self._widget.close()


# --- 主组件 ---

class EmoteWidget(QWebEngineView):
    """
    [Qt Widget Facade] PySide6 专用的 WebEngine 容器组件。
    
    设计模式:
        外观模式 (Facade Pattern): 它封装了底层的 WebView、SchemeHandler、Adapter 和 Controller，
        对外提供一个简单易用的 API 接口。

    使用示例:
        ```python
        # 1. 创建组件
        widget = EmoteWidget()
        widget.resize(800, 600)
        widget.show()
        
        # 2. 加载模型 (通过 .api 访问控制器功能)
        widget.api.load_model("chara.psb")
        
        # 3. 播放动画
        widget.api.play("hello")
        
        # 4. 连接信号
        widget.api.player_ready.connect(lambda timelines: print("模型就绪!", timelines))
        ```

    Attributes:
        api (ControllerProxy): 核心控制器的代理对象，所有业务操作都应通过此属性进行。
        controller (EmoteController): 内部控制器实例。
    """
    
    def __init__(self, parent: Optional[QWidget] = None, plugin_path: Optional[str] = None, config_override: Optional[Dict[str, Any]] = None, **kwargs: Any):
        """
        初始化 EmoteWidget 组件。

        Args:
            parent (Optional[QWidget]): 父级窗口控件。
            plugin_path (Optional[str]): 自定义插件目录路径。默认为内置 plugins 目录。
            config_override (Optional[Dict]): 用于覆盖默认配置的字典。
            **kwargs: 传递给 QWebEngineView 的其他参数。
        """
        super().__init__(parent)

        # 资源管理器：负责管理辅助窗口和清理任务
        self.resources = ResourceManager()
        
        # 1. 配置 WebEngine 环境 (透明背景支持)
        # 必须同时设置 Widget 属性和 Page 背景色为透明，才能实现网页背景透视
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background:transparent;") 
        self.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        # 2. 安装协议处理器 (Scheme Handler)
        # 用于拦截 `emote://` 开头的请求，将其重定向到本地文件系统或资源包
        # 注意：全局 Scheme 工厂必须在 Application 启动前注册，这里是针对 Profile 的局部安装
        self._scheme_handler = EmoteSchemeHandler()
        self.page().profile().installUrlSchemeHandler(b"emote", self._scheme_handler)

        # 3. 初始化 MVVM 架构组件
        # ViewAdapter: 将本 Widget 包装为控制器可识别的 IViewAdapter 接口
        self.adapter = WidgetAdapter(self)
        
        # Controller: 核心业务逻辑
        self.controller = EmoteController(
            view_adapter=self.adapter, 
            plugin_dir=plugin_path, 
            config_override=config_override
        )
        
        # 注册清理回调
        self.resources.register_cleanup_task(self.controller.cleanup)
        
        # 连接页面加载完成信号 -> 启动控制器初始化流程
        self.loadFinished.connect(self.controller.on_page_load_finished)
        
        # 4. 加载宿主页面 (index.html)
        # 获取绝对路径，兼容开发环境和打包环境
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        
        # 使用 file:// 协议加载本地文件，但在内部请求中使用 emote://
        url = QUrl.fromLocalFile(html_path)
        # 修正：不应更改主页面的 scheme，否则可能触发跨域安全策略。保持 file://，资源加载用 emote://。
        # url.setScheme("emote") 
        self.setUrl(url)

        # 调试窗口引用
        self._monitor_widget: Optional[LipSyncMonitorWidget] = None
        self._mask_monitor_widget: Optional[MaskMonitorWidget] = None

    @property
    def api(self) -> ControllerProxy:
        """
        [推荐] 获取核心控制器的代理接口。
        
        ControllerProxy 提供了一层额外的安全封装，不仅包含所有控制器方法，
        还会在访问私有成员（以 _ 开头）时抛出警告，确保 API 使用的规范性。
        """
        return ControllerProxy(self.controller)
    
    def __getattr__(self, name: str) -> Any:
        """
        [兼容层] 属性动态转发魔法。
        
        允许用户直接调用 `widget.load_model()` 而不必写 `widget.api.load_model()`。
        这种“外观模式”简化了 API，但为了代码清晰度，建议显式使用 `.api`。
        
        Args:
            name (str): 属性名。
            
        Returns:
            Any: 控制器对应的方法或属性。
            
        Raises:
            AttributeError: 如果控制器也没有该属性。
        """
        # 1. 检查 controller 是否有这个属性
        if self.controller and hasattr(self.controller, name):
            # 2. (可选) 发出弃用警告，提醒开发者改用 .api
            # warnings.warn(f"直接调用 'widget.{name}' 已过时，请改用 'widget.api.{name}'。", DeprecationWarning, stacklevel=2)
            
            # 3. 返回 controller 的属性（方法、信号或变量）
            return getattr(self.controller, name)
        
        # 4. 如果 controller 也没有，那就真的报错了
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def show_lip_sync_monitor(self, show: bool = True) -> None:
        """
        显示或隐藏口型同步调试监视器。
        
        监视器窗口会实时显示音频振幅曲线和嘴型张开度，
        对于调试 LipSync 参数配置非常有帮助。
        
        Args:
            show (bool): True 显示，False 隐藏。
        """
        if not self._monitor_widget:
            self._monitor_widget = LipSyncMonitorWidget()
            # 注册到 ResourceManager 以便自动管理生命周期
            self.resources.register_window(WindowAdapter(self._monitor_widget))
            # 连接数据信号：Controller (Model) -> Monitor (View)
            self.controller.lip_sync_debug_data.connect(self._monitor_widget.update_data)
        
        if show:
            self._monitor_widget.show()
        else:
            self._monitor_widget.hide()

    def get_monitor_widget(self) -> LipSyncMonitorWidget:
        """
        获取监视器控件实例（单例模式）。
        如果尚未创建，会自动创建一个隐藏的实例。
        
        Returns:
            LipSyncMonitorWidget: 监视器控件实例。
        """
        if not self._monitor_widget:
            self.show_lip_sync_monitor(False)
        return cast(LipSyncMonitorWidget, self._monitor_widget)

    def show_mask_monitor(self, show: bool = True) -> None:
        """
        显示或隐藏异形遮罩调试监视器。
        
        该窗口会以可视化的方式展示当前每帧计算出的点击穿透区域（红色矩形）。
        用于验证 `MaskSampler` 算法的效果。
        
        Args:
            show (bool): True 显示，False 隐藏。
        """
        if not self._mask_monitor_widget:
            self._mask_monitor_widget = MaskMonitorWidget()
            self.resources.register_window(WindowAdapter(self._mask_monitor_widget))
            self.controller.render_mask_visual_data.connect(self._mask_monitor_widget.update_mask)
        
        if show:
            self._mask_monitor_widget.show()
        else:
            self._mask_monitor_widget.hide()

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        [事件重写] 窗口关闭事件。
        
        在此处触发资源清理流程，关闭所有子窗口、停止线程、卸载插件。
        """
        logger.info("EmoteWidget 正在关闭，清理资源...")
        self.resources.shutdown()
        super().closeEvent(event)
