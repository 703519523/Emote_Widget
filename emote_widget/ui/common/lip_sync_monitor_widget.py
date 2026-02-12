# emote_widget/ui/common/monitor_widget.py

from collections import deque
from typing import Optional, Dict
from PySide6.QtCore import Qt, Slot, QPointF
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QPolygonF, QPaintEvent, 
                          QPainter as QPainterClass)
from PySide6.QtWidgets import QWidget

class LipSyncMonitorWidget(QWidget):
    _custom_font: QFont
    """
    [Qt 特有实现] 口型同步调试监视器
    只在基于 QtWidgets 的环境中使用。
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("音频同步监视器")
        self.setMinimumHeight(120)
        self.resize(400, 150)
        
        # 数据历史
        self.history_len = 200
        self.rms_history: deque[float] = deque(maxlen=self.history_len)
        self.threshold_history: deque[float] = deque(maxlen=self.history_len)
        
        # 当前状态
        self.current_peak = 0.0
        self.current_mean = 0.0
        self.max_val_seen = 0.1
        
        # 样式配置
        self.bg_color = QColor("#1E1E1E")
        self.mean_color = QColor("#4A90E2")
        self.peak_color = QColor("#F5A623")
        self.rms_color = QColor("#7ED321")
        self.threshold_color = QColor("#D0021B")
        self.text_color = QColor("#DDDDDD")
        self.grid_color = QColor("#444444")
        self._custom_font = QFont("Arial", 8)

    @Slot(dict)
    def update_data(self, data: Dict[str, float]):
        """
        槽函数：接收来自 Controller 的纯数据字典
        """
        rms = data.get("rms", 0.0)
        mean = data.get("mean", 0.0)
        peak = data.get("peak", 0.0)
        threshold = data.get("threshold", 0.0)
        
        self.rms_history.append(rms)
        self.threshold_history.append(threshold)
        self.current_mean = mean
        self.current_peak = peak
        
        # 动态调整 Y 轴比例
        self.max_val_seen = max(self.max_val_seen, peak, rms) * 0.995
        
        self.update() # 触发重绘

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainterClass.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.bg_color)
        
        w, h = self.width(), self.height()
        padding = 10
        label_area_height = 15
        chart_height = h - padding - label_area_height
        
        if chart_height <= 0:
            painter.end()
            return

        y_scale = chart_height / (self.max_val_seen + 1e-6)
        chart_y_origin = padding + chart_height

        # 1. 绘制网格线
        painter.setPen(self.grid_color)
        for i in range(1, 4):
            y = padding + chart_height * (i / 4.0)
            painter.drawLine(padding, int(y), w - padding, int(y))

        # 2. 绘制柱状图 (Mean & Peak)
        bar_width = 30
        mean_h = self.current_mean * y_scale
        peak_h = self.current_peak * y_scale
        
        painter.fillRect(padding + 10, int(chart_y_origin - mean_h), bar_width, int(mean_h), self.mean_color)
        painter.fillRect(padding + 50, int(chart_y_origin - peak_h), bar_width, int(peak_h), self.peak_color)

        if not self.rms_history:
            painter.end()
            return

        # 3. 绘制 RMS 曲线
        self._draw_polyline(painter, self.rms_history, self.rms_color, chart_y_origin, y_scale, w, padding)
        
        # 4. 绘制 阈值 虚线
        self._draw_polyline(painter, self.threshold_history, self.threshold_color, chart_y_origin, y_scale, w, padding, is_dash=True)

        # 5. 绘制文字
        painter.setFont(self._custom_font)
        painter.setPen(self.text_color)
        painter.drawText(padding + 10, h - 2, f"Mean: {self.current_mean:.3f}")
        painter.drawText(padding + 90, h - 2, f"Peak: {self.current_peak:.3f}")
        
        # 图例
        legend_y = padding + 10
        painter.drawText(w - 80, legend_y, f"RMS: {self.rms_history[-1]:.3f}")
        painter.drawText(w - 80, legend_y + 12, f"Thres: {self.threshold_history[-1]:.3f}")

        painter.end()

    def _draw_polyline(self, painter: QPainter, data: deque[float], color: QColor, 
                      y_origin: float, y_scale: float, w: int, padding: int, 
                      is_dash: bool = False) -> None:
        pen = QPen(color, 1.5)
        if is_dash: pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        points = QPolygonF()
        step = (w - 2 * padding) / (self.history_len - 1)
        
        for i, val in enumerate(data):
            x = padding + i * step
            y = y_origin - val * y_scale
            points.append(QPointF(x, y))
        painter.drawPolyline(points)