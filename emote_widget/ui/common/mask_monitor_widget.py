from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPaintEvent
from PySide6.QtCore import Qt, Slot, QRectF
from typing import Optional, List, Any

class MaskMonitorWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Mask Monitor")
        self.resize(400, 300)
        
        self.rects: List[List[int]] = []
        self.canvas_width: int = 1920
        self.canvas_height: int = 1080
        
        # Style
        self.bg_color = QColor(30, 30, 30)
        self.rect_fill_color = QColor(255, 0, 0, 150)
        self.rect_border_color = QColor(255, 100, 100)
        self.text_color = QColor(255, 255, 255)

    @Slot(list, int, int)
    def update_mask(self, rects: List[Any], width: int, height: int):
        """
        Update the mask data and repaint the widget.
        
        Args:
            rects: List of [x, y, w, h]
            width: Canvas width
            height: Canvas height
        """
        self.rects = rects
        if width > 0 and height > 0:
            self.canvas_width = width
            self.canvas_height = height
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw Background
        painter.fillRect(self.rect(), self.bg_color)
        
        if not self.rects:
            painter.setPen(self.text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Mask Data")
            return

        # Calculate Scale to fit window while maintaining aspect ratio
        win_w = self.width()
        win_h = self.height()
        
        scale_x = win_w / self.canvas_width
        scale_y = win_h / self.canvas_height
        scale = min(scale_x, scale_y) * 0.9 # 0.9 for padding
        
        # Calculate offset to center
        draw_w = self.canvas_width * scale
        draw_h = self.canvas_height * scale
        offset_x = (win_w - draw_w) / 2
        offset_y = (win_h - draw_h) / 2
        
        # Draw Border for Canvas Area
        painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.PenStyle.DashLine))
        # Use QRectF for floating point coordinates
        painter.drawRect(QRectF(offset_x, offset_y, draw_w, draw_h))

        # Draw Rects
        painter.setPen(QPen(self.rect_border_color, 1))
        painter.setBrush(QBrush(self.rect_fill_color))
        
        for r in self.rects:
            if len(r) < 4: continue
            # r is [x, y, w, h]
            x, y, w, h = r[0], r[1], r[2], r[3]
            
            # Map to view coordinates
            vx = offset_x + x * scale
            vy = offset_y + y * scale
            vw = w * scale
            vh = h * scale
            
            painter.drawRect(QRectF(vx, vy, vw, vh))
            
        # Draw Info
        painter.setPen(self.text_color)
        info_text = f"Rect Count: {len(self.rects)}\nCanvas: {self.canvas_width}x{self.canvas_height}"
        painter.drawText(10, 20, info_text)
