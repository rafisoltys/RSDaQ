"""QThread-based acquisition worker.

Pulls from the scan backend in a tight loop, applies calibration,
maintains a multi-channel ring buffer, runs the optional software trigger,
streams to a recorder, and emits Qt signals for the GUI thread.
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QObject, QThread, Signal, Slot

from rsdaq.calibration import CalibrationStore
from rsdaq.config import AcquisitionConfig, TriggerRunMode
from rsdaq.core.trigger import SoftwareTrigger
from rsdaq.daq.backend import ScanBackend
from rsdaq.io.recorder import Recorder

from .ringbuffer import RingBuffer
from .stats import StatsTracker

log = logging.getLogger(__name__)


class AcquisitionWorker(QObject):
    started_ok = Signal()
    stopped = Signal(str)              # reason
    error = Signal(str)
    progress = Signal(int, float)      # total_samples, elapsed_s
    triggered = Signal(int, object)    # global_sample_index, capture ndarray (n, total_ch)

    def __init__(self, backend: ScanBackend,
                 calibration: Optional[CalibrationStore] = None):
        super().__init__()
        self._backend = backend
        self._calibration = calibration
        self._cfg: Optional[AcquisitionConfig] = None
        self._buffer: Optional[RingBuffer] = None
        self._stats: Optional[StatsTracker] = None
        self._recorder: Optional[Recorder] = None
        self._trigger: Optional[SoftwareTrigger] = None
        self._channel_order: List[Tuple[int, int]] = []   # (address, channel) per col
        self._labels: List[str] = []
        self._abort = False
        self._t_start = 0.0

    # -------------------------------------------------- public accessors
    @property
    def buffer(self) -> Optional[RingBuffer]:
        return self._buffer

    @property
    def stats(self) -> Optional[StatsTracker]:
        return self._stats

    @property
    def labels(self) -> List[str]:
        return list(self._labels)

    @property
    def channel_order(self) -> List[Tuple[int, int]]:
        return list(self._channel_order)

    @property
    def trigger(self) -> Optional[SoftwareTrigger]:
        return self._trigger

    # -------------------------------------------------- configuration
    def configure(self, cfg: AcquisitionConfig) -> None:
        self._cfg = cfg
        self._labels = cfg.channel_labels()
        self._channel_order = [
            (b.address, ch) for b in cfg.boards for ch in b.enabled_channels
        ]
        n_ch = len(self._channel_order)
        capacity = max(1024, int(cfg.plot_window_seconds * cfg.sample_rate_hz))
        # Allow a wider buffer if FFT size is bigger than the plot window.
        if cfg.fft.enabled:
            capacity = max(capacity, int(cfg.fft.size * 2))
        self._buffer = RingBuffer(capacity, n_ch)
        self._stats = StatsTracker(n_ch, labels=self._labels)
        if cfg.record_to_file and cfg.record_path:
            self._recorder = Recorder.for_path(
                cfg.record_path, self._labels, cfg.sample_rate_hz)
        else:
            self._recorder = None
        if cfg.software_trigger.enabled and cfg.software_trigger.run_mode is not TriggerRunMode.FREE_RUN:
            self._trigger = SoftwareTrigger(cfg.software_trigger, n_channels=n_ch)
        elif cfg.software_trigger.enabled:
            self._trigger = SoftwareTrigger(cfg.software_trigger, n_channels=n_ch)
        else:
            self._trigger = None

    # -------------------------------------------------- main loop
    @Slot()
    def run(self) -> None:
        if self._cfg is None or self._buffer is None or self._stats is None:
            self.error.emit("Worker not configured.")
            return
        try:
            if self._recorder is not None:
                self._recorder.open()
            self._backend.start(self._cfg)
        except Exception as exc:
            log.exception("Acquisition start failed")
            self.error.emit(str(exc))
            self._cleanup()
            return

        self._abort = False
        self._t_start = time.monotonic()
        self.started_ok.emit()

        cal = self._calibration if (self._calibration and self._cfg.apply_calibration) else None

        try:
            while not self._abort:
                result = self._backend.read(timeout_s=0.05)
                if result is None:
                    if not self._backend.is_running():
                        break
                    continue
                samples, total = result
                if cal is not None:
                    samples = cal.apply_columns(samples, self._channel_order)
                self._buffer.write(samples)
                self._stats.update(samples)
                if self._recorder is not None:
                    self._recorder.write(samples)
                if self._trigger is not None and self._trigger.gating_active:
                    for ev in self._trigger.feed(samples):
                        self.triggered.emit(ev.sample_index, ev.waveform)
                self.progress.emit(int(total), time.monotonic() - self._t_start)
        except Exception as exc:
            log.exception("Acquisition error")
            self.error.emit(str(exc))
        finally:
            reason = "aborted" if self._abort else "finished"
            self._cleanup()
            self.stopped.emit(reason)

    @Slot()
    def request_stop(self) -> None:
        self._abort = True

    def _cleanup(self) -> None:
        try:
            self._backend.stop()
        except Exception:
            log.exception("Backend stop failed")
        if self._recorder is not None:
            try:
                self._recorder.close()
            except Exception:
                log.exception("Recorder close failed")


def make_worker_thread(worker: AcquisitionWorker) -> QThread:
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.stopped.connect(thread.quit)
    return thread
