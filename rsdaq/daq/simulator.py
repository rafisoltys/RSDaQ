"""Simulator backends (scan, thermocouple, output).

Used when no real hardware is present, but also driven on the Pi if the
operator forces ``--backend simulator``. The scan simulator can model multiple
"virtual" MCC118 boards in a single backend.
"""
from __future__ import annotations

import math
import random
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from rsdaq.config import (
    AcquisitionConfig, INPUT_RANGE_V, INPUT_RANGE_172_V, Mcc172AcquisitionConfig,
    NUM_CHANNELS_134, NUM_AO_152, NUM_DIO_152, ScanMode,
)
from .backend import OutputBackend, ScanBackend, ThermocoupleBackend


# --------------------------------------------------------------------- scan
class SimulatorScanBackend(ScanBackend):
    """Single- or multi-board MCC118 simulator.

    Synthesises a sine + Gaussian noise per channel. Each (board, channel) gets
    a deterministic frequency / amplitude / phase so traces are visually
    distinguishable.
    """

    name = "Simulator (MCC118)"

    def __init__(self, addresses: Optional[List[int]] = None):
        self._addresses = list(addresses) if addresses else None
        self._cfg: Optional[AcquisitionConfig] = None
        self._t_start: float = 0.0
        self._produced: int = 0
        self._running = False

    @property
    def board_info(self) -> str:
        if self._addresses:
            return f"Simulator (MCC118 x{len(self._addresses)})"
        return self.name

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

    def _signal_for(self, address: int, channel: int, t: np.ndarray) -> np.ndarray:
        seed = (address * 13 + channel * 7) % 100
        freq = 1.0 + 0.5 * channel + 0.25 * address
        amp = min(INPUT_RANGE_V, 1.0 + 0.25 * channel + 0.05 * address)
        phase = 0.3 * channel + 0.2 * address
        rng = np.random.default_rng(seed=int(t[0] * 1e6) ^ seed)
        sig = amp * np.sin(2 * np.pi * freq * t + phase)
        noise = rng.normal(0.0, 0.02, size=t.size)
        return sig + noise

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
        n = min(n, max(64, int(cfg.sample_rate_hz * 0.05)))

        idx = np.arange(self._produced, self._produced + n, dtype=np.float64)
        t = idx / cfg.sample_rate_hz

        cols: List[np.ndarray] = []
        for board in cfg.boards:
            for ch in board.enabled_channels:
                cols.append(self._signal_for(board.address, ch, t))
        samples = np.stack(cols, axis=1).astype(np.float64) if cols else \
            np.empty((n, 0), dtype=np.float64)

        self._produced += n
        if cfg.scan_mode is ScanMode.FINITE and self._produced >= cfg.samples_per_channel:
            self._running = False
        return samples, self._produced


# Backwards-compatible alias used by older code paths.
SimulatorBackend = SimulatorScanBackend


