"""Real-time scrolling plot built on pyqtgraph."""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from rsdaq.core.ringbuffer import RingBuffer

# 8 high-contrast colours (one per channel index 0..7).
CHANNEL_COLORS = [
    "#5a8dee", "#ff7043", "#66bb6a", "#ab47bc",
    "#ffca28", "#26c6da", "#ec407a", "#9ccc65",
]


class PlotPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, useOpenGL=False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget(background="#15171c")
        self._plot.setLabel("left", "Voltage", units="V",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.setLabel("bottom", "Time", units="s",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("left").setTextPen(pg.mkPen("#c8cdd9"))
        self._plot.getAxis("bottom").setTextPen(pg.mkPen("#c8cdd9"))
        layout.addWidget(self._plot)

        self._curves: List[pg.PlotDataItem] = []
        self._labels: List[str] = []
        self._channel_order: List[Tuple[int, int]] = []
        self._sample_rate: float = 1.0
        self._buffer: Optional[RingBuffer] = None
        self._trigger_line: Optional[pg.InfiniteLine] = None
        self._trigger_level: Optional[pg.InfiniteLine] = None

    def configure(self, channel_order: List[Tuple[int, int]], labels: List[str],
                  sample_rate_hz: float, buffer: RingBuffer,
                  trigger_level_v: Optional[float] = None) -> None:
        self._plot.clear()
        self._curves = []
        self._labels = list(labels)
        self._channel_order = list(channel_order)
        self._sample_rate = float(sample_rate_hz)
        self._buffer = buffer
        for i, lbl in enumerate(self._labels):
            _addr, ch = self._channel_order[i] if i < len(self._channel_order) else (0, i)
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color, width=1.6)
            curve = self._plot.plot([], [], pen=pen, name=lbl)
            self._curves.append(curve)
        self._trigger_line = None
        if trigger_level_v is not None:
            self._trigger_level = pg.InfiniteLine(
                pos=trigger_level_v, angle=0,
                pen=pg.mkPen("#ff8a65", width=1, style=pg.QtCore.Qt.DashLine))
            self._plot.addItem(self._trigger_level)
        else:
            self._trigger_level = None

    def clear(self) -> None:
        for c in self._curves:
            c.setData([], [])

    def mark_trigger(self, t_seconds: float) -> None:
        if self._trigger_line is not None:
            self._plot.removeItem(self._trigger_line)
        self._trigger_line = pg.InfiniteLine(
            pos=t_seconds, angle=90,
            pen=pg.mkPen("#ff8a65", width=1.5, style=pg.QtCore.Qt.DashLine))
        self._plot.addItem(self._trigger_line)

    def refresh(self) -> None:
        if self._buffer is None or not self._curves:
            return
        data, total = self._buffer.snapshot()
        n = data.shape[0]
        if n == 0:
            return
        t_end = total / self._sample_rate
        t_start = t_end - n / self._sample_rate
        x = np.linspace(t_start, t_end, n, endpoint=False)
        for i, curve in enumerate(self._curves):
            if i < data.shape[1]:
                curve.setData(x, data[:, i])
