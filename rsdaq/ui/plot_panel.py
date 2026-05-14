"""Real-time scrolling plot built on pyqtgraph."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QVBoxLayout, QWidget

from rsdaq.core.ringbuffer import RingBuffer

# 8 well-separated, high-contrast colours for the 8 MCC118 channels.
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
        self._channels: List[int] = []
        self._sample_rate: float = 1.0
        self._buffer: Optional[RingBuffer] = None

    def configure(self, channels: List[int], sample_rate_hz: float,
                  buffer: RingBuffer) -> None:
        self._plot.clear()
        self._curves = []
        self._channels = list(channels)
        self._sample_rate = float(sample_rate_hz)
        self._buffer = buffer
        for i, ch in enumerate(channels):
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color, width=1.6)
            curve = self._plot.plot([], [], pen=pen, name=f"CH {ch}")
            self._curves.append(curve)

    def clear(self) -> None:
        for c in self._curves:
            c.setData([], [])

    def refresh(self) -> None:
        if self._buffer is None or not self._curves:
            return
        data, total = self._buffer.snapshot()
        n = data.shape[0]
        if n == 0:
            return
        # Time axis ends at "now" and extends backwards `n / fs` seconds.
        t_end = total / self._sample_rate
        t_start = t_end - n / self._sample_rate
        x = np.linspace(t_start, t_end, n, endpoint=False)
        for i, curve in enumerate(self._curves):
            curve.setData(x, data[:, i])