# --------------------------------------------------------- vibration (172)
class SimulatorMcc172Backend(ScanBackend):
    """Simulated MCC172: 2 channels, sigma-delta-style synthesised vibration.

    Signal: per-channel sum of two tones with weak harmonics + Gaussian noise.
    IEPE-on channels include a small DC bias (~12 V on real hardware; here we
    emit ~0.5 V into the band-limited model so the AC plot shows it cleanly).
    """

    name = "Simulator (MCC172)"

    def __init__(self, addresses: Optional[List[int]] = None):
        self._addresses = list(addresses) if addresses else None
        self._cfg: Optional[Mcc172AcquisitionConfig] = None
        self._t_start: float = 0.0
        self._produced: int = 0
        self._running = False

    @property
    def board_info(self) -> str:
        if self._addresses:
            return f"Simulator (MCC172 x{len(self._addresses)})"
        return self.name

    def start(self, cfg) -> None:
        if not isinstance(cfg, Mcc172AcquisitionConfig):
            raise TypeError("MCC172 simulator requires Mcc172AcquisitionConfig")
        cfg.validate()
        self._cfg = cfg
        self._t_start = time.monotonic()
        self._produced = 0
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _signal_for(self, board, ch: int, t: np.ndarray) -> np.ndarray:
        # Two tones per channel (e.g. fundamental 60 Hz + harmonic) plus noise.
        seed = (board.address * 17 + ch * 11) % 999
        f1 = 60.0 + 5.0 * ch + 2.5 * board.address
        f2 = 2.0 * f1
        amp = 0.6 if ch == 0 else 0.4
        rng = np.random.default_rng(seed=int(t[0] * 1e6) ^ seed)
        sig = amp * np.sin(2 * np.pi * f1 * t) + 0.25 * amp * np.sin(2 * np.pi * f2 * t)
        sig += rng.normal(0.0, 0.02, size=t.size)
        # Reflect IEPE bias (small to keep within ±5 V).
        ch_cfg = board.channel_configs[ch] if ch < len(board.channel_configs) else None
        if ch_cfg is not None and ch_cfg.iepe_enabled:
            sig += 0.5
        return np.clip(sig, -INPUT_RANGE_172_V, INPUT_RANGE_172_V)

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
        n = min(n, max(64, int(cfg.sample_rate_hz * 0.05)))
        idx = np.arange(self._produced, self._produced + n, dtype=np.float64)
        t = idx / cfg.sample_rate_hz

        cols: List[np.ndarray] = []
        for board in cfg.boards:
            for ch in board.enabled_channels:
                cols.append(self._signal_for(board, ch, t))
        samples = np.stack(cols, axis=1).astype(np.float64) if cols else \
            np.empty((n, 0), dtype=np.float64)
        self._produced += n
        if cfg.scan_mode is ScanMode.FINITE and self._produced >= cfg.samples_per_channel:
            self._running = False
        return samples, self._produced


# ------------------------------------------------------------ thermocouple
class SimulatorTCBackend(ThermocoupleBackend):
    """Simulated MCC134: drifts a "room temperature" plus per-channel offset."""

    name = "Simulator (MCC134)"

    def __init__(self):
        self._addr: Optional[int] = None
        self._tc_types: List[str] = ["DISABLED"] * NUM_CHANNELS_134
        self._t0 = time.monotonic()
        self._room = 22.0  # deg C
        self._biases = [0.0, 5.0, -3.0, 12.0]

    def open(self, address: int) -> None:
        self._addr = address

    def close(self) -> None:
        self._addr = None

    def set_tc_type(self, channel: int, tc_type: str) -> None:
        self._tc_types[channel] = tc_type.upper()

    def read_temperatures(self) -> List[Optional[float]]:
        elapsed = time.monotonic() - self._t0
        out: List[Optional[float]] = []
        for ch in range(NUM_CHANNELS_134):
            if self._tc_types[ch] in ("DISABLED", ""):
                out.append(None)
                continue
            wave = 1.5 * math.sin(2 * math.pi * 0.05 * elapsed + ch * 0.6)
            jitter = random.uniform(-0.05, 0.05)
            out.append(self._room + self._biases[ch] + wave + jitter)
        return out

    def read_cjc(self) -> List[Optional[float]]:
        return [self._room + random.uniform(-0.05, 0.05)
                for _ in range(NUM_CHANNELS_134)]


# ------------------------------------------------------------------ output
class SimulatorOutputBackend(OutputBackend):
    name = "Simulator (MCC152)"

    def __init__(self):
        self._addr: Optional[int] = None
        self._ao = [0.0] * NUM_AO_152
        self._dio_dir = [False] * NUM_DIO_152   # False = output, True = input
        self._dio_val = [False] * NUM_DIO_152

    def open(self, address: int) -> None:
        self._addr = address

    def close(self) -> None:
        self._addr = None

    def set_ao(self, channel: int, voltage: float) -> None:
        self._ao[channel] = max(0.0, min(5.0, float(voltage)))

    def get_ao(self, channel: int) -> float:
        return self._ao[channel]

    def set_dio_direction(self, bit: int, output: bool) -> None:
        # output=True means the bit is driven by us; mapping: dir flag stored as `not output`
        self._dio_dir[bit] = not output

    def get_dio_direction(self, bit: int) -> bool:
        return not self._dio_dir[bit]

    def set_dio(self, bit: int, value: bool) -> None:
        if not self._dio_dir[bit]:  # output mode
            self._dio_val[bit] = bool(value)

    def get_dio(self, bit: int) -> bool:
        # Inputs report a "floating" pseudo-random value if not explicitly set.
        return self._dio_val[bit]
