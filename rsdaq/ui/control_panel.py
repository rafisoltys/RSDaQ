"""Left-hand control panel: channel enables, sample rate, trigger, recording."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from rsdaq.config import (
    AcquisitionConfig, MAX_AGGREGATE_RATE_HZ, NUM_CHANNELS, ScanMode, TriggerMode,
)


class ControlPanel(QWidget):
    start_requested = Signal(AcquisitionConfig)
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._wire()
        self.set_running(False)
        self._update_aggregate_label()

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Channels
        ch_group = QGroupBox("Channels")
        ch_layout = QGridLayout(ch_group)
        ch_layout.setHorizontalSpacing(14)
        ch_layout.setVerticalSpacing(6)
        self.channel_checks: List[QCheckBox] = []
        for i in range(NUM_CHANNELS):
            cb = QCheckBox(f"CH {i}")
            cb.setChecked(i == 0)
            self.channel_checks.append(cb)
            ch_layout.addWidget(cb, i // 2, i % 2)
        root.addWidget(ch_group)

        # Acquisition
        acq_group = QGroupBox("Acquisition")
        acq_form = QFormLayout(acq_group)
        acq_form.setLabelAlignment(Qt.AlignRight)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(1.0, float(MAX_AGGREGATE_RATE_HZ))
        self.rate_spin.setDecimals(1)
        self.rate_spin.setValue(1000.0)
        self.rate_spin.setSuffix(" Hz")
        acq_form.addRow("Sample rate (per ch):", self.rate_spin)

        self.scan_combo = QComboBox()
        self.scan_combo.addItems([m.value for m in ScanMode])
        acq_form.addRow("Scan mode:", self.scan_combo)

        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(1, 10_000_000)
        self.samples_spin.setValue(10_000)
        acq_form.addRow("Samples / channel:", self.samples_spin)

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems([m.value for m in TriggerMode])
        acq_form.addRow("Trigger:", self.trigger_combo)

        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.1, 600.0)
        self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(5.0)
        self.window_spin.setSuffix(" s")
        acq_form.addRow("Plot window:", self.window_spin)

        self.aggregate_label = QLabel("--")
        self.aggregate_label.setProperty("role", "muted")
        acq_form.addRow("Aggregate rate:", self.aggregate_label)

        root.addWidget(acq_group)

        # Recording
        rec_group = QGroupBox("Recording")
        rec_layout = QVBoxLayout(rec_group)
        self.record_check = QCheckBox("Record acquisition to file")
        rec_layout.addWidget(self.record_check)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("(no file selected)")
        self.path_edit.setEnabled(False)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setEnabled(False)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.browse_btn)
        rec_layout.addLayout(path_row)
        hint = QLabel("CSV (*.csv) or HDF5 (*.h5)")
        hint.setProperty("role", "muted")
        rec_layout.addWidget(hint)
        root.addWidget(rec_group)

        # Spacer + actions
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)

        actions = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startButton")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopButton")
        actions.addWidget(self.start_btn)
        actions.addWidget(self.stop_btn)
        root.addLayout(actions)

        root.addStretch(1)

    # ------------------------------------------------------------------ wire
    def _wire(self) -> None:
        for cb in self.channel_checks:
            cb.toggled.connect(self._update_aggregate_label)
        self.rate_spin.valueChanged.connect(self._update_aggregate_label)
        self.scan_combo.currentTextChanged.connect(self._on_scan_mode_changed)
        self.record_check.toggled.connect(self._on_record_toggled)
        self.browse_btn.clicked.connect(self._on_browse)
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self._on_scan_mode_changed(self.scan_combo.currentText())

    # --------------------------------------------------------------- callbacks
    def _on_scan_mode_changed(self, text: str) -> None:
        is_finite = text == ScanMode.FINITE.value
        self.samples_spin.setEnabled(is_finite)

    def _on_record_toggled(self, checked: bool) -> None:
        self.path_edit.setEnabled(checked)
        self.browse_btn.setEnabled(checked)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Record to...", "",
            "CSV (*.csv);;HDF5 (*.h5 *.hdf5);;All files (*)")
        if path:
            self.path_edit.setText(path)

    def _on_start_clicked(self) -> None:
        try:
            cfg = self.collect_config()
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        self.start_requested.emit(cfg)

    def _update_aggregate_label(self) -> None:
        n = sum(1 for cb in self.channel_checks if cb.isChecked())
        rate = self.rate_spin.value()
        agg = rate * max(1, n)
        ok = agg <= MAX_AGGREGATE_RATE_HZ and n > 0
        self.aggregate_label.setText(
            f"{agg:,.0f} S/s ({n} ch)" if n else "no channels selected"
        )
        self.aggregate_label.setStyleSheet(
            "" if ok else "color:#ff6b6b; font-weight:600;"
        )

    # ----------------------------------------------------------------- public
    def collect_config(self) -> AcquisitionConfig:
        channels = [i for i, cb in enumerate(self.channel_checks) if cb.isChecked()]
        cfg = AcquisitionConfig(
            enabled_channels=channels,
            sample_rate_hz=self.rate_spin.value(),
            samples_per_channel=self.samples_spin.value(),
            scan_mode=ScanMode(self.scan_combo.currentText()),
            trigger_mode=TriggerMode(self.trigger_combo.currentText()),
            plot_window_seconds=self.window_spin.value(),
            record_to_file=self.record_check.isChecked(),
            record_path=self.path_edit.text().strip(),
        )
        cfg.validate()
        if cfg.record_to_file and not cfg.record_path:
            raise ValueError("Recording is enabled but no file was selected.")
        return cfg

    def set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        editable = (
            *self.channel_checks, self.rate_spin, self.scan_combo,
            self.samples_spin, self.trigger_combo, self.window_spin,
            self.record_check,
        )
        for w in editable:
            w.setEnabled(not running)
        # path_edit / browse_btn only enabled when not running AND record is on
        rec = self.record_check.isChecked() and not running
        self.path_edit.setEnabled(rec)
        self.browse_btn.setEnabled(rec)
        # samples_spin only meaningful in finite mode
        if not running:
            self._on_scan_mode_changed(self.scan_combo.currentText())
