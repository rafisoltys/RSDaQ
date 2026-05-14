"""Real MCC118 backend using Digilent's daqhats library."""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np

from rsdaq.config import AcquisitionConfig, ScanMode, TriggerMode
from .backend import DaqBackend

log = logging.getLogger(__name__)

# Imported lazily so non-Pi machines don't blow up at import time.
try:
    from daqhats import mcc118, OptionFlags, TriggerModes, HatIDs, hat_list  # type: ignore
    _HAS_DAQHATS = True
except Exception as _exc:  # pragma: no cover
    _HAS_DAQHATS = False
    _IMPORT_ERROR = _exc


class MCC118Backend(DaqBackend):
    name = "MCC118"

    def __init__(self, address: Optional[int] = None):
        if not _HAS_DAQHATS:
            raise RuntimeError(f"daqhats not available: {_IMPORT_ERROR}")

        if address is None:
            boards = hat_list(filter_by_id=HatIDs.MCC_118)
            if not boards:
                raise RuntimeError("No MCC118 board detected on the SPI bus.")
            address = boards[0].address
            log.info("Using MCC118 at address %d", address)
        self._addr = address
        self._hat = mcc118(address)
        self._cfg: Optional[AcquisitionConfig] = None
        self._running = False
        self._total = 0

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _channel_mask(channels) -> int:
        mask = 0
        for ch in channels:
            mask |= 1 << ch
        return mask

    @staticmethod
    def _trigger_mode(tm: TriggerMode):
        return {
            TriggerMode.IMMEDIATE: TriggerModes.RISING_EDGE,  # ignored when no trigger flag
            TriggerMode.SOFTWARE: TriggerModes.RISING_EDGE,   # daqhats has no SW trig; use immediate
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

    # --------------------------------------------------------------- lifecycle
    def start(self, cfg: AcquisitionConfig) -> None:
        cfg.validate()
        self._cfg = cfg
        self._total = 0

        mask = self._channel_mask(cfg.enabled_channels)
        samples = 0 if cfg.scan_mode is ScanMode.CONTINUOUS else cfg.samples_per_channel
        opts = self._options(cfg)

        if opts & OptionFlags.EXTTRIGGER:
            self._hat.trigger_mode(self._trigger_mode(cfg.trigger_mode))

        self._hat.a_in_scan_start(mask, samples, cfg.sample_rate_hz, opts)
        self._running = True
        log.info("MCC118 scan started: mask=0x%02x rate=%.1f Hz opts=0x%x",
                 mask, cfg.sample_rate_hz, int(opts))

    def stop(self) -> None:
        if self._running:
            try:
                self._hat.a_in_scan_stop()
            finally:
                self._hat.a_in_scan_cleanup()
                self._running = False

    def is_running(self) -> bool:
        return self._running

    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        if not self._running or self._cfg is None:
            return None
        # -1 = read all available samples right now.
        result = self._hat.a_in_scan_read_numpy(-1, timeout_s)
        if result.hardware_overrun or result.buffer_overrun:
            log.error("MCC118 overrun (hw=%s buf=%s)",
                      result.hardware_overrun, result.buffer_overrun)
        data = result.data
        if data is None or data.size == 0:
            if not result.running:
                self._running = False
            return None
        n_ch = len(self._cfg.enabled_channels)
        samples = data.reshape(-1, n_ch)
        self._total += samples.shape[0]
        if not result.running:
            self._running = False
        return samples, self._total

    @property
    def board_info(self) -> str:
        return f"MCC118 @ address {self._addr}"
