"""
EmoteWidget Qt 适配器模块。

本模块实现了 `IViewAdapter` 接口的 Qt 版本，用于在 `PySide6.QtWebEngineWidgets.QWebEngineView`
环境下运行 EmoteWidget SDK。它负责将控制器的抽象指令转换为具体的 Qt API 调用。
"""

from typing import Optional, List, Any
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import Qt, QObject, QRect
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QWidget

from emote_widget.core.adapter_interface import IViewAdapter
from emote_widget.utils.logger import emote_widget_logger as logger

class WidgetAdapter(IViewAdapter):
    """
    [Qt 适配器] 实现 IViewAdapter 接口，桥接 Controller 与 QWebEngineView。
    
    主要功能:
    1. **JS 执行**: 封装 `page().runJavaScript()`。
    2. **桥接注入**: 封装 `QWebChannel` 的注册流程。
    3. **窗口特效**: 利用 `QWidget.setMask` 实现异形窗口和点击穿透。
    """
    
    def __init__(self, webview: QWebEngineView) -> None:
        """
        初始化适配器。
        
        Args:
            webview (QWebEngineView): 目标 Web 视图组件实例。
        """
        self.webview = webview
        # 初始化 WebChannel 并挂载到页面
        # 必须在页面加载前完成设置，否则 JS 端可能无法连接
        self._web_channel = QWebChannel(self.webview.page())
        self.webview.page().setWebChannel(self._web_channel)

    def run_javascript(self, script: str) -> None:
        """
        [实现接口] 在 Web 页面中执行 JavaScript 代码。
        QtWebEngine 的 runJavaScript 是异步的，不会阻塞 Python 线程。
        """
        self.webview.page().runJavaScript(script)

    def register_python_bridge(self, bridge_obj: Any, name: str) -> None:
        """
        [实现接口] 将 Python 对象注册到 WebChannel。
        
        这使得前端 JS 可以通过 `qt.webChannelTransport` 访问该对象。
        在我们的 SDK 中，JS 端的 `QWebChannel` 初始化脚本会自动将此对象
        挂载到 `window[name]` (例如 `window.py_api`)。
        """
        if not isinstance(bridge_obj, QObject):
            logger.error(f"register_python_bridge: 对象 {bridge_obj} 不是 QObject，无法注册。")
            return
            
        self._web_channel.registerObject(name, bridge_obj)
        logger.debug(f"已注册 WebChannel 对象: {name}")

    def set_window_transparent(self, transparent: bool) -> None:
        """
        [实现接口] 设置顶层窗口的透明属性。
        
        注意:
            此方法会修改窗口的 WindowFlags (FramelessWindowHint)，
            可能会导致窗口在运行时短暂闪烁或重创建。
        """
        window = self.webview.window() # 获取顶层窗口 (可能是 self.webview 本身)
        if not window:
            return
        
        # 检查是否为嵌入模式 (有父窗口)
        # 如果是嵌入模式，我们不应随意修改父窗口的属性，只确保自身背景透明即可
        if self.webview.parent():
            if transparent:
                self.webview.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                self.webview.setStyleSheet("background:transparent;")
            return

        # 独立窗口模式 (Top-level Widget)
        if transparent:
            # 开启无边框 + 透明背景
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
            # 更改 Flags 后通常需要重新 show 才能生效
            window.show()
        else:
            # 恢复默认 (有边框 + 不透明)
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            window.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
            window.show()

    def set_mouse_pass_through(self, enable: bool) -> None:
        """[实现接口] 暂不支持全窗口鼠标穿透，仅支持基于 Mask 的穿透。"""
        logger.warning("set_mouse_pass_through: Qt Adapter 暂未实现全窗口穿透 API。建议使用 set_render_mask。")
    
    def set_render_mask(self, rects: Optional[List[List[int]]]) -> None:
        """
        [实现接口] 设置异形窗口遮罩 (Input Mask)。
        
        原理:
            利用 `QWidget.setMask(QRegion)` 方法。
            QRegion 定义了窗口的“有效区域”，只有在区域内的部分才接收鼠标事件并显示内容；
            区域外的部分对操作系统来说是“不存在”的，鼠标会直接穿透到底层窗口。
            
        Args:
            rects: 矩形列表 [[x,y,w,h], ...]。如果为 None 或空列表，则清除遮罩。
        """
        if rects is None:
            # 恢复默认：全窗口可点击
            self.webview.clearMask()
            return

        if not rects:
            # 空列表 = 全透明 = 全穿透 (设置一个空的 Region)
            self.webview.setMask(QRegion()) 
            return

        region = QRegion()
        
        # 批量合并矩形
        # 性能提示: QRegion 的合并操作 (+) 在矩形数量较多 (>100) 时可能较慢。
        # 但由于我们使用了 Greedy Meshing 算法，rects 数量通常很少 (<50)，性能是可以接受的。
        for x, y, w, h in rects:
             # 为了容错和视觉连续性，稍微向外膨胀一点点 (adjusted)
             # 但这里我们保持精确，相信 mask_sampler.js 的计算
             region += QRect(int(x), int(y), int(w), int(h))
        
        self.webview.setMask(region)

    def get_ui_object(self) -> QWidget:
        """[实现接口] 返回底层的 QWebEngineView 实例。"""
        return self.webview
