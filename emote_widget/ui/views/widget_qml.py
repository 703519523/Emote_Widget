"""
EmoteWidget QML 视图组件模块。

本模块提供了适用于 Qt Quick/QML 环境的后端逻辑组件 `EmoteWidgetQml`。
它通过 `QObject` 属性绑定和信号槽机制，实现了 QML 前端与 Python 后端控制器的双向通信。

注意：
此文件仅包含 Python 侧的 ViewModel 逻辑。
实际的 QML 界面定义位于 `EmoteWidget.qml` 文件中。
"""

import os
from typing import Optional, Dict, Any
from PySide6.QtCore import QObject, Signal, Slot, Property , Qt
from emote_widget.core.controller import EmoteController
from emote_widget.core.scheme_handler import EmoteSchemeHandler
from emote_widget.core.resource_manager import ResourceManager
from emote_widget.ui.adapters.qml_adapter import QmlAdapter
from emote_widget.utils.logger import emote_widget_logger as logger

class _SignalRelay(QObject):
    """
    [内部辅助类] 信号中继器。
    
    作用:
        负责接收 Controller 的原生信号并转发给 `EmoteWidgetQml` 定义的 QML 兼容信号。
        使用显式 @Slot 装饰器定义槽函数，避免 Shiboken 在运行时出现类型转换错误。
    
    Args:
        target_facade (EmoteWidgetQml): 要转发到的目标 ViewModel 实例。
    """
    def __init__(self, target_facade: "EmoteWidgetQml"):
        super().__init__()
        self._target = target_facade

    @Slot()
    def on_load_finished(self) -> None:
        self._target.loadFinished.emit()

    @Slot(list)
    def on_player_ready(self, timelines: list[str]) -> None:
        self._target.playerReady.emit(timelines)

    @Slot()
    def on_plugins_load_finished(self) -> None:
        self._target.pluginsLoadFinished.emit()

    @Slot()
    def on_character_clicked(self) -> None:
        self._target.characterClicked.emit()

    @Slot()
    def on_character_hovered(self) -> None:
        self._target.characterHovered.emit()

