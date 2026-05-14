"""Real MCC118 backend supporting multi-board acquisition.

Starts a synchronised scan on every selected board and round-robin reads
samples, interleaving them into one ``(n, total_channels)`` matrix in the
column order produced by ``AcquisitionConfig.channel_labels()``.

Multi-board scans are software-aligned: each board is started back-to-back
with the same ``a_in_scan_start(...)`` parameters; for tightly synchronised
acquisitions one board's CLK output should be wired to the others' CLK input
and configured externally (advanced; out of scope here).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np

from rsdaq.config import AcquisitionConfig, ScanMode, TriggerMode
from .backend import ScanBackend

log = logging.getLogger(__name__)

try:
    from daqhats import mcc118, OptionFlags, TriggerModes, HatIDs, hat_list  # type: ignore
    _HAS_DAQHATS = True
except Exception as _exc:  # pragma: no cover
    _HAS_DAQHATS = False
    _IMPORT_ERROR = _exc


class MCC118Backend(ScanBackend):
    """Single- or multi-board MCC118 scan backend."""

    name = "MCC118"

    def __init__(self, addresses: Optional[List[int]] = None):
        if not _HAS_DAQHATS:
            raise RuntimeError(f"daqhats not available: {_IMPORT_ERROR}")
        if addresses is None:
            entries = hat_list(filter_by_id=HatIDs.MCC_118)
            if not entries:
                raise RuntimeError("No MCC118 boards detected on the SPI bus.")
            addresses = [int(e.address) for e in entries]
        if not addresses:
            raise RuntimeError("No MCC118 addresses provided.")
        self._addresses = sorted(set(int(a) for a in addresses))
        self._hats = {a: mcc118(a) for a in self._addresses}
        self._cfg: Optional[AcquisitionConfig] = None
        self._running = False
        self._total = 0
        # Per-board state used during reads
        self._board_order: List[int] = []
        self._channels_per_board: List[List[int]] = []

    @property
    def board_info(self) -> str:
        return f"MCC118 x{len(self._addresses)} @ " + ", ".join(str(a) for a in self._addresses)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _channel_mask(channels) -> int:
        mask = 0
        for ch in channels:
            mask |= 1 << ch
        return mask

    @staticmethod
    def _trigger_mode(tm: TriggerMode):
        return {
            TriggerMode.IMMEDIATE: TriggerModes.RISING_EDGE,
            TriggerMode.SOFTWARE_LEVEL: TriggerModes.RISING_EDGE,
            TriggerMode.EXTERNAL_RISING: TriggerModes.RISING_EDGE,
            TriggerMode.EXTERNAL_FALLING: TriggerModes.FALLING_EDGE,
        }[tm]

    @staticmethod
    def _options(cfg: AcquisitionConfig) -> int:
        opts = OptionFlags.DEFAULT
        if cfg.scan_mode is ScanMode.CONTINUOUS:
            opts |= OptionFlags.CONTINUOUS
        if cfg.trigger_mode in (TriggerMode.EXTERNAL_RISING, TriggerMode.EXTERNAL_FALLING):
            opts |= OptionFlags.EXTTRIGGER
        return opts

    # --------------------------------------------------------- lifecycle
    def start(self, cfg: AcquisitionConfig) -> None:
        cfg.validate()
        wanted = [b.address for b in cfg.boards]
        for a in wanted:
            if a not in self._hats:
                raise RuntimeError(
                    f"Address {a} not in opened MCC118 boards "
                    f"{sorted(self._hats.keys())}."
                )
        self._cfg = cfg
        self._total = 0
        self._board_order = wanted
        self._channels_per_board = [b.enabled_channels for b in cfg.boards]

        opts = self._options(cfg)
        samples = 0 if cfg.scan_mode is ScanMode.CONTINUOUS else cfg.samples_per_channel

        for board in cfg.boards:
            hat = self._hats[board.address]
            mask = self._channel_mask(board.enabled_channels)
            if opts & OptionFlags.EXTTRIGGER:
                hat.trigger_mode(self._trigger_mode(cfg.trigger_mode))
            hat.a_in_scan_start(mask, samples, cfg.sample_rate_hz, opts)
        self._running = True
        log.info("MCC118 scan started on %s @ %.1f Hz, opts=0x%x",
                 self._board_order, cfg.sample_rate_hz, int(opts))

    def stop(self) -> None:
        if not self._running:
            return
        for a in self._board_order:
            try:
                self._hats[a].a_in_scan_stop()
            except Exception:
                log.exception("scan_stop failed for board %d", a)
        for a in self._board_order:
            try:
                self._hats[a].a_in_scan_cleanup()
            except Exception:
                log.exception("scan_cleanup failed for board %d", a)
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        if not self._running or self._cfg is None:
            return None

        # Read each board, take the smallest common count, build the matrix.
        per_board_matrices: List[np.ndarray] = []
        any_running = False
        for a, channels in zip(self._board_order, self._channels_per_board):
            hat = self._hats[a]
            r = hat.a_in_scan_read_numpy(-1, timeout_s)
            if r.hardware_overrun or r.buffer_overrun:
                log.error("Board %d overrun (hw=%s buf=%s)",
                          a, r.hardware_overrun, r.buffer_overrun)
            if r.running:
                any_running = True
            data = r.data
            if data is None or data.size == 0:
                per_board_matrices.append(np.empty((0, len(channels)), dtype=np.float64))
            else:
                per_board_matrices.append(data.reshape(-1, len(channels)))

        # Common (minimum) row count across boards keeps columns time-aligned.
        n = min((m.shape[0] for m in per_board_matrices), default=0)
        if n == 0:
            if not any_running:
                self._running = False
            return None

        cols = [m[:n] for m in per_board_matrices]
        samples = np.concatenate(cols, axis=1) if cols else \
            np.empty((n, 0), dtype=np.float64)
        self._total += n
        if not any_running:
            self._running = False
        return samples, self._total
