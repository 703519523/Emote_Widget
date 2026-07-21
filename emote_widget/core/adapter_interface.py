"""
EmoteWidget 视图适配器接口模块。

本模块定义了 `IViewAdapter` 抽象基类，作为连接 `EmoteController` (业务逻辑) 与具体 UI 框架 (如 Qt, QML, Chromium) 的契约。
通过实现此接口，可以将 EmoteWidget 移植到任何支持 WebView 的 GUI 环境中，而无需修改核心控制器代码。
"""

from abc import ABC, abstractmethod
from typing import Any, List
from emote_widget.utils.logger import emote_widget_logger as logger

class IViewAdapter(ABC):
    """
    [视图适配器接口] 定义 Python 控制器与 UI 视图层交互的标准协议。
    
    设计目的 (Design Purpose):
        实现核心业务逻辑与 UI 框架的解耦。控制器仅通过此接口与视图通信，
        不依赖于具体的 QWebEngineView 或其他控件。
    
    实现指南 (Implementation Guide):
        1. **必须实现** (@abstractmethod) 的方法：
           - `run_javascript`: 执行 JS 代码。
           - `register_python_bridge`: 注入 Python 对象到 JS 环境。
           
        2. **可选实现** (Virtual) 的方法：
           - `set_window_transparent`: 窗口透明化。
           - `set_render_mask`: 异形窗口点击穿透。
           - 默认实现会记录一条警告日志，表明该功能在当前适配器下不可用。
    """

    @abstractmethod
    def run_javascript(self, script: str) -> None:
        """
        [必须] 在底层的 Web 视图中执行 JavaScript 代码。
        
        此方法应是“发后即忘”(Fire-and-forget) 的，或者通过回调机制（在实现内部处理）。
        控制器层期望此方法调用后能尽快返回，不阻塞 Python 线程。
        
        异常处理:
            实现类应当捕获所有可能的底层异常（如 WebView 崩溃、未初始化），
            并记录错误日志，严禁抛出异常导致控制器崩溃。

        Args:
            script (str): 要执行的 JavaScript 代码字符串。
        """
        pass
    
    @abstractmethod
    def register_python_bridge(self, bridge_obj: Any, name: str) -> None:
        """
        [必须] 将 Python 对象注入到 JavaScript 全局环境中。
        
        这是实现 Python -> JS -> Python 异步回环的关键。
        
        在 Qt 环境下，通常使用 `QWebChannel` 实现。
        在其他环境（如 CEF），可能使用 `BindObject` 等机制。
        
        Args:
            bridge_obj (Any): 要注入的 Python 对象（通常继承自 QObject）。
            name (str): 在 JS `window` 对象下的属性名（例如 "py_api"）。
        """
        pass

    def set_window_transparent(self, transparent: bool) -> None:
        """
        [可选] 设置顶层窗口的背景透明属性。
        
        用于实现“桌面挂件”模式。如果具体的 UI 框架不支持透明窗口
        （例如在浏览器中运行，或受限于系统合成器），可保持默认实现。
        
        Args:
            transparent (bool): True 为透明（无边框、背景穿透），False 为不透明。
        """
        self._log_not_implemented("set_window_transparent")

    def set_mouse_pass_through(self, enable: bool) -> None:
        """
        [可选] 设置整个窗口的鼠标穿透属性。
        
        开启后，所有鼠标事件（点击、移动）都应直接传递给下层窗口。
        注意：这与 `set_render_mask` 不同，后者是基于像素区域的精细控制。
        
        Args:
            enable (bool): 是否开启全窗口穿透。
        """
        self._log_not_implemented("set_mouse_pass_through")

    def set_render_mask(self, rects: List[List[int]]) -> None:
        """
        [可选] 设置窗口的异形渲染遮罩 (Mask)，用于实现像素级点击穿透。
        
        控制器会定期计算模型当前的非透明区域，并通过此方法传递给视图。
        视图层应利用这些矩形区域设置窗口的输入遮罩 (Input Mask)。
        在遮罩内的区域接收鼠标事件，遮罩外的区域鼠标穿透到桌面。
        
        Args:
            rects (List[List[int]]): 矩形列表，格式为 `[[x, y, w, h], ...]`。
                                     坐标系基于 WebView 内容区域。
        """
        self._log_not_implemented("set_render_mask")

    def get_ui_object(self) -> Any:
        """
        [可选] 获取底层的 UI 控件对象实例。
        
        在某些情况下（如 Factory 模式组装），外部可能需要访问真实的
        QWidget 或其他控件对象。
        
        Returns:
            Any: 底层 UI 对象。如果不适用，返回 None。
        """
        self._log_not_implemented("get_ui_object")
        return None

    def _log_not_implemented(self, method_name: str) -> None:
        """内部辅助方法：记录“功能未实现”的警告日志。"""
        adapter_name = self.__class__.__name__
        logger.warning(f"ViewAdapter '{adapter_name}' 未实现可选功能 '{method_name}'，该调用已被忽略。")
