from PySide6.QtCore import QObject, Signal, Slot
from emote_widget.utils.logger import emote_widget_logger as logger
# ------------------------------------------------------------------------------
#  内部通信桥梁
# ------------------------------------------------------------------------------
class _PythonApiBridge(QObject):
    """一个私有类，作为从 JavaScript 到 Python 的通信桥梁。"""
    # 当 JS 调用 on_player_ready 时，它会携带动画列表并被发射
    player_ready_signal = Signal(list)

    on_character_clicked_signal = Signal()

    on_character_hovered_signal = Signal()

    def __init__(self,widget=None):
        super().__init__()

    @Slot(list)
    def on_player_ready(self, timelines):
        """这个 @Slot 装饰器使该方法可以被 JavaScript 调用。"""
        logger.info(f"--> _PythonApiBridge.on_player_ready Slot CALLED by JS. Timelines count: {len(timelines)}")
        self.player_ready_signal.emit(timelines)
        
    @Slot()
    def js_on_character_click(self):
        """当 JS 检测到 canvas 被点击时调用此函数。"""
        self.on_character_clicked_signal.emit()

    @Slot()
    def js_on_character_hover(self):
        """当 JS 检测到 canvas 被长悬停时调用此函数。"""
        self.on_character_hovered_signal.emit()

    @Slot(str, str)
    def on_js_error(self, message, stack):
        """接收来自 JavaScript 的错误并记录。"""
        logger.error(f"[JavaScript Error]\n  Message: {message}\n  Stack: {stack}")