from PySide6.QtCore import QObject, Qt, QMetaObject, Q_ARG
from PySide6.QtQuick import QQuickWindow

# 引入接口和日志
from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.utils.logger import adapter_logger as logger

class QmlAdapter(IViewAdapter):
    """QML WebEngineView 的适配器实现。"""
    
    def __init__(self, qml_item: QObject = None):
        self._item = qml_item
        if self._item:
            self._item.setProperty("backgroundColor", "transparent")
        
        # [关键修改] 初始化时就创建bridge属性
        self._bridge_object = None
        self._bridge_name = None

    def set_view(self, qml_item: QObject):
        """设置或更新关联的 QML Item (WebEngineView)"""
        if not qml_item:
            logger.warning("QmlAdapter: set_view received None")
            return
        self._item = qml_item
        self._item.setProperty("backgroundColor", "transparent")
        logger.info(f"QmlAdapter: View 已绑定: {self._item}")

    @property
    def bridge_object(self) -> QObject:
        """提供对bridge对象的访问。"""
        return self._bridge_object

    def run_javascript(self, script: str) -> None:
        """在QML WebEngineView中执行JavaScript代码。"""
        if not self._item:
            logger.debug("QML Adapter: View尚未绑定，忽略JS执行。")
            return

        # [Fix] 不要移除换行符，防止单行注释(//)导致后续代码失效
        # safe_script = script.replace('\n', ' ').strip()
        try:
            QMetaObject.invokeMethod(
                self._item, 
                "runJavaScript", 
                Qt.ConnectionType.DirectConnection,
                Q_ARG(str, script)
            )
        except Exception as e:
            logger.error(f"QML Adapter: JS执行失败: {e}")
            logger.error(f"脚本内容: {script[:200]}...")

    def register_python_bridge(self, bridge_obj: QObject, name: str) -> None:
        """注册Python Bridge对象。"""
        bridge_obj.setObjectName(name)
        # [关键修改] 保存对bridge对象的引用
        self._bridge_object = bridge_obj
        self._bridge_name = name
        logger.info(f"QML Adapter: Bridge 对象已注册: name='{name}', id={id(bridge_obj)}")

    def set_window_transparent(self, transparent: bool) -> None:
        """设置QML顶层窗口的透明穿透。"""
        if not self._item:
            return

        window = self._item.window() 
        
        if not window:
            logger.warning("QML Adapter: 无法获取顶层窗口，透明设置失败。")
            return

        if transparent:
            window.setColor(Qt.GlobalColor.transparent)
            flags = window.flags() | Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)
        else:
            window.setColor(Qt.GlobalColor.white)
            flags = window.flags() & ~Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)

    def set_mouse_pass_through(self, enable: bool) -> None:
        if enable:
            logger.warning("QML Adapter: set_mouse_pass_through 尚未完全实现，请在 QML 侧配合处理。")
    
    def get_ui_object(self) -> QObject:
        return self._item