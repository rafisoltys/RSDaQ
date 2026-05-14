"""QThread-based acquisition worker.

The worker pulls samples from the backend in a tight loop, writes them to the
ring buffer and (optionally) to a recorder, and emits Qt signals so the GUI
thread can refresh at its own cadence.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from rsdaq.config import AcquisitionConfig
from rsdaq.daq.backend import DaqBackend
from rsdaq.io.recorder import Recorder

from .ringbuffer import RingBuffer
from .stats import StatsTracker

log = logging.getLogger(__name__)


class AcquisitionWorker(QObject):
    started_ok = Signal()
    stopped = Signal(str)         # reason
    error = Signal(str)
    progress = Signal(int, float) # total_samples, elapsed_s

    def __init__(self, backend: DaqBackend):
        super().__init__()
        self._backend = backend
        self._cfg: Optional[AcquisitionConfig] = None
        self._buffer: Optional[RingBuffer] = None
        self._stats: Optional[StatsTracker] = None
        self._recorder: Optional[Recorder] = None
        self._abort = False
        self._t_start = 0.0

    # GUI-thread-safe handles
    @property
    def buffer(self) -> Optional[RingBuffer]:
        return self._buffer

    @property
    def stats(self) -> Optional[StatsTracker]:
        return self._stats

    def configure(self, cfg: AcquisitionConfig) -> None:
        self._cfg = cfg
        n_ch = len(cfg.enabled_channels)
        capacity = max(1024, int(cfg.plot_window_seconds * cfg.sample_rate_hz))
        self._buffer = RingBuffer(capacity, n_ch)
        self._stats = StatsTracker(n_ch)
        if cfg.record_to_file and cfg.record_path:
            self._recorder = Recorder.for_path(
                cfg.record_path, cfg.enabled_channels, cfg.sample_rate_hz)
        else:
            self._recorder = None

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

        try:
            while not self._abort:
                result = self._backend.read(timeout_s=0.05)
                if result is None:
                    if not self._backend.is_running():
                        break
                    continue
                samples, total = result
                self._buffer.write(samples)
                self._stats.update(samples)
                if self._recorder is not None:
                    self._recorder.write(samples)
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
    """Move the worker to a fresh thread and wire up auto-cleanup."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.stopped.connect(thread.quit)
    return thread
