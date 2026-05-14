"""Top-level window and orchestration of worker / UI."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QSplitter, QStatusBar,
    QTabWidget, QVBoxLayout, QWidget,
)

from rsdaq.calibration import CalibrationStore
from rsdaq.config import AcquisitionConfig
from rsdaq.core.worker import AcquisitionWorker, make_worker_thread
from rsdaq.daq import (
    create_output_backend, create_scan_backend, create_thermocouple_backend,
    create_vibration_backend, scan_boards,
)
from rsdaq.daq.backend import ScanBackend
from rsdaq.daq.boards import BoardInfo, BoardKind
from rsdaq.display import DisplayStore

from .boards_dialog import BoardsDialog
from .calibration_dialog import CalibrationDialog
from .control_panel import ControlPanel
from .display_dialog import DisplayDialog
from .fft_panel import FFTPanel
from .output_panel import OutputPanel
from .plot_panel import PlotPanel
from .stats_panel import StatsPanel
from .tc_panel import ThermocouplePanel
from .vibration_panel import VibrationPanel

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 50  # 20 Hz GUI refresh
CONTROL_PANEL_WIDTH = 440  # wide enough that the inner scrollbar isn't needed


class MainWindow(QMainWindow):
    def __init__(self, prefer_backend: str = "auto"):
        super().__init__()
        self.setWindowTitle("RSDaQ - MCC HAT Data Acquisition")
        self.resize(1500, 860)

        self._prefer = prefer_backend
        self._boards: List[BoardInfo] = []
        self._scan_backend: Optional[ScanBackend] = None
        self._worker: Optional[AcquisitionWorker] = None
        self._thread = None
        self._calibration = CalibrationStore.load()
        self._display = DisplayStore.load()
        self._captures: List[np.ndarray] = []  # software-trigger captures

        # Tab key -> page widget. Pages are kept alive even when hidden so that
        # acquisitions can keep updating the buffers behind a hidden tab.
        self._tab_pages: Dict[str, QWidget] = {}

        self._build_ui()
        self._build_menu()
        self._build_status_bar()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh)

        # Initial board scan
        self._do_scan_boards(initial=True)

    # =================================================================== UI
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        self.control_panel = ControlPanel()
        self.control_panel.setFixedWidth(CONTROL_PANEL_WIDTH)
        self.control_panel.start_requested.connect(self._on_start)
        self.control_panel.stop_requested.connect(self._on_stop)
        self.control_panel.boards_dialog_requested.connect(self._open_boards_dialog)
        self.control_panel.calibration_dialog_requested.connect(self._open_calibration_dialog)
        self.control_panel.display_dialog_requested.connect(self._open_display_dialog)
        self.control_panel.tab_visibility_changed.connect(self._on_tab_visibility_changed)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Build the four "always-available" tab pages first.
        self._build_acquire_page()
        self._build_spectrum_page()
        self._build_captures_page()

        # Function tabs (TC / output / vibration) are built lazily once boards
        # are detected.
        self._tc_panels: List[ThermocouplePanel] = []
        self._out_panels: List[OutputPanel] = []
        self._vib_panels: List[VibrationPanel] = []

        outer.addWidget(self.control_panel)
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

    def _build_acquire_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8); layout.setSpacing(8)

        self.plot_panel = PlotPanel()
        self.stats_panel = StatsPanel()
        self.stats_panel.setMaximumHeight(220)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.plot_panel)
        splitter.addWidget(self.stats_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self._tab_pages["acquire"] = page
        self.tabs.addTab(page, "Acquire")

    def _build_spectrum_page(self) -> None:
        self.fft_panel = FFTPanel()
        self._tab_pages["spectrum"] = self.fft_panel
        self.tabs.addTab(self.fft_panel, "Spectrum")

    def _build_captures_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        self._captures_label = QLabel("Software-trigger captures will appear here.")
        self._captures_label.setProperty("role", "muted")
        layout.addWidget(self._captures_label)
        self._captures_plot = PlotPanel()
        layout.addWidget(self._captures_plot, 1)
        self._tab_pages["captures"] = page
        self.tabs.addTab(page, "Trigger captures")

    def _rebuild_function_tabs(self) -> None:
        """Add or replace MCC134 / MCC152 / MCC172 tabs based on detected boards.

        Function tabs are always inserted at fixed positions (after the three
        always-on tabs), then individually hidden via setTabVisible() according
        to the user's checkbox. We never call removeTab() to toggle visibility -
        that caused Qt to keep stale labels around and made one tab's text bleed
        onto a neighbour.
        """
        # Drop existing TC / Output / Vibration pages (they own their backends).
        for key in ("thermocouples", "outputs", "vibration"):
            page = self._tab_pages.pop(key, None)
            if page is not None:
                idx = self.tabs.indexOf(page)
                if idx >= 0:
                    self.tabs.removeTab(idx)
                page.deleteLater()
        self._tc_panels = []
        self._out_panels = []
        self._vib_panels = []

        tc_boards = [b for b in self._boards if b.kind is BoardKind.MCC134]
        if tc_boards:
            tc_host = QWidget(); v = QVBoxLayout(tc_host)
            v.setContentsMargins(0, 0, 0, 0)
            for b in tc_boards:
                panel = ThermocouplePanel(create_thermocouple_backend(self._prefer), b.address)
                v.addWidget(panel)
                self._tc_panels.append(panel)
            self._tab_pages["thermocouples"] = tc_host
            self.tabs.addTab(tc_host, "Thermocouples")

        out_boards = [b for b in self._boards if b.kind is BoardKind.MCC152]
        if out_boards:
            out_host = QWidget(); v = QVBoxLayout(out_host)
            v.setContentsMargins(0, 0, 0, 0)
            for b in out_boards:
                panel = OutputPanel(create_output_backend(self._prefer), b.address)
                v.addWidget(panel)
                self._out_panels.append(panel)
            self._tab_pages["outputs"] = out_host
            self.tabs.addTab(out_host, "Outputs")

        vib_boards = [b for b in self._boards if b.kind is BoardKind.MCC172]
        if vib_boards:
            vib_host = QWidget(); v = QVBoxLayout(vib_host)
            v.setContentsMargins(0, 0, 0, 0)
            for b in vib_boards:
                back = create_vibration_backend(addresses=[b.address], prefer=self._prefer)
                panel = VibrationPanel(back, b.address)
                v.addWidget(panel)
                self._vib_panels.append(panel)
            self._tab_pages["vibration"] = vib_host
            self.tabs.addTab(vib_host, "Vibration (MCC172)")

        # Update which checkboxes are enabled and re-apply current visibility.
        self.control_panel.set_tab_available("thermocouples", bool(tc_boards))
        self.control_panel.set_tab_available("outputs", bool(out_boards))
        self.control_panel.set_tab_available("vibration", bool(vib_boards))
        self._reapply_tab_visibility()

    def _reapply_tab_visibility(self) -> None:
        """Hide/show each tab using QTabWidget.setTabVisible() - no remove/add."""
        for key, page in self._tab_pages.items():
            idx = self.tabs.indexOf(page)
            if idx < 0:
                continue
            visible = self.control_panel.is_tab_visible(key)
            self.tabs.setTabVisible(idx, visible)

    def _on_tab_visibility_changed(self, key: str, visible: bool) -> None:
        page = self._tab_pages.get(key)
        if page is None:
            return
        idx = self.tabs.indexOf(page)
        if idx < 0:
            return
        self.tabs.setTabVisible(idx, visible)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction(QAction("&Quit", self,
                                    shortcut=QKeySequence.Quit, triggered=self.close))

        boards_menu = bar.addMenu("&Boards")
        boards_menu.addAction(QAction("Scan && configure...", self,
                                      triggered=self._open_boards_dialog))
        boards_menu.addAction(QAction("Calibration...", self,
                                      triggered=self._open_calibration_dialog))
        boards_menu.addAction(QAction("Visualisation && units...", self,
                                      triggered=self._open_display_dialog))

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(QAction("&About RSDaQ", self,
                                    triggered=self._show_about))

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.status_state = QLabel("Idle")
        self.status_board = QLabel("")
        self.status_progress = QLabel("")
        bar.addWidget(self.status_state, 0)
        bar.addPermanentWidget(self.status_progress, 1)
        bar.addPermanentWidget(self.status_board, 0)

    # ============================================================= board mgmt
    def _do_scan_boards(self, initial: bool = False) -> None:
        self._boards = scan_boards()
        self._apply_boards()
        if initial and not self._boards:
            self.statusBar().showMessage("No boards detected; running in simulator mode.", 5000)

    def _apply_boards(self) -> None:
        mcc118 = [b for b in self._boards if b.kind is BoardKind.MCC118]
        self.control_panel.set_mcc118_boards(mcc118)
        self.control_panel.update_boards_summary(self._boards)
        self.status_board.setText(self._boards_status_text())
        if mcc118:
            try:
                self._scan_backend = create_scan_backend(
                    addresses=[b.address for b in mcc118], prefer=self._prefer)
            except Exception as exc:
                log.warning("Could not create scan backend: %s", exc)
                self._scan_backend = create_scan_backend(prefer="simulator")
        else:
            self._scan_backend = None
        self._rebuild_function_tabs()

    def _boards_status_text(self) -> str:
        if not self._boards:
            return "No boards"
        parts = []
        for b in self._boards:
            parts.append(f"#{b.address}:{b.kind.value}{'*' if b.simulated else ''}")
        return "  ".join(parts)

    def _open_boards_dialog(self) -> None:
        dlg = BoardsDialog(current=self._boards, parent=self)
        if dlg.exec():
            self._boards = dlg.selected_boards()
            self._apply_boards()

    def _open_calibration_dialog(self) -> None:
        mcc118 = [b for b in self._boards if b.kind is BoardKind.MCC118]
        if not mcc118:
            QMessageBox.information(self, "Calibration",
                                    "No MCC118 boards configured.")
            return
        dlg = CalibrationDialog(self._calibration, mcc118, parent=self)
        dlg.exec()

    def _open_display_dialog(self) -> None:
        mcc118 = [b for b in self._boards if b.kind is BoardKind.MCC118]
        if not mcc118:
            QMessageBox.information(self, "Display",
                                    "No MCC118 boards configured.")
            return
        dlg = DisplayDialog(self._display, mcc118, parent=self)
        dlg.exec()

    # ================================================================= start
    def _on_start(self, cfg: AcquisitionConfig) -> None:
        if self._scan_backend is None:
            QMessageBox.warning(self, "No board", "No MCC118 board configured.")
            self.control_panel.set_running(False)
            return
        log.info("Starting acquisition: %s", cfg)
        self._captures.clear()
        self._captures_label.setText("Software-trigger captures will appear here.")
        self._captures_plot.clear()

        self._worker = AcquisitionWorker(self._scan_backend, calibration=self._calibration)
        self._worker.configure(cfg)
        assert self._worker.buffer is not None and self._worker.stats is not None

        order = self._worker.channel_order
        labels = self._worker.labels
        sw = cfg.software_trigger
        trig_level = sw.level_v if sw.enabled else None
        self.plot_panel.configure(order, labels, cfg.sample_rate_hz,
                                  self._worker.buffer,
                                  display_store=self._display,
                                  trigger_level_v=trig_level)
        self.stats_panel.configure(order, labels, self._worker.stats,
                                   display_store=self._display)
        self.fft_panel.configure(order, labels, cfg.sample_rate_hz, self._worker.buffer)
        self._captures_plot.configure(order, labels, cfg.sample_rate_hz, self._worker.buffer,
                                      display_store=self._display)

        self._worker.started_ok.connect(self._on_worker_started)
        self._worker.stopped.connect(self._on_worker_stopped)
        self._worker.error.connect(self._on_worker_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.triggered.connect(self._on_trigger_event)

        self._thread = make_worker_thread(self._worker)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self.control_panel.set_running(True)
        self.status_state.setText("Starting...")

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.status_state.setText("Stopping...")

    # ============================================================ worker hooks
    def _on_worker_started(self) -> None:
        self._refresh_timer.start()
        self.status_state.setText("Acquiring")

    def _on_worker_stopped(self, reason: str) -> None:
        self._refresh_timer.stop()
        self._on_refresh()
        self.control_panel.set_running(False)
        self.status_state.setText(f"Idle ({reason})")

    def _on_worker_error(self, msg: str) -> None:
        self._refresh_timer.stop()
        QMessageBox.critical(self, "Acquisition error", msg)
        self.control_panel.set_running(False)
        self.status_state.setText("Error")

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater(); self._worker = None
        if self._thread is not None:
            self._thread.deleteLater(); self._thread = None

    def _on_progress(self, total: int, elapsed: float) -> None:
        self.status_progress.setText(f"{total:,} samples  |  {elapsed:6.2f} s")

    def _on_trigger_event(self, sample_index: int, waveform: np.ndarray) -> None:
        self._captures.append(waveform)
        self._captures_label.setText(
            f"{len(self._captures)} capture(s); "
            f"latest at sample #{sample_index:,}, length={waveform.shape[0]}")
        if self._worker is not None and self._worker._cfg is not None:  # type: ignore[attr-defined]
            self.plot_panel.mark_trigger(
                sample_index / self._worker._cfg.sample_rate_hz)  # type: ignore[attr-defined]
        # Flip to the captures tab on the very first event (only if visible).
        if len(self._captures) == 1:
            page = self._tab_pages.get("captures")
            if page is not None:
                idx = self.tabs.indexOf(page)
                if idx >= 0:
                    self.tabs.setCurrentIndex(idx)

    def _on_refresh(self) -> None:
        # Always update plot + stats so values are correct when the user shows
        # the tab again.
        self.plot_panel.refresh()
        self.stats_panel.refresh()
        if self.tabs.currentWidget() is self.fft_panel:
            self.fft_panel.refresh()

    # ============================================================== about/close
    def _show_about(self) -> None:
        backends = ", ".join(b.kind.value for b in self._boards) or "no boards"
        QMessageBox.about(
            self, "About RSDaQ",
            "<h3>RSDaQ</h3>"
            "<p>Data acquisition for Digilent MCC HATs on Raspberry Pi 5.</p>"
            f"<p>Detected boards: <b>{backends}</b></p>"
            "<p>Supports MCC118, MCC134, MCC152 and MCC172.</p>"
        )

    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            if self._thread is not None:
                self._thread.quit(); self._thread.wait(2000)
        for w in self.findChildren(VibrationPanel):
            w.stop_and_close()
        super().closeEvent(event)
