from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QObject, QRect
from PySide6.QtGui import QRegion
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

    def register_python_bridge(self, bridge_obj: QObject, name: str) -> None:
        """
        将 Python 对象注册到 WebChannel，使其在 JS 中可用 (e.g. window.py_api)
        """
        self._web_channel.registerObject(name, bridge_obj)
        logger.debug(f"已注册 WebChannel 对象: {name}")

    def set_window_transparent(self, transparent: bool) -> None:
        """
        设置顶层窗口的透明穿透属性。
        只有当 webview 本身就是顶层窗口（没有父窗口）时，才修改窗口标志位。
        如果嵌入在其他窗口中，仅设置背景透明属性，避免破坏父窗口布局。
        """
        window = self.webview.window() # 获取顶层窗口
        if not window:
            return
        
        if self.webview.parent():
            # 嵌入模式：不修改 WindowFlags，只修改背景属性，允许上层应用遮罩
            # 这种情况下，全窗透明由父窗口自己管理，只负责组件内部透明
            # 但需要确保 TranslucentBackground 被设置，以便遮罩生效时能透到底色
            pass 
        else:
            # 独立窗口模式：修改 WindowFlags 实现无边框透明
            if transparent:
                # 开启透明穿透
                window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
                window.show() # 更改 Flags 后通常需要重新 show
            else:
                # 关闭透明穿透 (恢复默认)
                window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                window.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
                window.show()

    def set_mouse_pass_through(self, enable: bool) -> None:
        # Qt 窗口级别的鼠标穿透比较复杂，通常包含在 set_window_transparent 
        # 的 FramelessWindowHint + TranslucentBackground 组合效果中。
        # 如果需要更高级的“鼠标点透但可见”，通常需要操作系统 API，此处暂留空。
        logger.warning("set_mouse_pass_through: Qt Adapter 尚未实现独立的鼠标穿透功能。")
    
    def set_render_mask(self, rects: list[list[int]] | None) -> None:
        """
        设置渲染区域掩码 (用于点击穿透)。
        rects: [[x, y, w, h], ...] 矩形列表。如果为 None，则清除遮罩（恢复全窗口点击）。
        """
        if rects is None:
            self.webview.clearMask()
            return

        if not rects:
            # 列表为空 = 全透明 = 全穿透 (设置空遮罩)
            self.webview.setMask(QRegion()) 
            return

        region = QRegion()
        # 批量添加矩形
        # 注意：Python 循环添加可能稍慢，如果 rects 数量巨大需要优化
        for x, y, w, h in rects:
             # 向外膨胀2像素以避免缺口
             region += QRect(int(x), int(y), int(w), int(h)).adjusted(-2, -2, 2, 2)
        
        self.webview.setMask(region)

    def get_ui_object(self) -> QWidget:
        return self.webview