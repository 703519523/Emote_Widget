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
    负责接收 Controller 的信号并转发给 Facade。
    使用显式 @Slot 避免 Shiboken 类型转换错误。
    """
    def __init__(self, target_facade: "EmoteWidgetQml"):
        super().__init__()
        self._target = target_facade

    @Slot()
    def on_load_finished(self):
        self._target.loadFinished.emit()

    @Slot(list)
    def on_player_ready(self, timelines: list[str]):
        self._target.playerReady.emit(timelines)

    @Slot()
    def on_plugins_load_finished(self):
        self._target.pluginsLoadFinished.emit()

    @Slot()
    def on_character_clicked(self):
        self._target.characterClicked.emit()

    @Slot()
    def on_character_hovered(self):
        self._target.characterHovered.emit()

class EmoteWidgetQml(QObject):
    """
    [QML ViewModel] 支持声明式属性绑定的后端。
    """
    
    # 信号定义
    loadFinished = Signal()
    playerReady = Signal(list, arguments=['timelines']) 
    pluginsLoadFinished = Signal()
    characterClicked = Signal()
    characterHovered = Signal()
    variablesReceived = Signal(list, arguments=['variables'])
    diffTimelinesReceived = Signal(list, arguments=['timelines'])
    markerPositionReceived = Signal(dict, arguments=['position'])
    
    # 属性变化信号
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
        self._target_view = None
        self._model_source = ""
        self._page_loaded = False

        self._scheme_handler = EmoteSchemeHandler()

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(base_dir, 'web_frontend', 'pyside_webview.html')
        self._main_page_url = f"emote:///{html_path.replace(os.sep, '/')}"

        # [架构重构] 提前初始化 Controller 和 Adapter
        self.adapter = QmlAdapter(None) # 初始无 View
        
        self.controller = EmoteController(
            view_adapter=self.adapter,
            plugin_dir=self._plugin_path,
            config_override=self._config_override
        )
        self.resources.register_cleanup_task(self.controller.cleanup)

        # 连接信号 (使用 QueuedConnection)
        ct = Qt.ConnectionType.QueuedConnection
        self.controller.load_finished.connect(self._relay.on_load_finished, type=ct)
        self.controller.player_ready.connect(self._relay.on_player_ready, type=ct)
        self.controller.plugins_load_finished.connect(self._relay.on_plugins_load_finished, type=ct)
        self.controller.on_character_clicked.connect(self._relay.on_character_clicked, type=ct)
        self.controller.on_character_hovered.connect(self._relay.on_character_hovered, type=ct)

    @Property(QObject, notify=bridgeChanged)
    def bridge(self) -> Optional[QObject]:
        """[只读] 暴露 Controller 内部的 Bridge 对象给 QML"""
        # 使用 getattr 安全访问 _bridge，避免 pylance 报错
        bridge = getattr(self.controller, '_bridge', None)
        if self.controller and bridge:
            return bridge
        return None

    @Property(QObject, constant=True)
    def api(self) -> QObject:
        """[只读] 暴露 Controller 实例给 QML"""
        return self.controller

    def get_targetView(self) -> Optional[QObject]:
        return self._target_view

    def set_targetView(self, item: Optional[QObject]):
        if self._target_view == item: return
        self._target_view = item
        self.targetViewChanged.emit()
        
        if item:
            self._attach_view(item)
    
    targetView = Property(QObject, get_targetView, set_targetView, notify=targetViewChanged)

    def get_modelSource(self) -> str:
        return self._model_source

    def set_modelSource(self, path: str):
        if self._model_source == path: return
        self._model_source = path
        self.modelSourceChanged.emit()
        
        # 如果控制器已就绪，立即加载；否则等待初始化后加载
        if self.controller and self._page_loaded:
            self.controller.load_model(path)
            
    modelSource = Property(str, get_modelSource, set_modelSource, notify=modelSourceChanged)

    @Property(str, constant=True)
    def mainPageUrl(self):
        return self._main_page_url

    def _attach_view(self, qml_item: QObject):
        logger.info(f"EmoteWidgetQml: 绑定 View: {qml_item}")
        
        # 1. 更新 Adapter
        self.adapter.set_view(qml_item)

        # 2. 安装 Scheme Handler
        try:
            profile = qml_item.property("profile")
            if profile:
                # 检查是否已经安装过，或者直接重新安装
                profile.installUrlSchemeHandler(b"emote", self._scheme_handler)
                logger.info("SchemeHandler 已安装到 WebEngineProfile")
        except Exception as e:
            logger.warning(f"SchemeHandler 安装警告: {e}")

        # 注意：这里不需要再 emit bridgeChanged，因为 bridge 一直都在

    @Slot(QObject)
    def registerWebChannel(self, channel_obj: QObject):
        """供 QML 调用，手动注册 WebChannel 对象"""
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
            
            # 使用 QWebChannel.registerObject
            # 注意：这里假设 channel_obj 是 QWebChannel (或 QQmlWebChannel) 的实例
            # 在 PySide6 中，QML WebChannel 传递过来应该是 QObject，
            # 我们需要确信它有 registerObject 方法。
            # QQmlWebChannel 继承自 QWebChannel。
            
            # 必须设置 objectName，虽然 registerObject 第一个参数就是名字
            bridge.setObjectName("py_api")
            
            # 使用 getattr 动态调用 registerObject 以避免 pylance 静态检查错误
            # 因为 QObject 类型本身没有 registerObject 方法
            register_func = getattr(channel_obj, "registerObject", None)
            if callable(register_func):
                register_func("py_api", bridge)
                logger.info("EmoteWidgetQml: Bridge 注册成功！")
            else:
                logger.error("EmoteWidgetQml: WebChannel 对象缺少 registerObject 方法")

        except Exception as e:
            logger.error(f"EmoteWidgetQml: 注册 Bridge 失败: {e}")

    @Slot(bool)
    def notifyPageLoadFinished(self, success: bool):
        """供 QML 调用，通知页面加载完成"""
        self._page_loaded = success
        
        if self.controller:
            # 1. 启动业务逻辑（插件加载等）
            self.controller.on_page_load_finished(success)
            
            # 2. 页面加载好了，现在可以加载积压的模型了
            if success and self._model_source:
                logger.info(f"EmoteWidgetQml: 页面就绪，执行延迟加载模型: {self._model_source}")
                self.controller.load_model(self._model_source)

    @Slot()
    def cleanup(self):
        self.resources.shutdown()

    # --- 异步查询 Wrapper (保留，因为 QML 无法直接传递 callback) ---

    @Slot()
    def requestVariables(self):
        """请求变量列表 (异步)"""
        if self.controller:
            self.controller.get_variables(lambda vars: self.variablesReceived.emit(vars))

    @Slot()
    def requestDiffTimelines(self):
        """请求差分动画列表 (异步)"""
        if self.controller:
            self.controller.get_diff_timelines(lambda timelines: self.diffTimelinesReceived.emit(timelines))

    @Slot(str)
    def requestMarkerPosition(self, name: str):
        """请求标记点位置 (异步)"""
        if self.controller:
            self.controller.get_marker_position(name, lambda pos: self.markerPositionReceived.emit(pos if pos else {}))
