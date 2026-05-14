"""Real MCC172 (IEPE / vibration / acoustic) backend.

The MCC172 is a 2-channel, 24-bit sigma-delta input HAT with per-channel:
    - IEPE excitation (constant-current source for accelerometers/mics)
    - AC/DC coupling
    - shared sigma-delta clock (multi-board: master/slave configuration)

This backend speaks the same ``ScanBackend`` interface as the MCC118 backend,
but consumes a ``Mcc172AcquisitionConfig`` (different rate constraints, no
aggregate-rate ceiling, only 2 channels).
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np

from rsdaq.config import Mcc172AcquisitionConfig, ScanMode
from .backend import ScanBackend

log = logging.getLogger(__name__)

try:
    from daqhats import mcc172, OptionFlags, SourceType  # type: ignore
    _HAS_DAQHATS = True
except Exception as _exc:  # pragma: no cover
    _HAS_DAQHATS = False
    _IMPORT_ERROR = _exc


class MCC172Backend(ScanBackend):
    """Single- or multi-board MCC172 backend (single-board fully tested,
    multi-board configures master/slave clock automatically)."""

    name = "MCC172"

    def __init__(self, addresses: Optional[List[int]] = None):
        if not _HAS_DAQHATS:
            raise RuntimeError(f"daqhats not available: {_IMPORT_ERROR}")
        if not addresses:
            raise RuntimeError("No MCC172 addresses provided.")
        self._addresses = sorted(set(int(a) for a in addresses))
        self._hats = {a: mcc172(a) for a in self._addresses}
        self._cfg: Optional[Mcc172AcquisitionConfig] = None
        self._running = False
        self._total = 0
        self._board_order: List[int] = []
        self._channels_per_board: List[List[int]] = []

    @property
    def board_info(self) -> str:
        return f"MCC172 x{len(self._addresses)} @ " + ", ".join(str(a) for a in self._addresses)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _channel_mask(channels) -> int:
        mask = 0
        for ch in channels:
            mask |= 1 << ch
        return mask

    # --------------------------------------------------------- lifecycle
    def start(self, cfg) -> None:
        if not isinstance(cfg, Mcc172AcquisitionConfig):
            raise TypeError("MCC172 backend requires Mcc172AcquisitionConfig")
        cfg.validate()
        for b in cfg.boards:
            if b.address not in self._hats:
                raise RuntimeError(
                    f"MCC172 address {b.address} not opened (have "
                    f"{sorted(self._hats.keys())}).")
        self._cfg = cfg
        self._total = 0
        self._board_order = [b.address for b in cfg.boards]
        self._channels_per_board = [list(b.enabled_channels) for b in cfg.boards]

        # Multi-board sync: first board is master, remaining are slaves.
        # daqhats: a_in_clock_config_write(clock_source, sample_rate)
        for i, board in enumerate(cfg.boards):
            hat = self._hats[board.address]
            for slot, ch in enumerate(board.enabled_channels):
                ch_cfg = (board.channel_configs[ch] if ch < len(board.channel_configs)
                          else None)
                if ch_cfg is None:
                    continue
                try:
                    hat.iepe_config_write(ch, 1 if ch_cfg.iepe_enabled else 0)
                except Exception:
                    log.exception("iepe_config_write failed (%d:%d)", board.address, ch)
            try:
                if i == 0:
                    hat.a_in_clock_config_write(SourceType.LOCAL, cfg.sample_rate_hz)
                else:
                    hat.a_in_clock_config_write(SourceType.SLAVE, cfg.sample_rate_hz)
            except Exception:
                log.exception("clock_config_write failed for board %d", board.address)

        # Wait for clock to stabilize on master
        master = self._hats[cfg.boards[0].address]
        try:
            # daqhats has a a_in_clock_config_read returning (source, rate, synced)
            for _ in range(50):
                _src, _rate, synced = master.a_in_clock_config_read()
                if synced:
                    break
        except Exception:
            log.debug("clock_config_read not available; continuing.")

        opts = OptionFlags.DEFAULT
        if cfg.scan_mode is ScanMode.CONTINUOUS:
            opts |= OptionFlags.CONTINUOUS
        samples = 0 if cfg.scan_mode is ScanMode.CONTINUOUS else cfg.samples_per_channel
        for board in cfg.boards:
            hat = self._hats[board.address]
            mask = self._channel_mask(board.enabled_channels)
            hat.a_in_scan_start(mask, samples, opts)
        self._running = True
        log.info("MCC172 scan started on %s @ %.1f Hz, opts=0x%x",
                 self._board_order, cfg.sample_rate_hz, int(opts))

    def stop(self) -> None:
        if not self._running:
            return
        for a in self._board_order:
            try:
                self._hats[a].a_in_scan_stop()
            except Exception:
                log.exception("MCC172 scan_stop failed for %d", a)
        for a in self._board_order:
            try:
                self._hats[a].a_in_scan_cleanup()
            except Exception:
                log.exception("MCC172 scan_cleanup failed for %d", a)
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        if not self._running or self._cfg is None:
            return None
        per_board: List[np.ndarray] = []
        any_running = False
        for a, channels in zip(self._board_order, self._channels_per_board):
            hat = self._hats[a]
            r = hat.a_in_scan_read_numpy(-1, timeout_s)
            if r.hardware_overrun or r.buffer_overrun:
                log.error("MCC172 %d overrun (hw=%s buf=%s)",
                          a, r.hardware_overrun, r.buffer_overrun)
            if r.running:
                any_running = True
            data = r.data
            if data is None or data.size == 0:
                per_board.append(np.empty((0, len(channels)), dtype=np.float64))
            else:
                per_board.append(data.reshape(-1, len(channels)))
        n = min((m.shape[0] for m in per_board), default=0)
        if n == 0:
            if not any_running:
                self._running = False
            return None
        cols = [m[:n] for m in per_board]
        samples = np.concatenate(cols, axis=1) if cols else \
            np.empty((n, 0), dtype=np.float64)
        self._total += n
        if not any_running:
            self._running = False
        return samples, self._total
