"""Left-hand control panel: per-board channel matrix, sample rate, triggers, recording."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from rsdaq.config import (
    AcquisitionConfig, BoardSelection, FFTConfig, FFTWindow,
    MAX_AGGREGATE_RATE_HZ, NUM_CHANNELS_118, ScanMode, SoftwareTriggerConfig,
    TriggerMode, TriggerRunMode, TriggerSlope,
)
from rsdaq.daq.boards import BoardInfo, BoardKind


class ControlPanel(QWidget):
    start_requested = Signal(AcquisitionConfig)
    stop_requested = Signal()
    boards_dialog_requested = Signal()
    calibration_dialog_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mcc118_boards: List[BoardInfo] = []
        # board address -> list[QCheckBox] (length 8)
        self._channel_checks: Dict[int, List[QCheckBox]] = {}
        self._build()
        self._wire()

    # =======================================================================
    # Build
    # =======================================================================
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---- Boards header ----
        boards_group = QGroupBox("Boards")
        bv = QVBoxLayout(boards_group)
        self.boards_summary = QLabel("Scan to detect boards.")
        self.boards_summary.setProperty("role", "muted")
        self.boards_summary.setWordWrap(True)
        bv.addWidget(self.boards_summary)
        row = QHBoxLayout()
        self.scan_btn = QPushButton("Scan / configure boards...")
        self.cal_btn = QPushButton("Calibration...")
        row.addWidget(self.scan_btn)
        row.addWidget(self.cal_btn)
        bv.addLayout(row)
        root.addWidget(boards_group)

        # ---- Channels (per-board grid, populated dynamically) ----
        self.channels_group = QGroupBox("MCC118 channels")
        self.channels_layout = QVBoxLayout(self.channels_group)
        self.no_boards_label = QLabel("No MCC118 boards configured. Use 'Scan' above.")
        self.no_boards_label.setProperty("role", "muted")
        self.channels_layout.addWidget(self.no_boards_label)
        root.addWidget(self.channels_group)

        # ---- Acquisition ----
        acq_group = QGroupBox("Acquisition")
        acq_form = QFormLayout(acq_group)
        acq_form.setLabelAlignment(Qt.AlignRight)

        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setRange(1.0, float(MAX_AGGREGATE_RATE_HZ))
        self.rate_spin.setDecimals(1); self.rate_spin.setValue(1000.0); self.rate_spin.setSuffix(" Hz")
        acq_form.addRow("Sample rate (per ch):", self.rate_spin)

        self.scan_combo = QComboBox()
        self.scan_combo.addItems([m.value for m in ScanMode])
        acq_form.addRow("Scan mode:", self.scan_combo)

        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(1, 10_000_000); self.samples_spin.setValue(10_000)
        acq_form.addRow("Samples / channel:", self.samples_spin)

        self.trigger_combo = QComboBox()
        self.trigger_combo.addItems([m.value for m in TriggerMode])
        acq_form.addRow("HW trigger:", self.trigger_combo)

        self.window_spin = QDoubleSpinBox()
        self.window_spin.setRange(0.1, 600.0); self.window_spin.setSingleStep(0.5)
        self.window_spin.setValue(5.0); self.window_spin.setSuffix(" s")
        acq_form.addRow("Plot window:", self.window_spin)

        self.cal_check = QCheckBox("Apply calibration")
        self.cal_check.setChecked(True)
        acq_form.addRow("", self.cal_check)

        self.aggregate_label = QLabel("--")
        self.aggregate_label.setProperty("role", "muted")
        acq_form.addRow("Per-board aggregate:", self.aggregate_label)
        root.addWidget(acq_group)

        # ---- Software trigger ----
        sw_group = QGroupBox("Software trigger (level)")
        sw_form = QFormLayout(sw_group)
        sw_form.setLabelAlignment(Qt.AlignRight)
        self.sw_enable = QCheckBox("Enable")
        sw_form.addRow("", self.sw_enable)
        self.sw_run_mode = QComboBox()
        self.sw_run_mode.addItems([m.value for m in TriggerRunMode])
        sw_form.addRow("Mode:", self.sw_run_mode)
        self.sw_source = QComboBox()
        sw_form.addRow("Source:", self.sw_source)
        self.sw_level = QDoubleSpinBox()
        self.sw_level.setRange(-10.0, 10.0); self.sw_level.setDecimals(3)
        self.sw_level.setSingleStep(0.05); self.sw_level.setSuffix(" V")
        sw_form.addRow("Level:", self.sw_level)
        self.sw_slope = QComboBox()
        self.sw_slope.addItems([s.value for s in TriggerSlope])
        sw_form.addRow("Slope:", self.sw_slope)
        self.sw_pre = QSpinBox()
        self.sw_pre.setRange(0, 1_000_000); self.sw_pre.setValue(256)
        sw_form.addRow("Pre-samples:", self.sw_pre)
        self.sw_post = QSpinBox()
        self.sw_post.setRange(1, 10_000_000); self.sw_post.setValue(1024)
        sw_form.addRow("Post-samples:", self.sw_post)
        root.addWidget(sw_group)

        # ---- FFT ----
        fft_group = QGroupBox("FFT view")
        fft_form = QFormLayout(fft_group)
        self.fft_enable = QCheckBox("Show FFT tab")
        self.fft_enable.setChecked(True)
        fft_form.addRow("", self.fft_enable)
        self.fft_size = QComboBox()
        for s in (256, 512, 1024, 2048, 4096, 8192, 16384, 32768):
            self.fft_size.addItem(str(s), s)
        self.fft_size.setCurrentText("4096")
        fft_form.addRow("Size:", self.fft_size)
        self.fft_window = QComboBox()
        for w in FFTWindow:
            self.fft_window.addItem(w.value, w)
        fft_form.addRow("Window:", self.fft_window)
        root.addWidget(fft_group)

        # ---- Recording ----
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

        # ---- Actions ----
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
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

    # =======================================================================
    # Wiring
    # =======================================================================
    def _wire(self) -> None:
        self.scan_btn.clicked.connect(self.boards_dialog_requested.emit)
        self.cal_btn.clicked.connect(self.calibration_dialog_requested.emit)
        self.rate_spin.valueChanged.connect(self._update_aggregate_label)
        self.scan_combo.currentTextChanged.connect(self._on_scan_mode_changed)
        self.record_check.toggled.connect(self._on_record_toggled)
        self.browse_btn.clicked.connect(self._on_browse)
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.sw_enable.toggled.connect(self._on_sw_enable_toggled)
        self._on_scan_mode_changed(self.scan_combo.currentText())
        self._on_sw_enable_toggled(self.sw_enable.isChecked())
        self.set_running(False)
        self._update_aggregate_label()

    # =======================================================================
    # Public: set the list of MCC118 boards
    # =======================================================================
    def set_mcc118_boards(self, boards: List[BoardInfo]) -> None:
        self._mcc118_boards = list(boards)
        self._channel_checks = {}
        # Clear layout
        while self.channels_layout.count():
            item = self.channels_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not boards:
            self.channels_layout.addWidget(self.no_boards_label)
            self.no_boards_label.show()
            self._update_aggregate_label()
            self._rebuild_sw_source_options()
            return
        for board in boards:
            grp = QGroupBox(f"Board #{board.address}")
            grid = QGridLayout(grp)
            grid.setHorizontalSpacing(14); grid.setVerticalSpacing(6)
            checks: List[QCheckBox] = []
            for i in range(NUM_CHANNELS_118):
                cb = QCheckBox(f"CH{i}")
                cb.setChecked(i == 0)
                cb.toggled.connect(self._update_aggregate_label)
                cb.toggled.connect(self._rebuild_sw_source_options)
                checks.append(cb)
                grid.addWidget(cb, i // 4, i % 4)
            self._channel_checks[board.address] = checks
            self.channels_layout.addWidget(grp)
        self._update_aggregate_label()
        self._rebuild_sw_source_options()

    def update_boards_summary(self, boards: List[BoardInfo]) -> None:
        if not boards:
            self.boards_summary.setText("No boards detected.")
        else:
            parts = ", ".join(f"#{b.address} {b.kind.value}" for b in boards)
            tag = " (simulated)" if any(b.simulated for b in boards) else ""
            self.boards_summary.setText(f"{len(boards)} board(s){tag}: {parts}")

    # =======================================================================
    # Helpers
    # =======================================================================
    def _on_scan_mode_changed(self, text: str) -> None:
        self.samples_spin.setEnabled(text == ScanMode.FINITE.value)

    def _on_record_toggled(self, checked: bool) -> None:
        self.path_edit.setEnabled(checked)
        self.browse_btn.setEnabled(checked)

    def _on_sw_enable_toggled(self, checked: bool) -> None:
        for w in (self.sw_run_mode, self.sw_source, self.sw_level,
                  self.sw_slope, self.sw_pre, self.sw_post):
            w.setEnabled(checked)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Record to...", "",
            "CSV (*.csv);;HDF5 (*.h5 *.hdf5);;All files (*)")
        if path:
            self.path_edit.setText(path)

    def _enabled_per_board(self) -> List[Tuple[int, List[int]]]:
        out: List[Tuple[int, List[int]]] = []
        for board in self._mcc118_boards:
            checks = self._channel_checks.get(board.address, [])
            chans = [i for i, cb in enumerate(checks) if cb.isChecked()]
            if chans:
                out.append((board.address, chans))
        return out

    def _rebuild_sw_source_options(self) -> None:
        current = self.sw_source.currentData() if self.sw_source.count() else None
        self.sw_source.clear()
        idx = 0
        for addr, chans in self._enabled_per_board():
            for ch in chans:
                self.sw_source.addItem(f"B{addr}:CH{ch}", idx)
                idx += 1
        if current is not None:
            cur_idx = self.sw_source.findData(current)
            if cur_idx >= 0:
                self.sw_source.setCurrentIndex(cur_idx)

    def _update_aggregate_label(self) -> None:
        per_board = self._enabled_per_board()
        if not per_board:
            self.aggregate_label.setText("no channels selected")
            self.aggregate_label.setStyleSheet("color:#ff6b6b; font-weight:600;")
            return
        max_n = max(len(c) for _a, c in per_board)
        rate = self.rate_spin.value()
        agg = rate * max_n
        ok = agg <= MAX_AGGREGATE_RATE_HZ
        n_boards = len(per_board)
        self.aggregate_label.setText(f"{agg:,.0f} S/s on busiest board ({n_boards} board(s))")
        self.aggregate_label.setStyleSheet("" if ok else "color:#ff6b6b; font-weight:600;")

    def _on_start_clicked(self) -> None:
        try:
            cfg = self.collect_config()
        except ValueError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Invalid configuration", str(exc))
            return
        self.start_requested.emit(cfg)

    # =======================================================================
    # Public API
    # =======================================================================
    def collect_config(self) -> AcquisitionConfig:
        per_board = self._enabled_per_board()
        if not per_board:
            raise ValueError("Select at least one channel on at least one board.")
        boards = [BoardSelection(address=a, enabled_channels=c) for a, c in per_board]

        sw = SoftwareTriggerConfig(
            enabled=self.sw_enable.isChecked(),
            run_mode=TriggerRunMode(self.sw_run_mode.currentText()),
            source=int(self.sw_source.currentData() or 0),
            level_v=float(self.sw_level.value()),
            slope=TriggerSlope(self.sw_slope.currentText()),
            pre_samples=int(self.sw_pre.value()),
            post_samples=int(self.sw_post.value()),
        )
        fft = FFTConfig(
            enabled=self.fft_enable.isChecked(),
            size=int(self.fft_size.currentData()),
            window=FFTWindow(self.fft_window.currentData()),
        )
        cfg = AcquisitionConfig(
            boards=boards,
            sample_rate_hz=self.rate_spin.value(),
            samples_per_channel=self.samples_spin.value(),
            scan_mode=ScanMode(self.scan_combo.currentText()),
            trigger_mode=TriggerMode(self.trigger_combo.currentText()),
            plot_window_seconds=self.window_spin.value(),
            record_to_file=self.record_check.isChecked(),
            record_path=self.path_edit.text().strip(),
            apply_calibration=self.cal_check.isChecked(),
            software_trigger=sw,
            fft=fft,
        )
        cfg.validate()
        if cfg.record_to_file and not cfg.record_path:
            raise ValueError("Recording is enabled but no file was selected.")
        return cfg

    def set_running(self, running: bool) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        for grp in (self.channels_group,):
            grp.setEnabled(not running)
        for w in (
            self.scan_btn, self.cal_btn, self.rate_spin, self.scan_combo,
            self.samples_spin, self.trigger_combo, self.window_spin,
            self.cal_check, self.record_check, self.sw_enable, self.fft_enable,
            self.fft_size, self.fft_window,
        ):
            w.setEnabled(not running)
        rec = self.record_check.isChecked() and not running
        self.path_edit.setEnabled(rec)
        self.browse_btn.setEnabled(rec)
        if not running:
            self._on_scan_mode_changed(self.scan_combo.currentText())
            self._on_sw_enable_toggled(self.sw_enable.isChecked())
