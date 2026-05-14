"""Acquisition configuration objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class TriggerMode(str, Enum):
    IMMEDIATE = "Immediate"
    SOFTWARE = "Software"
    EXTERNAL_RISING = "External rising edge"
    EXTERNAL_FALLING = "External falling edge"


class ScanMode(str, Enum):
    CONTINUOUS = "Continuous"
    FINITE = "Finite"


# MCC118 hardware constants
MAX_AGGREGATE_RATE_HZ = 100_000  # 100 kS/s shared across enabled channels
NUM_CHANNELS = 8
INPUT_RANGE_V = 10.0  # +/- 10 V


@dataclass
class AcquisitionConfig:
    enabled_channels: List[int] = field(default_factory=lambda: [0])
    sample_rate_hz: float = 1000.0          # per-channel rate
    samples_per_channel: int = 10_000       # only used in FINITE mode
    scan_mode: ScanMode = ScanMode.CONTINUOUS
    trigger_mode: TriggerMode = TriggerMode.IMMEDIATE
    plot_window_seconds: float = 5.0
    record_to_file: bool = False
    record_path: str = ""

    @property
    def aggregate_rate_hz(self) -> float:
        return self.sample_rate_hz * max(1, len(self.enabled_channels))

    def validate(self) -> None:
        if not self.enabled_channels:
            raise ValueError("At least one channel must be enabled.")
        for ch in self.enabled_channels:
            if not 0 <= ch < NUM_CHANNELS:
                raise ValueError(f"Channel {ch} out of range 0..{NUM_CHANNELS - 1}.")
        if self.sample_rate_hz <= 0:
            raise ValueError("Sample rate must be positive.")
        if self.aggregate_rate_hz > MAX_AGGREGATE_RATE_HZ:
            raise ValueError(
                f"Aggregate rate {self.aggregate_rate_hz:.0f} Hz exceeds MCC118 "
                f"limit of {MAX_AGGREGATE_RATE_HZ} S/s. "
                f"Reduce sample rate or disable channels."
            )
        if self.scan_mode is ScanMode.FINITE and self.samples_per_channel <= 0:
            raise ValueError("Samples per channel must be positive in finite mode.")
