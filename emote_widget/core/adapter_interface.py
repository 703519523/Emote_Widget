from abc import ABC, abstractmethod
from typing import Any
from emote_widget.utils.logger import emote_widget_logger as logger

class IViewAdapter(ABC):
    """
    视图适配器接口。
    
    分为两类方法：
    1. 核心方法 (@abstractmethod): 子类必须实现，否则无法运行。
    2. 可选能力 (普通方法): 子类可按需覆盖。若不覆盖，调用时会打印日志但不崩溃。
    """

    @abstractmethod
    def run_javascript(self, script: str) -> None:
        """
        必须实现：在底层 Web 视图中执行 JS 代码。
        不允许抛出异常，失败应记录日志。

        由于废弃了直接回调机制，现在所有带返回值的 JS 调用
        都通过 Bridge 的信号机制来处理。
        """
        pass
    
    @abstractmethod
    def register_python_bridge(self, bridge_obj: Any, name: str) -> None:
        """
        [必须]
        注入 Python 对象到 JS 环境 (QWebChannel 或其他机制)
        bridge_obj: 通常是 QObject
        name: 在 window 对象下的名字，如 'py_api'
        """
        pass

    def set_window_transparent(self, transparent: bool) -> None:
        """
        [可选] 设置顶层窗口透明/穿透。
        如果具体的 UI 框架（如 Web 浏览器、简单的 Frame）不支持，可不实现。
        """
        self._log_not_implemented("set_window_transparent")

    def set_mouse_pass_through(self, enable: bool) -> None:
        """
        [可选] 设置鼠标穿透。
        """
        self._log_not_implemented("set_mouse_pass_through")

    def set_render_mask(self, rects: list[list[int]]) -> None:
        """
        [可选] 设置渲染区域掩码 (用于点击穿透)。
        rects: [[x, y, w, h], ...] 矩形列表
        """
        self._log_not_implemented("set_render_mask")

    def get_ui_object(self) -> Any:
        """
        [可选] 返回底层的 UI 控件对象。
        用于 Factory 组装。如果不实现，Factory 可能会直接返回 Adapter 实例本身。
        """
        self._log_not_implemented("set_mouse_pass_through")
        return None

    def _log_not_implemented(self, method_name: str):
        """记录未实现的警告"""
        adapter_name = self.__class__.__name__
        logger.warning(f"Adapter '{adapter_name}' 未实现可选功能 '{method_name}'，调用已被忽略。")