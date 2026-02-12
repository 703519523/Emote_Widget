# emote_widget/ui/adapters/qml_adapter.py

from typing import Any, Callable, Optional
from PySide6.QtCore import QObject, Qt
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtQuick import QQuickWindow

# 引入接口和日志
from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.utils.logger import adapter_logger as logger

class QmlAdapter(IViewAdapter):
    """
    QML WebEngineView 的适配器实现。
    
    注意：在 PySide6 中，QML 的 WebEngineView 在 Python 侧表现为 QObject，
    并没有一个具体的 'QQuickWebEngineView' 类可以导入用于类型检查。
    因此我们使用 QObject 作为类型注解，并依靠动态调用。
    """
    
    def __init__(self, qml_item: QObject):
        if not qml_item:
            raise ValueError("QmlAdapter 需要一个有效的 QML Item 实例")
        
        # 类型注解使用 Any(动态对象)，避免 Pylance 报错
        self._item: Any = qml_item
        self._web_channel = QWebChannel(self._item)
        
        # 1. 挂载 WebChannel
        # 对应 QML: WebEngineView { webChannel: ... }
        # 注意：QML 端该属性必须存在（通常是默认存在的，或者需要手动声明属性）
        self._item.setProperty("webChannel", self._web_channel)
        
        # 2. 设置背景透明
        # 对应 QML: WebEngineView { backgroundColor: "transparent" }
        self._item.setProperty("backgroundColor", "transparent")

    def run_javascript(self, script: str) -> None:
        # QML 对象暴露的 runJavaScript 方法直接挂在 item 上
        # 这是一个动态方法，静态检查可能无法识别，但运行时有效
        if hasattr(self._item, "runJavaScript"):
            self._item.runJavaScript(script)
        else:
            logger.error("QML Item 不支持 runJavaScript 方法，请检查对象是否为 WebEngineView。")

    def run_javascript_with_callback(self, script: str, callback: Callable[[Any], None]) -> None:
        if not hasattr(self._item, "runJavaScript"):
            logger.error("QML Item 不支持 runJavaScript 方法。")
            return

        # PySide6 对 QML 方法的调用支持传入 Python 回调
        if callback is not None:
            self._item.runJavaScript(script, callback)
        else:
            self._item.runJavaScript(script)

    def register_python_bridge(self, bridge_obj: QObject, name: str) -> None:
        self._web_channel.registerObject(name, bridge_obj)
        logger.info(f"QML Adapter: 已注册 WebChannel 对象: {name}")

    def set_window_transparent(self, transparent: bool) -> None:
        """
        设置 QML 顶层窗口的透明穿透。
        """
        # 获取 Item 所在的 QQuickWindow
        window: Optional[QQuickWindow] = self._item.window() 
        
        if not window:
            logger.warning("QML Adapter: 无法获取顶层窗口，透明设置失败。")
            return

        if transparent:
            # 1. 设置窗口背景色为透明
            window.setColor(Qt.GlobalColor.transparent)
            # 2. 去除边框
            flags = window.flags() | Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)
        else:
            # 恢复逻辑
            window.setColor(Qt.GlobalColor.white) # 这里假设恢复为白色，或者你可以尝试读取之前的颜色
            flags = window.flags() & ~Qt.WindowType.FramelessWindowHint
            window.setFlags(flags)

    def set_mouse_pass_through(self, enable: bool) -> None:
        # QML 的鼠标穿透通常需要在 QML 端处理 Mask，
        # 或者在 Python 端对 Window 设置 Qt.WindowTransparentForInput
        if enable:
            logger.warning("QML Adapter: set_mouse_pass_through 尚未完全实现，请在 QML 侧配合处理。")
    
    def get_ui_object(self) -> QObject:
        return self._item