class EmoteWidgetQml(QObject):
    """
    [QML ViewModel] EmoteWidget 的 QML 后端逻辑类。
    
    特性:
        - **属性绑定**: 支持通过 QML 属性直接控制模型加载 (`modelSource`)。
        - **信号转发**: 将 Python 事件转换为 QML 信号。
        - **生命周期管理**: 处理页面加载、WebChannel 注册等时序问题。

    在 QML 中的使用:
        该类通常通过 `qmlRegisterType` 注册为 QML 类型，或者作为上下文属性注入。
        请参考 `EmoteWidget.qml` 获取完整的组件实现。
    """
    
    # --- 信号定义 (QML API) ---
    loadFinished = Signal()
    """当内部 Web 页面加载完成时触发。"""
    
    playerReady = Signal(list, arguments=['timelines']) 
    """当模型加载就绪时触发。参数: timelines (list[str])"""
    
    pluginsLoadFinished = Signal()
    """当所有插件加载完成时触发。"""
    
    characterClicked = Signal()
    """当角色被点击时触发。"""
    
    characterHovered = Signal()
    """当鼠标悬停在角色上时触发。"""
    
    variablesReceived = Signal(list, arguments=['variables'])
    """异步变量查询结果信号。参数: variables (list[dict])"""
    
    diffTimelinesReceived = Signal(list, arguments=['timelines'])
    """异步差分动画查询结果信号。参数: timelines (list[str])"""
    
    markerPositionReceived = Signal(dict, arguments=['position'])
    """异步标记点查询结果信号。参数: position (dict {x, y})"""
    
    # 属性变化通知信号 (Property Notify Signals)
    targetViewChanged = Signal()
    modelSourceChanged = Signal()
    bridgeChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None, plugin_path: Optional[str] = None, config_override: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self._relay = _SignalRelay(self)
        self.resources = ResourceManager()
        self._plugin_path = plugin_path
        self._config_override = config_override
        
        # 内部状态
        self._target_view: Optional[QObject] = None
        self._model_source: str = ""
        self._page_loaded: bool = False

        self._scheme_handler = EmoteSchemeHandler()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        # QML WebEngineView 加载本地文件需要标准 URL 格式
        self._main_page_url = f"emote:///{html_path.replace(os.sep, '/')}"

        # [架构重构] 提前初始化 Controller 和 Adapter
        # 此时 Adapter 还没有关联具体的 View，稍后在 set_targetView 中绑定
        self.adapter = QmlAdapter(None) 
        
        self.controller = EmoteController(
            view_adapter=self.adapter,
            plugin_dir=self._plugin_path,
            config_override=self._config_override
        )
        self.resources.register_cleanup_task(self.controller.cleanup)

        # 连接 Controller 信号 -> Relay -> QML 信号
        # 使用 QueuedConnection 确保跨线程安全
        ct = Qt.ConnectionType.QueuedConnection
        self.controller.load_finished.connect(self._relay.on_load_finished, type=ct)
        self.controller.player_ready.connect(self._relay.on_player_ready, type=ct)
        self.controller.plugins_load_finished.connect(self._relay.on_plugins_load_finished, type=ct)
        self.controller.on_character_clicked.connect(self._relay.on_character_clicked, type=ct)
        self.controller.on_character_hovered.connect(self._relay.on_character_hovered, type=ct)

    # --- QML 属性 (Properties) ---

    @Property(QObject, notify=bridgeChanged)
    def bridge(self) -> Optional[QObject]:
        """
        [只读] 获取 Controller 内部的 PythonApiBridge 对象。
        QML 端的 WebChannel 需要注册此对象，才能实现 JS 通信。
        """
        # 使用 getattr 安全访问私有成员 _bridge
        bridge = getattr(self.controller, '_bridge', None)
        if self.controller and bridge:
            return bridge
        return None

    @Property(QObject, constant=True)
    def api(self) -> QObject:
        """
        [只读] 暴露 Controller 实例给 QML。
        允许在 QML JavaScript 中直接调用 controller 的槽函数（如 play, load_model）。
        """
        return self.controller

    def get_targetView(self) -> Optional[QObject]:
        return self._target_view

    def set_targetView(self, item: Optional[QObject]) -> None:
        """
        设置关联的 WebEngineView 对象。
        当 QML 中的组件实例化完成后，会将自身传给此属性。
        """
        if self._target_view == item: return
        self._target_view = item
        self.targetViewChanged.emit()
        
        if item:
            self._attach_view(item)
    
    targetView = Property(QObject, get_targetView, set_targetView, notify=targetViewChanged)

    def get_modelSource(self) -> str:
        return self._model_source

    def set_modelSource(self, path: str) -> None:
        """
        设置要加载的模型路径。
        支持相对路径（相对于资源目录）或绝对路径。
        """
        if self._model_source == path: return
        self._model_source = path
        self.modelSourceChanged.emit()
        
        # 逻辑：如果控制器已就绪，立即加载；否则等待初始化完成后加载
        if self.controller and self._page_loaded:
            self.controller.load_model(path)
            
    modelSource = Property(str, get_modelSource, set_modelSource, notify=modelSourceChanged)

    @Property(str, constant=True)
    def mainPageUrl(self) -> str:
        """获取主入口 HTML 页面的 URL (emote:// 协议)。"""
        return self._main_page_url

    # --- 内部逻辑 ---

    def _attach_view(self, qml_item: QObject) -> None:
        """将 QML WebEngineView 绑定到 Adapter，并安装 SchemeHandler。"""
        logger.info(f"EmoteWidgetQml: 绑定 View: {qml_item}")
        
        # 1. 更新 Adapter 的目标视图
        self.adapter.set_view(qml_item)

        # 2. 安装 Scheme Handler 到 Profile
        try:
            profile = qml_item.property("profile")
            if profile:
                # 注意：PySide6 中 installUrlSchemeHandler 可能不可用，
                # 取决于具体的绑定版本。如果失败会捕获异常。
                profile.installUrlSchemeHandler(b"emote", self._scheme_handler)
                logger.info("SchemeHandler 已安装到 WebEngineProfile")
        except Exception as e:
            logger.warning(f"SchemeHandler 安装警告 (可能不影响使用): {e}")

    @Slot(QObject)
    def registerWebChannel(self, channel_obj: QObject) -> None:
        """
        [关键] 供 QML 调用，手动注册 WebChannel 对象。
        
        QML 中的 `WebChannel` 组件创建后，必须调用此方法，
        将 Python 端的 Bridge 对象注册进去，否则通信会断开。
        
        Args:
            channel_obj: QML 中的 `WebChannel` 实例。
        """
        if not channel_obj:
            logger.error("EmoteWidgetQml: 接收到的 WebChannel 对象为空")
            return
            
        try:
            # 获取 bridge 对象
            bridge = getattr(self.controller, '_bridge', None)
            if not bridge:
                logger.error("EmoteWidgetQml: Bridge 尚未初始化")
                return

            logger.info(f"EmoteWidgetQml: 正在注册 bridge 到 WebChannel: {channel_obj}")
            
            # 必须设置 objectName，虽然 registerObject 第一个参数就是名字
            bridge.setObjectName("py_api")
            
            # 动态调用 registerObject 方法 (QML WebChannel 暴露的方法)
            register_func = getattr(channel_obj, "registerObject", None)
            if callable(register_func):
                register_func("py_api", bridge)
                logger.info("EmoteWidgetQml: Bridge 注册成功！")
            else:
                logger.error("EmoteWidgetQml: WebChannel 对象缺少 registerObject 方法")

        except Exception as e:
            logger.error(f"EmoteWidgetQml: 注册 Bridge 失败: {e}")

    @Slot(bool)
    def notifyPageLoadFinished(self, success: bool) -> None:
        """
        供 QML 调用，通知 Python 页面加载完成。
        
        WebEngineView 的 `loadingChanged` 信号触发时调用此方法。
        """
        self._page_loaded = success
        
        if self.controller:
            # 1. 启动业务逻辑（插件加载等）
            self.controller.on_page_load_finished(success)
            
            # 2. 页面加载好了，现在可以加载积压的模型了 (如果有)
            if success and self._model_source:
                logger.info(f"EmoteWidgetQml: 页面就绪，执行延迟加载模型: {self._model_source}")
                self.controller.load_model(self._model_source)

    @Slot()
    def cleanup(self) -> None:
        """清理资源，应在组件销毁前调用。"""
        self.resources.shutdown()

    # --- 异步查询 Wrapper ---
    # QML JavaScript 无法直接传递 Python 回调函数，
    # 因此我们需要将异步查询封装为 "请求 -> 信号" 的模式。

    @Slot()
    def requestVariables(self) -> None:
        """
        请求变量列表 (异步)。
        结果将通过 `variablesReceived` 信号返回。
        """
        if self.controller:
            self.controller.get_variables(lambda vars: self.variablesReceived.emit(vars))

    @Slot()
    def requestDiffTimelines(self) -> None:
        """
        请求差分动画列表 (异步)。
        结果将通过 `diffTimelinesReceived` 信号返回。
        """
        if self.controller:
            self.controller.get_diff_timelines(lambda timelines: self.diffTimelinesReceived.emit(timelines))

    @Slot(str)
    def requestMarkerPosition(self, name: str) -> None:
        """
        请求标记点位置 (异步)。
        结果将通过 `markerPositionReceived` 信号返回。
        """
        if self.controller:
            self.controller.get_marker_position(name, lambda pos: self.markerPositionReceived.emit(pos if pos else {}))
