from typing import Any, Callable
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QObject
from PySide6.QtWidgets import QWidget

from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.utils.logger import emote_widget_logger as logger

class WidgetAdapter(IViewAdapter):
    """
    Qt WebEngineView 的适配器实现。
    它封装了具体的 Qt API 调用，供 Controller 使用。
    """
    def __init__(self, webview: QWebEngineView):
        self.webview = webview
        self._web_channel = QWebChannel(self.webview.page())
        self.webview.page().setWebChannel(self._web_channel)

    def run_javascript(self, script: str) -> None:
        self.webview.page().runJavaScript(script)

    def run_javascript_with_callback(self, script: str, callback: Callable[[Any], None]) -> None:
        # Qt 的 runJavaScript 支持可选的 callback 参数
        if callback:
            self.webview.page().runJavaScript(script, callback)
        else:
            self.webview.page().runJavaScript(script)

    def register_python_bridge(self, bridge_obj: QObject, name: str) -> None:
        """
        将 Python 对象注册到 WebChannel，使其在 JS 中可用 (e.g. window.py_api)
        """
        self._web_channel.registerObject(name, bridge_obj)
        logger.debug(f"已注册 WebChannel 对象: {name}")

    def set_window_transparent(self, transparent: bool) -> None:
        """
        设置顶层窗口的透明穿透属性。
        """
        window = self.webview.window() # 获取顶层窗口
        if not window:
            return

        if transparent:
            # 开启透明穿透
            window.setAttribute(Qt.WA_TranslucentBackground, True)
            window.setWindowFlag(Qt.FramelessWindowHint, True)
            window.show() # 更改 Flags 后通常需要重新 show
        else:
            # 关闭透明穿透 (恢复默认)
            window.setAttribute(Qt.WA_TranslucentBackground, False)
            window.setWindowFlag(Qt.FramelessWindowHint, False)
            window.show()

    def set_mouse_pass_through(self, enable: bool) -> None:
        # Qt 窗口级别的鼠标穿透比较复杂，通常包含在 set_window_transparent 
        # 的 FramelessWindowHint + TranslucentBackground 组合效果中。
        # 如果需要更高级的“鼠标点透但可见”，通常需要操作系统 API，此处暂留空。
        logger.warning("set_mouse_pass_through: Qt Adapter 尚未实现独立的鼠标穿透功能。")
    
    def get_ui_object(self) -> QWidget:
        return self.webview