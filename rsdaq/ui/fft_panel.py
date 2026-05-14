"""FFT view computed over the most recent N samples of the live ring buffer."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QSpinBox,
    QVBoxLayout, QWidget,
)

from rsdaq.config import FFTWindow
from rsdaq.core.ringbuffer import RingBuffer
from .plot_panel import CHANNEL_COLORS


_VALID_SIZES = [256, 512, 1024, 2048, 4096, 8192, 16384, 32768]


def _window(name: FFTWindow, n: int) -> np.ndarray:
    if name is FFTWindow.HANN:
        return np.hanning(n)
    if name is FFTWindow.HAMMING:
        return np.hamming(n)
    if name is FFTWindow.BLACKMAN:
        return np.blackman(n)
    return np.ones(n)


class FFTPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self._labels: List[str] = []
        self._channel_addr_ch: List[tuple] = []
        self._sample_rate: float = 1.0
        self._buffer: Optional[RingBuffer] = None
        self._curves: List[pg.PlotDataItem] = []

        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QGroupBox("Spectrum settings")
        form = QFormLayout(controls)
        self.size_combo = QComboBox()
        for s in _VALID_SIZES:
            self.size_combo.addItem(str(s), s)
        self.size_combo.setCurrentIndex(_VALID_SIZES.index(4096))
        form.addRow("FFT size:", self.size_combo)

        self.window_combo = QComboBox()
        for w in FFTWindow:
            self.window_combo.addItem(w.value, w)
        form.addRow("Window:", self.window_combo)

        self.log_check = QCheckBox("Log magnitude (dBFS)")
        self.log_check.setChecked(True)
        form.addRow("", self.log_check)

        layout.addWidget(controls)

        self._plot = pg.PlotWidget(background="#15171c")
        self._plot.setLabel("left", "Magnitude", units="dB",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.setLabel("bottom", "Frequency", units="Hz",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("left").setTextPen(pg.mkPen("#c8cdd9"))
        self._plot.getAxis("bottom").setTextPen(pg.mkPen("#c8cdd9"))
        layout.addWidget(self._plot, 1)

        # Live updates
        self.size_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.window_combo.currentIndexChanged.connect(self._on_settings_changed)
        self.log_check.toggled.connect(self._on_settings_changed)

    def _on_settings_changed(self, *_args) -> None:
        self._update_axes()

    # ----------------------------------------------------------- public API
    def configure(self, channel_order, labels: List[str], sample_rate_hz: float,
                  buffer: RingBuffer) -> None:
        self._plot.clear()
        self._curves = []
        self._labels = list(labels)
        self._channel_addr_ch = list(channel_order)  # list[(addr, ch)]
        self._sample_rate = float(sample_rate_hz)
        self._buffer = buffer
        for i, lbl in enumerate(self._labels):
            addr, ch = self._channel_addr_ch[i] if i < len(self._channel_addr_ch) else (0, 0)
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color, width=1.4)
            curve = self._plot.plot([], [], pen=pen, name=lbl)
            self._curves.append(curve)
        self._update_axes()

    def clear(self) -> None:
        for c in self._curves:
            c.setData([], [])

    def _current_size(self) -> int:
        return int(self.size_combo.currentData())

    def _current_window(self) -> FFTWindow:
        return FFTWindow(self.window_combo.currentData())

    def _update_axes(self) -> None:
        self._plot.setLabel("left", "Magnitude",
                            units="dB" if self.log_check.isChecked() else "V")

    def refresh(self) -> None:
        if self._buffer is None or not self._curves:
            return
        data, _total = self._buffer.snapshot()
        n_avail = data.shape[0]
        if n_avail == 0:
            return
        n = min(self._current_size(), n_avail)
        if n < 32:
            return
        # Use a power-of-two trim (not strictly required but cleaner).
        n = 1 << (n.bit_length() - 1)
        seg = data[-n:]
        win = _window(self._current_window(), n)
        # Coherent gain correction so amplitudes are comparable.
        coherent_gain = win.sum() / n if win.sum() > 0 else 1.0

        windowed = seg * win[:, None]
        spec = np.fft.rfft(windowed, axis=0)
        mag = np.abs(spec) * (2.0 / n) / coherent_gain
        freqs = np.fft.rfftfreq(n, d=1.0 / self._sample_rate)

        if self.log_check.isChecked():
            # 0 dBFS reference = INPUT_RANGE_V
            from rsdaq.config import INPUT_RANGE_V
            ref = max(INPUT_RANGE_V, 1e-9)
            y = 20 * np.log10(np.maximum(mag, 1e-12) / ref)
        else:
            y = mag

        for i, curve in enumerate(self._curves):
            if i >= y.shape[1]:
                break
            curve.setData(freqs, y[:, i])
