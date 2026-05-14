"""MCC134 (thermocouple) panel.

Self-contained: owns its own QTimer that polls the backend a few times a
second, displays per-channel temperature + CJC and a slow rolling plot.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from rsdaq.config import NUM_CHANNELS_134
from rsdaq.daq.backend import ThermocoupleBackend
from .plot_panel import CHANNEL_COLORS

TC_TYPES = ["DISABLED", "J", "K", "T", "E", "R", "S", "B", "N"]


class ThermocouplePanel(QWidget):
    """Operates an open MCC134 (or simulator) at one address."""

    HEADERS = ["Channel", "Type", "Temperature", "CJC"]

    def __init__(self, backend: ThermocoupleBackend, address: int, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._address = address
        self._poll_ms = 500
        self._history_seconds = 600
        self._times: Deque[float] = deque()
        self._series: List[Deque[float]] = [deque() for _ in range(NUM_CHANNELS_134)]
        self._t = 0.0
        self._build()
        # Reasonable defaults
        for ch in range(NUM_CHANNELS_134):
            type_combo: QComboBox = self.table.cellWidget(ch, 1)  # type: ignore
            type_combo.setCurrentText("K")
            self._on_type_changed(ch, "K")
        self._timer = QTimer(self)
        self._timer.setInterval(self._poll_ms)
        self._timer.timeout.connect(self._poll)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        info = QLabel(f"<b>MCC134</b> at address #{self._address}")
        layout.addWidget(info)

        self.table = QTableWidget(NUM_CHANNELS_134, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        for i in range(len(self.HEADERS)):
            h.setSectionResizeMode(i, QHeaderView.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for ch in range(NUM_CHANNELS_134):
            self.table.setItem(ch, 0, _ro(f"CH{ch}"))
            combo = QComboBox()
            combo.addItems(TC_TYPES)
            combo.currentTextChanged.connect(
                lambda txt, c=ch: self._on_type_changed(c, txt))
            self.table.setCellWidget(ch, 1, combo)
            self.table.setItem(ch, 2, _val("--"))
            self.table.setItem(ch, 3, _val("--"))
        layout.addWidget(self.table)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Poll (ms):"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(100, 5000)
        self.poll_spin.setSingleStep(100)
        self.poll_spin.setValue(self._poll_ms)
        self.poll_spin.valueChanged.connect(self._on_poll_changed)
        controls.addWidget(self.poll_spin)
        controls.addStretch(1)
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        layout.addLayout(controls)

        # Plot
        self._plot = pg.PlotWidget(background="#15171c")
        self._plot.setLabel("left", "Temperature", units="°C",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.setLabel("bottom", "Time", units="s",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("left").setTextPen(pg.mkPen("#c8cdd9"))
        self._plot.getAxis("bottom").setTextPen(pg.mkPen("#c8cdd9"))
        self._curves = []
        for ch in range(NUM_CHANNELS_134):
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color, width=1.6)
            self._curves.append(self._plot.plot([], [], pen=pen, name=f"CH{ch}"))
        layout.addWidget(self._plot, 1)

    # -------------------------------------------------------- event handlers
    def _on_type_changed(self, channel: int, tc_type: str) -> None:
        try:
            self._backend.set_tc_type(channel, tc_type)
        except Exception:
            pass

    def _on_poll_changed(self, ms: int) -> None:
        self._poll_ms = ms
        self._timer.setInterval(ms)

    def _on_start(self) -> None:
        try:
            self._backend.open(self._address)
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Open failed", str(exc))
            return
        # Re-apply tc types
        for ch in range(NUM_CHANNELS_134):
            combo: QComboBox = self.table.cellWidget(ch, 1)  # type: ignore
            self._on_type_changed(ch, combo.currentText())
        self._timer.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_stop(self) -> None:
        self._timer.stop()
        try:
            self._backend.close()
        except Exception:
            pass
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    # ------------------------------------------------------------ polling
    def _poll(self) -> None:
        temps = self._backend.read_temperatures()
        cjcs = self._backend.read_cjc()
        self._t += self._poll_ms / 1000.0
        # Trim history to roughly the configured window.
        max_points = max(60, int(self._history_seconds / (self._poll_ms / 1000.0)))
        self._times.append(self._t)
        if len(self._times) > max_points:
            self._times.popleft()
        for ch in range(NUM_CHANNELS_134):
            t_val = temps[ch]
            c_val = cjcs[ch]
            self.table.item(ch, 2).setText(
                "open" if t_val is None else f"{t_val:+8.3f} °C")
            self.table.item(ch, 3).setText(
                "--" if c_val is None else f"{c_val:+8.3f} °C")
            v = float("nan") if t_val is None else float(t_val)
            self._series[ch].append(v)
            if len(self._series[ch]) > max_points:
                self._series[ch].popleft()
            xs = list(self._times)[-len(self._series[ch]):]
            self._curves[ch].setData(xs, list(self._series[ch]))


def _ro(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(Qt.AlignCenter)
    return it


def _val(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it
