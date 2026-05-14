"""MCC172 (IEPE / vibration) panel.

Self-contained: owns its own QThread + worker, lets the user toggle IEPE
excitation and AC/DC coupling per channel, set a sigma-delta sample rate, and
view a live time-domain plot plus an FFT spectrum.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from rsdaq.config import (
    CouplingMode, IEPEChannelConfig, INPUT_RANGE_172_V, MAX_RATE_172_HZ,
    MIN_RATE_172_HZ, Mcc172AcquisitionConfig, Mcc172BoardSelection,
    NUM_CHANNELS_172, ScanMode,
)
from rsdaq.core.ringbuffer import RingBuffer
from rsdaq.daq.backend import ScanBackend
from .plot_panel import CHANNEL_COLORS

log = logging.getLogger(__name__)

REFRESH_MS = 50


class _VibrationWorker(QObject):
    started_ok = Signal()
    stopped = Signal(str)
    error = Signal(str)
    progress = Signal(int)

    def __init__(self, backend: ScanBackend, cfg: Mcc172AcquisitionConfig,
                 buffer: RingBuffer):
        super().__init__()
        self._backend = backend
        self._cfg = cfg
        self._buffer = buffer
        self._abort = False

    @Slot()
    def run(self) -> None:
        try:
            self._backend.start(self._cfg)
        except Exception as exc:
            log.exception("MCC172 start failed")
            self.error.emit(str(exc))
            return
        self.started_ok.emit()
        try:
            while not self._abort:
                r = self._backend.read(0.05)
                if r is None:
                    if not self._backend.is_running():
                        break
                    continue
                samples, total = r
                self._buffer.write(samples)
                self.progress.emit(int(total))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            try:
                self._backend.stop()
            except Exception:
                pass
            self.stopped.emit("aborted" if self._abort else "finished")

    @Slot()
    def request_stop(self) -> None:
        self._abort = True


class VibrationPanel(QWidget):
    """Operates an MCC172 (or its simulator) at one address."""

    def __init__(self, backend: ScanBackend, address: int, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._address = address
        self._buffer: Optional[RingBuffer] = None
        self._worker: Optional[_VibrationWorker] = None
        self._thread: Optional[QThread] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_MS)
        self._refresh_timer.timeout.connect(self._refresh_plots)
        self._build()

    # ------------------------------------------------------------------- UI
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>MCC172</b> at address #{self._address}"))
        header.addStretch(1)
        layout.addLayout(header)

        # ---- Per-channel config ----
        ch_group = QGroupBox("Channels")
        ch_layout = QHBoxLayout(ch_group)
        self._channel_widgets: List[dict] = []
        for ch in range(NUM_CHANNELS_172):
            box = QGroupBox(f"CH{ch}")
            f = QFormLayout(box)
            enabled = QCheckBox("Enable"); enabled.setChecked(True)
            iepe = QCheckBox("IEPE excitation")
            coupling = QComboBox(); coupling.addItems([m.value for m in CouplingMode])
            sens = QDoubleSpinBox()
            sens.setDecimals(3); sens.setRange(0.1, 100_000.0); sens.setValue(1000.0)
            unit = QComboBox()
            unit.addItems(["mV/V", "mV/g", "mV/Pa"])
            f.addRow("", enabled)
            f.addRow("", iepe)
            f.addRow("Coupling:", coupling)
            f.addRow("Sensitivity:", sens)
            f.addRow("Unit:", unit)
            ch_layout.addWidget(box)
            self._channel_widgets.append({
                "enabled": enabled, "iepe": iepe, "coupling": coupling,
                "sens": sens, "unit": unit,
            })
        layout.addWidget(ch_group)

        # ---- Acquisition controls ----
        acq_group = QGroupBox("Acquisition")
        acq_layout = QHBoxLayout(acq_group)
        form = QFormLayout()
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(MIN_RATE_172_HZ, MAX_RATE_172_HZ)
        self.rate_spin.setSingleStep(100); self.rate_spin.setValue(10_240.0)
        self.rate_spin.setSuffix(" Hz"); self.rate_spin.setDecimals(0)
        form.addRow("Sample rate:", self.rate_spin)
        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.1, 60.0); self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(2.0); self.window_spin.setSuffix(" s")
        form.addRow("Plot window:", self.window_spin)
        acq_layout.addLayout(form)
        acq_layout.addStretch(1)
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop"); self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        acq_layout.addWidget(self.start_btn)
        acq_layout.addWidget(self.stop_btn)
        layout.addWidget(acq_group)

        # ---- Plots ----
        splitter = QSplitter(Qt.Vertical)

        self._time_plot = pg.PlotWidget(background="#15171c")
        self._time_plot.setLabel("left", "Voltage", units="V",
                                 **{"color": "#c8cdd9", "font-size": "11pt"})
        self._time_plot.setLabel("bottom", "Time", units="s",
                                 **{"color": "#c8cdd9", "font-size": "11pt"})
        self._time_plot.showGrid(x=True, y=True, alpha=0.25)
        self._time_plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._time_plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._time_plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        splitter.addWidget(self._time_plot)

        self._fft_plot = pg.PlotWidget(background="#15171c")
        self._fft_plot.setLabel("left", "Magnitude", units="dB",
                                **{"color": "#c8cdd9", "font-size": "11pt"})
        self._fft_plot.setLabel("bottom", "Frequency", units="Hz",
                                **{"color": "#c8cdd9", "font-size": "11pt"})
        self._fft_plot.showGrid(x=True, y=True, alpha=0.25)
        self._fft_plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._fft_plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._fft_plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        splitter.addWidget(self._fft_plot)
        splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self._time_curves: List[pg.PlotDataItem] = []
        self._fft_curves: List[pg.PlotDataItem] = []
        self.status_label = QLabel("Idle")
        self.status_label.setProperty("role", "muted")
        layout.addWidget(self.status_label)

    # --------------------------------------------------------------- start
    def _collect_cfg(self) -> Mcc172AcquisitionConfig:
        channels: List[int] = []
        ch_cfgs: List[IEPEChannelConfig] = []
        for ch, w in enumerate(self._channel_widgets):
            ch_cfg = IEPEChannelConfig(
                iepe_enabled=w["iepe"].isChecked(),
                coupling=CouplingMode(w["coupling"].currentText()),
                sensitivity_mv_per_unit=float(w["sens"].value()),
            )
            ch_cfgs.append(ch_cfg)
            if w["enabled"].isChecked():
                channels.append(ch)
        cfg = Mcc172AcquisitionConfig(
            boards=[Mcc172BoardSelection(
                address=self._address,
                enabled_channels=channels,
                channel_configs=ch_cfgs)],
            sample_rate_hz=float(self.rate_spin.value()),
            plot_window_seconds=float(self.window_spin.value()),
            scan_mode=ScanMode.CONTINUOUS,
        )
        cfg.validate()
        return cfg

    def _on_start(self) -> None:
        try:
            cfg = self._collect_cfg()
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        n_ch = sum(len(b.enabled_channels) for b in cfg.boards)
        capacity = max(2048, int(cfg.plot_window_seconds * cfg.sample_rate_hz))
        capacity = max(capacity, 8192)  # ensure FFT has enough samples
        self._buffer = RingBuffer(capacity, n_ch)

        self._time_plot.clear(); self._fft_plot.clear()
        self._time_curves = []; self._fft_curves = []
        labels = cfg.channel_labels()
        for slot, ch in enumerate(cfg.boards[0].enabled_channels):
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            pen = pg.mkPen(color, width=1.5)
            self._time_curves.append(self._time_plot.plot([], [], pen=pen, name=labels[slot]))
            self._fft_curves.append(self._fft_plot.plot([], [], pen=pen, name=labels[slot]))

        self._cfg = cfg
        self._worker = _VibrationWorker(self._backend, cfg, self._buffer)
        self._worker.started_ok.connect(self._on_started)
        self._worker.stopped.connect(self._on_stopped)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stopped.connect(self._thread.quit)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        self.status_label.setText("Starting...")

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()

    def _on_started(self) -> None:
        self._refresh_timer.start()
        self.status_label.setText("Acquiring")

    def _on_stopped(self, reason: str) -> None:
        self._refresh_timer.stop()
        self._refresh_plots()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.status_label.setText(f"Idle ({reason})")

    def _on_error(self, msg: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        self._refresh_timer.stop()
        QMessageBox.critical(self, "MCC172 error", msg)
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.status_label.setText("Error")

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater(); self._worker = None
        if self._thread is not None:
            self._thread.deleteLater(); self._thread = None

    def _on_progress(self, total: int) -> None:
        self.status_label.setText(f"Acquiring  -  {total:,} samples")

    # -------------------------------------------------------------- plots
    def _refresh_plots(self) -> None:
        if self._buffer is None:
            return
        data, total = self._buffer.snapshot()
        n = data.shape[0]
        if n == 0:
            return
        rate = float(self.rate_spin.value())
        t_end = total / rate
        t_start = t_end - n / rate
        x = np.linspace(t_start, t_end, n, endpoint=False)
        for i, curve in enumerate(self._time_curves):
            if i < data.shape[1]:
                curve.setData(x, data[:, i])
        # FFT over the most recent power-of-two window.
        m = 1 << (n.bit_length() - 1)
        m = min(m, 16384)
        if m < 256:
            return
        seg = data[-m:]
        win = np.hanning(m)
        spec = np.fft.rfft(seg * win[:, None], axis=0)
        mag = np.abs(spec) * (2.0 / win.sum())
        freqs = np.fft.rfftfreq(m, d=1.0 / rate)
        ref = INPUT_RANGE_172_V
        y = 20 * np.log10(np.maximum(mag, 1e-12) / ref)
        for i, curve in enumerate(self._fft_curves):
            if i < y.shape[1]:
                curve.setData(freqs, y[:, i])

    def stop_and_close(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            if self._thread is not None:
                self._thread.quit(); self._thread.wait(1500)
