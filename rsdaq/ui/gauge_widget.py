"""Custom widgets for non-graph visualisations: vertical bar + radial gauge."""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QBrush, QLinearGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget


# Re-use the same channel palette for consistency with the graph.
DEFAULT_FG = "#5a8dee"
PANEL_BG = "#15171c"
GROOVE_BG = "#2a2e3a"
TEXT_COLOR = "#e6e6e6"
MUTED_COLOR = "#8a90a0"


class _BaseValueWidget(QWidget):
    """Common state for bar + gauge."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._value: float = 0.0
        self._minimum: float = 0.0
        self._maximum: float = 1.0
        self._unit: str = "V"
        self._title: str = ""
        self._color: QColor = QColor(DEFAULT_FG)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_range(self, minimum: float, maximum: float) -> None:
        if maximum <= minimum:
            maximum = minimum + 1.0
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self.update()

    def set_unit(self, unit: str) -> None:
        self._unit = str(unit)
        self.update()

    def set_title(self, title: str) -> None:
        self._title = str(title)
        self.update()

    def set_color(self, color) -> None:
        self._color = QColor(color)
        self.update()

    def set_value(self, value: float) -> None:
        self._value = float(value)
        self.update()

    def value(self) -> float:
        return self._value

    def _fraction(self) -> float:
        rng = self._maximum - self._minimum
        if rng == 0:
            return 0.0
        return max(0.0, min(1.0, (self._value - self._minimum) / rng))


class BarWidget(_BaseValueWidget):
    """Compact vertical bar gauge with min/max labels and current value."""

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(80, 160)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(110, 220)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(PANEL_BG))

        w = self.width()
        h = self.height()
        margin = 6
        title_h = 18
        value_h = 22
        scale_w = 36

        # Title
        p.setPen(QColor(TEXT_COLOR))
        title_font = QFont(p.font())
        title_font.setBold(True)
        p.setFont(title_font)
        p.drawText(QRectF(margin, margin, w - 2 * margin, title_h),
                   Qt.AlignHCenter | Qt.AlignVCenter, self._title)

        # Value text at bottom
        p.setPen(QColor(self._color))
        val_font = QFont(p.font())
        val_font.setPointSizeF(val_font.pointSizeF() + 1)
        val_font.setBold(True)
        p.setFont(val_font)
        value_text = f"{self._value:+.3f} {self._unit}"
        p.drawText(QRectF(margin, h - margin - value_h, w - 2 * margin, value_h),
                   Qt.AlignHCenter | Qt.AlignVCenter, value_text)

        # Bar groove
        groove_top = margin + title_h + 4
        groove_bottom = h - margin - value_h - 6
        groove_h = max(20.0, groove_bottom - groove_top)
        groove_x = (w - 2 * margin - scale_w) / 2 + margin
        groove_w = max(10.0, w - 2 * margin - scale_w - margin)

        groove_rect = QRectF(groove_x, groove_top, groove_w, groove_h)
        p.setBrush(QColor(GROOVE_BG))
        p.setPen(QPen(QColor("#3a3f50"), 1))
        p.drawRoundedRect(groove_rect, 4, 4)

        # Filled portion
        frac = self._fraction()
        fill_h = groove_h * frac
        fill_rect = QRectF(groove_x, groove_top + (groove_h - fill_h), groove_w, fill_h)
        gradient = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
        gradient.setColorAt(0.0, self._color)
        gradient.setColorAt(1.0, self._color.darker(150))
        p.setBrush(QBrush(gradient))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(fill_rect, 4, 4)

        # Tick labels (min, mid, max)
        p.setPen(QColor(MUTED_COLOR))
        tick_font = QFont(p.font())
        tick_font.setBold(False)
        tick_font.setPointSizeF(max(7.5, tick_font.pointSizeF() - 2))
        p.setFont(tick_font)
        scale_x = groove_x + groove_w + 6
        scale_w_actual = w - margin - scale_x
        for frac_t, val in (
            (0.0, self._maximum),
            (0.5, (self._maximum + self._minimum) / 2),
            (1.0, self._minimum),
        ):
            y = groove_top + groove_h * frac_t
            p.drawText(
                QRectF(scale_x, y - 8, scale_w_actual, 16),
                Qt.AlignVCenter | Qt.AlignLeft, f"{val:.2f}",
            )

        p.end()


class GaugeWidget(_BaseValueWidget):
    """270-degree radial gauge (12 o'clock = no value, sweeping clockwise)."""

    def minimumSizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(150, 130)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(220, 200)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor(PANEL_BG))

        w = self.width()
        h = self.height()
        size = min(w, h) - 20
        cx = w / 2
        cy = h / 2 + 6  # leave room for title above
        radius = size / 2
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)

        # Title above
        p.setPen(QColor(TEXT_COLOR))
        title_font = QFont(p.font())
        title_font.setBold(True)
        p.setFont(title_font)
        p.drawText(
            QRectF(0, 2, w, 18),
            Qt.AlignHCenter | Qt.AlignVCenter, self._title,
        )

        # Sweep angles: Qt uses 1/16th degree, 0 at 3 o'clock, ccw positive.
        # We want a 240-deg sweep starting at 210 deg (lower-left) and ending at -30 deg (lower-right),
        # i.e. start_angle=210, span=-240 (clockwise).
        start_angle = 210
        full_span = -240

        # Background arc
        pen_bg = QPen(QColor(GROOVE_BG), max(8.0, radius * 0.16))
        pen_bg.setCapStyle(Qt.FlatCap)
        p.setPen(pen_bg)
        p.drawArc(rect, start_angle * 16, full_span * 16)

        # Value arc
        frac = self._fraction()
        pen_fg = QPen(self._color, max(8.0, radius * 0.16))
        pen_fg.setCapStyle(Qt.FlatCap)
        p.setPen(pen_fg)
        p.drawArc(rect, start_angle * 16, int(full_span * frac) * 16)

        # Centered value text
        p.setPen(QColor(self._color))
        val_font = QFont(p.font())
        val_font.setBold(True)
        val_font.setPointSizeF(max(11.0, radius * 0.22))
        p.setFont(val_font)
        value_text = f"{self._value:+.2f}"
        p.drawText(rect, Qt.AlignHCenter | Qt.AlignVCenter, value_text)

        # Unit beneath value
        p.setPen(QColor(MUTED_COLOR))
        unit_font = QFont(p.font())
        unit_font.setBold(False)
        unit_font.setPointSizeF(max(8.0, radius * 0.13))
        p.setFont(unit_font)
        unit_rect = QRectF(rect)
        unit_rect.translate(0, radius * 0.30)
        p.drawText(unit_rect, Qt.AlignHCenter | Qt.AlignVCenter, self._unit)

        # Min/Max labels
        tick_font = QFont(p.font())
        tick_font.setPointSizeF(max(7.5, radius * 0.10))
        p.setFont(tick_font)
        # min: at start_angle (210 deg)
        for label_val, deg in ((self._minimum, 210), (self._maximum, -30)):
            rad = math.radians(deg)
            tx = cx + math.cos(rad) * (radius + 8)
            ty = cy - math.sin(rad) * (radius + 8)
            p.drawText(
                QRectF(tx - 30, ty - 8, 60, 16),
                Qt.AlignHCenter | Qt.AlignVCenter, f"{label_val:.1f}",
            )

        p.end()


__all__ = ["BarWidget", "GaugeWidget", "VizStyle"]
from rsdaq.display import VizStyle  # noqa: E402,F401  re-export
