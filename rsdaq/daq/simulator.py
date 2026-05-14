"""Simulator backend used when no MCC118 hardware is present.

Generates per-channel synthetic waveforms (sine + noise) at the configured
sample rate so the GUI can be developed and tested off the Pi.
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

import numpy as np

from rsdaq.config import AcquisitionConfig, ScanMode, INPUT_RANGE_V
from .backend import DaqBackend


class SimulatorBackend(DaqBackend):
    name = "Simulator"

    def __init__(self):
        self._cfg: Optional[AcquisitionConfig] = None
        self._t_start: float = 0.0
        self._produced: int = 0
        self._running = False

    def start(self, cfg: AcquisitionConfig) -> None:
        cfg.validate()
        self._cfg = cfg
        self._t_start = time.monotonic()
        self._produced = 0
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        if not self._running or self._cfg is None:
            return None

        cfg = self._cfg
        elapsed = time.monotonic() - self._t_start
        target = int(elapsed * cfg.sample_rate_hz)

        if cfg.scan_mode is ScanMode.FINITE:
            target = min(target, cfg.samples_per_channel)

        n = target - self._produced
        if n <= 0:
            time.sleep(min(timeout_s, 0.01))
            return None

        # Cap chunk size so we feed the GUI at a reasonable cadence.
        n = min(n, max(64, int(cfg.sample_rate_hz * 0.05)))

        idx = np.arange(self._produced, self._produced + n, dtype=np.float64)
        t = idx / cfg.sample_rate_hz
        rng = np.random.default_rng()

        cols = []
        for slot, ch in enumerate(cfg.enabled_channels):
            freq = 1.0 + 0.5 * ch          # 1, 1.5, 2.0 ... Hz
            amp = min(INPUT_RANGE_V, 1.0 + 0.25 * ch)
            phase = 0.3 * ch
            sig = amp * np.sin(2 * np.pi * freq * t + phase)
            noise = rng.normal(0.0, 0.02, size=n)
            cols.append(sig + noise)
        samples = np.stack(cols, axis=1).astype(np.float64)

        self._produced += n
        if cfg.scan_mode is ScanMode.FINITE and self._produced >= cfg.samples_per_channel:
            self._running = False
        return samples, self._produced

    @property
    def board_info(self) -> str:
        return "Simulator (no MCC118 detected)"
