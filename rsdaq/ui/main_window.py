"""Top-level window and orchestration of worker / UI."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QSplitter, QStatusBar,
    QVBoxLayout, QWidget,
)

from rsdaq.config import AcquisitionConfig
from rsdaq.core.worker import AcquisitionWorker, make_worker_thread
from rsdaq.daq import create_backend
from rsdaq.daq.backend import DaqBackend

from .control_panel import ControlPanel
from .plot_panel import PlotPanel
from .stats_panel import StatsPanel

log = logging.getLogger(__name__)

REFRESH_INTERVAL_MS = 50  # 20 Hz GUI refresh


class MainWindow(QMainWindow):
    def __init__(self, backend: Optional[DaqBackend] = None):
        super().__init__()
        self.setWindowTitle("RSDaQ - MCC118 Data Acquisition")
        self.resize(1280, 760)

        self._backend: DaqBackend = backend or create_backend("auto")
        self._worker: Optional[AcquisitionWorker] = None
        self._thread = None

        self._build_ui()
        self._build_menu()
        self._build_status_bar()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh)

        self._set_status_idle()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.control_panel = ControlPanel()
        self.control_panel.setFixedWidth(320)
        self.control_panel.start_requested.connect(self._on_start)
        self.control_panel.stop_requested.connect(self._on_stop)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        self.plot_panel = PlotPanel()
        self.stats_panel = StatsPanel()
        self.stats_panel.setMaximumHeight(220)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.plot_panel)
        splitter.addWidget(self.stats_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        right_layout.addWidget(splitter)

        outer.addWidget(self.control_panel)
        outer.addWidget(right, 1)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        quit_act = QAction("&Quit", self, shortcut=QKeySequence.Quit, triggered=self.close)
        file_menu.addAction(quit_act)

        help_menu = bar.addMenu("&Help")
        about_act = QAction("&About RSDaQ", self, triggered=self._show_about)
        help_menu.addAction(about_act)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.status_state = QLabel("Idle")
        self.status_board = QLabel(self._backend.board_info)
        self.status_board.setProperty("role", "muted")
        self.status_progress = QLabel("")
        bar.addWidget(self.status_state, 0)
        bar.addPermanentWidget(self.status_progress, 1)
        bar.addPermanentWidget(self.status_board, 0)

    # -------------------------------------------------------------- handlers
    def _on_start(self, cfg: AcquisitionConfig) -> None:
        log.info("Starting acquisition: %s", cfg)
        self._worker = AcquisitionWorker(self._backend)
        self._worker.configure(cfg)

        # Wire UI panels to the freshly created buffer/stats objects.
        assert self._worker.buffer is not None and self._worker.stats is not None
        self.plot_panel.configure(cfg.enabled_channels, cfg.sample_rate_hz, self._worker.buffer)
        self.stats_panel.configure(cfg.enabled_channels, self._worker.stats)

        self._worker.started_ok.connect(self._on_worker_started)
        self._worker.stopped.connect(self._on_worker_stopped)
        self._worker.error.connect(self._on_worker_error)
        self._worker.progress.connect(self._on_progress)

        self._thread = make_worker_thread(self._worker)
        self._thread.finished.connect(self._on_thread_finished)
        self._thread.start()
        self.control_panel.set_running(True)
        self.status_state.setText("Starting...")

    def _on_stop(self) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            self.status_state.setText("Stopping...")

    def _on_worker_started(self) -> None:
        self._refresh_timer.start()
        self.status_state.setText("Acquiring")

    def _on_worker_stopped(self, reason: str) -> None:
        self._refresh_timer.stop()
        self._on_refresh()  # final paint
        self.control_panel.set_running(False)
        self.status_state.setText(f"Idle ({reason})")

    def _on_worker_error(self, msg: str) -> None:
        self._refresh_timer.stop()
        QMessageBox.critical(self, "Acquisition error", msg)
        self.control_panel.set_running(False)
        self.status_state.setText("Error")

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _on_progress(self, total: int, elapsed: float) -> None:
        self.status_progress.setText(f"{total:,} samples  |  {elapsed:6.2f} s")

    def _on_refresh(self) -> None:
        self.plot_panel.refresh()
        self.stats_panel.refresh()

    def _set_status_idle(self) -> None:
        self.status_state.setText("Idle")
        self.status_progress.setText("")

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About RSDaQ",
            "<h3>RSDaQ</h3>"
            "<p>Data acquisition for the Digilent MCC118 HAT on Raspberry Pi 5.</p>"
            f"<p>Backend: <b>{self._backend.board_info}</b></p>"
        )

    # --------------------------------------------------------------- closing
    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.request_stop()
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait(2000)
        super().closeEvent(event)
