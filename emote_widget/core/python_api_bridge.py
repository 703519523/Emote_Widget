"""
EmoteWidget Python API 桥接模块。

本模块定义了 `PythonApiBridge` 类，作为 JavaScript (WebEngine) 环境与 Python 原生环境之间的通信枢纽。
它利用 Qt 的 `QWebChannel` 机制，将 Python 对象暴露给 JS，使得前端可以调用后端的方法。

主要职责:
    - **消息中转**: 接收 JS 发出的信号（如点击、加载完成）并转发给 Controller。
    - **异步回环**: 配合 Controller 的 `_safe_query` 机制，接收异步 JS 函数调用的返回值。
    - **错误上报**: 将 JS 端的未捕获异常传递给 Python 日志系统。
    - **数据传输**: 接收高频的 Mask 数据（用于点击穿透）。
"""

from typing import Optional, List
from PySide6.QtCore import QObject, Signal, Slot
from emote_widget.utils.logger import emote_widget_logger as logger

class PythonApiBridge(QObject):
    """
    [通信桥梁] 暴露给 JavaScript 环境的 Python 对象。
    
    在 JS 端，该对象通常被命名为 `py_api`。
    
    安全注意事项 (Security Note):
        由于此对象的方法可以被任意 JS 代码调用，因此必须严格限制暴露的方法 (@Slot)。
        不要暴露任何可能导致系统命令执行或敏感文件读取的方法。
    """
    
    # --- 信号定义 (Python 内部使用) ---
    
    player_ready_signal = Signal(list)
    """当 JS 端模型加载就绪时发射。参数: timelines (list[str])"""

    on_character_clicked_signal = Signal()
    """当 JS 端检测到点击事件时发射。"""

    on_character_hovered_signal = Signal()
    """当 JS 端检测到悬停事件时发射。"""

    query_result_signal = Signal(str, str)
    """通用查询回传信号。参数: (request_id: str, result_json: str)"""

    render_mask_updated_signal = Signal(str)
    """渲染掩码更新信号。参数: (mask_data_json: str)"""

    def __init__(self, controller: Optional[QObject] = None) -> None:
        """
        初始化桥接对象。
        
        Args:
            controller (QObject, optional): 持有此桥接对象的控制器实例。
                                          主要用于防止被过早垃圾回收。
        """
        super().__init__()
        self._controller = controller

    # --- 槽函数 (暴露给 JS 的 API) ---

    @Slot(list)
    def on_player_ready(self, timelines: List[str]) -> None:
        """
        [JS调用] 通知 Python 模型加载已完成。
        
        JS 代码: `py_api.on_player_ready(["idle", "touch_head"])`
        """
        logger.info(f"--> [Bridge] on_player_ready called. Timelines count: {len(timelines)}")
        self.player_ready_signal.emit(timelines)
    
    @Slot(str, str) 
    def receive_query_result(self, request_id: str, result_json: str) -> None:
        """
        [JS调用] 接收异步查询的结果。
        
        配合 Controller 中的 `_safe_query` 使用，实现 UUID 匹配的回调机制。
        
        Args:
            request_id (str): 查询请求的唯一标识符。
            result_json (str): JSON 格式的查询结果字符串。
        """
        # 频繁调用的日志级别设为 debug，避免刷屏
        logger.debug(f"--> [Bridge] receive_query_result: {request_id[:8]}...")
        self.query_result_signal.emit(request_id, result_json)
        
    @Slot()
    def js_on_character_click(self) -> None:
        """[JS调用] 当 Canvas 被点击时触发。"""
        self.on_character_clicked_signal.emit()

    @Slot()
    def js_on_character_hover(self) -> None:
        """[JS调用] 当 Canvas 被长悬停时触发。"""
        self.on_character_hovered_signal.emit()

    @Slot(str, str)
    def on_js_error(self, message: str, stack: str) -> None:
        """
        [JS调用] 接收 JS 端的错误信息。
        
        这对于调试 WebEngine 中的问题非常有帮助，因为 WebView 的控制台日志
        通常不容易直接看到。
        """
        logger.error(f"[JavaScript Error]\n  Message: {message}\n  Stack: {stack}")

    @Slot(str)
    def receive_render_mask(self, mask_json: str) -> None:
        """
        [JS调用] 接收高频的渲染区域掩码数据。
        
        用于实现点击穿透功能。此方法会被 JS 端的 `MaskSampler` 定期调用。
        
        Args:
            mask_json (str): 包含 rects 列表的 JSON 字符串。
        """
        # 极高频调用，默认不记录日志
        self.render_mask_updated_signal.emit(mask_json)
