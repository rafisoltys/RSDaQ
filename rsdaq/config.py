"""Acquisition configuration objects."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TriggerMode(str, Enum):
    IMMEDIATE = "Immediate"
    SOFTWARE_LEVEL = "Software (level)"
    EXTERNAL_RISING = "External rising edge"
    EXTERNAL_FALLING = "External falling edge"


class TriggerRunMode(str, Enum):
    """How the acquisition behaves with respect to triggers (software trigger)."""
    FREE_RUN = "Free run"      # no gating: every sample is shown
    NORMAL = "Normal"          # capture and re-arm after each trigger
    SINGLE = "Single"          # capture once and stop


class TriggerSlope(str, Enum):
    RISING = "Rising"
    FALLING = "Falling"


class ScanMode(str, Enum):
    CONTINUOUS = "Continuous"
    FINITE = "Finite"


class FFTWindow(str, Enum):
    HANN = "Hann"
    HAMMING = "Hamming"
    BLACKMAN = "Blackman"
    RECT = "Rectangular"


# MCC118 hardware constants
MAX_AGGREGATE_RATE_HZ = 100_000  # 100 kS/s shared across enabled channels (per board)
NUM_CHANNELS_118 = 8
INPUT_RANGE_V = 10.0  # +/- 10 V

# MCC134 / MCC152 channel counts
NUM_CHANNELS_134 = 4
NUM_AO_152 = 2
NUM_DIO_152 = 8

# MCC172 hardware constants
NUM_CHANNELS_172 = 2
MAX_RATE_172_HZ = 51_200            # per-channel max (sigma-delta)
MIN_RATE_172_HZ = 200
INPUT_RANGE_172_V = 5.0


class CouplingMode(str, Enum):
    AC = "AC"
    DC = "DC"


class SensitivityUnit(str, Enum):
    """Sensor sensitivity units used by the MCC172 panel."""
    MV_PER_G = "mV/g"           # accelerometers
    MV_PER_PA = "mV/Pa"         # microphones
    MV_PER_V = "mV/V"           # passthrough (no scaling)


@dataclass
class IEPEChannelConfig:
    """Per-channel MCC172 settings (IEPE excitation / coupling / sensitivity)."""
    iepe_enabled: bool = False
    coupling: CouplingMode = CouplingMode.DC
    sensitivity_mv_per_unit: float = 1000.0  # mV per engineering unit (g, Pa, ...)
    unit: SensitivityUnit = SensitivityUnit.MV_PER_V


@dataclass
class BoardSelection:
    """One MCC118 board participating in an acquisition."""
    address: int
    enabled_channels: List[int] = field(default_factory=lambda: [0])

    def validate(self) -> None:
        if not self.enabled_channels:
            raise ValueError(f"Board {self.address}: at least one channel required.")
        for ch in self.enabled_channels:
            if not 0 <= ch < NUM_CHANNELS_118:
                raise ValueError(
                    f"Board {self.address}: channel {ch} out of range "
                    f"0..{NUM_CHANNELS_118 - 1}.")


@dataclass
class SoftwareTriggerConfig:
    enabled: bool = False
    run_mode: TriggerRunMode = TriggerRunMode.FREE_RUN
    source: int = 0           # logical channel index (across all boards) to monitor
    level_v: float = 0.0
    slope: TriggerSlope = TriggerSlope.RISING
    pre_samples: int = 256
    post_samples: int = 1024
    rearm_holdoff_samples: int = 0


@dataclass
class FFTConfig:
    enabled: bool = True
    size: int = 4096          # power of two recommended
    window: FFTWindow = FFTWindow.HANN
    log_y: bool = True


@dataclass
class AcquisitionConfig:
    """Complete description of one MCC118 acquisition (possibly multi-board)."""

    boards: List[BoardSelection] = field(default_factory=list)
    sample_rate_hz: float = 1000.0          # per-channel rate (same on every board)
    samples_per_channel: int = 10_000       # only used in FINITE mode
    scan_mode: ScanMode = ScanMode.CONTINUOUS
    trigger_mode: TriggerMode = TriggerMode.IMMEDIATE
    plot_window_seconds: float = 5.0
    record_to_file: bool = False
    record_path: str = ""
    apply_calibration: bool = True
    software_trigger: SoftwareTriggerConfig = field(default_factory=SoftwareTriggerConfig)
    fft: FFTConfig = field(default_factory=FFTConfig)

    # ---------- back-compat shims used by existing UI / docs ----------
    @property
    def enabled_channels(self) -> List[int]:
        if not self.boards:
            return []
        return list(self.boards[0].enabled_channels)

    @enabled_channels.setter
    def enabled_channels(self, channels: List[int]) -> None:
        if not self.boards:
            self.boards = [BoardSelection(address=0, enabled_channels=list(channels))]
        else:
            self.boards[0].enabled_channels = list(channels)

    # ---------------- properties / validation ----------------
    @property
    def total_channels(self) -> int:
        return sum(len(b.enabled_channels) for b in self.boards)

    @property
    def aggregate_rate_hz_per_board(self) -> float:
        """Worst-case aggregate sample rate on a single board."""
        if not self.boards:
            return 0.0
        return self.sample_rate_hz * max(len(b.enabled_channels) for b in self.boards)

    def channel_labels(self) -> List[str]:
        labels: List[str] = []
        for b in self.boards:
            for ch in b.enabled_channels:
                labels.append(f"B{b.address}:CH{ch}")
        return labels

    def validate(self) -> None:
        if not self.boards:
            raise ValueError("At least one MCC118 board must be selected.")
        seen = set()
        for b in self.boards:
            if b.address in seen:
                raise ValueError(f"Duplicate board address {b.address}.")
            seen.add(b.address)
            b.validate()
        if self.sample_rate_hz <= 0:
            raise ValueError("Sample rate must be positive.")
        if self.aggregate_rate_hz_per_board > MAX_AGGREGATE_RATE_HZ:
            raise ValueError(
                f"Per-board aggregate {self.aggregate_rate_hz_per_board:.0f} Hz "
                f"exceeds MCC118 limit of {MAX_AGGREGATE_RATE_HZ} S/s. "
                f"Reduce sample rate or disable channels."
            )
        if self.scan_mode is ScanMode.FINITE and self.samples_per_channel <= 0:
            raise ValueError("Samples per channel must be positive in finite mode.")
        if self.software_trigger.enabled:
            if not 0 <= self.software_trigger.source < self.total_channels:
                raise ValueError(
                    f"Software trigger source {self.software_trigger.source} "
                    f"is outside enabled-channel range "
                    f"0..{self.total_channels - 1}.")
            if self.software_trigger.pre_samples < 0 or self.software_trigger.post_samples <= 0:
                raise ValueError("Trigger pre_samples >= 0 and post_samples > 0 required.")
        if self.fft.size < 32 or (self.fft.size & (self.fft.size - 1)) != 0:
            raise ValueError("FFT size must be a power of two >= 32.")


@dataclass
class Mcc172BoardSelection:
    """One MCC172 board: up to 2 channels with per-channel IEPE / coupling settings."""
    address: int
    enabled_channels: List[int] = field(default_factory=lambda: [0, 1])
    channel_configs: List[IEPEChannelConfig] = field(
        default_factory=lambda: [IEPEChannelConfig(), IEPEChannelConfig()])

    def validate(self) -> None:
        if not self.enabled_channels:
            raise ValueError(f"MCC172 #{self.address}: at least one channel required.")
        for ch in self.enabled_channels:
            if not 0 <= ch < NUM_CHANNELS_172:
                raise ValueError(
                    f"MCC172 #{self.address}: channel {ch} out of range "
                    f"0..{NUM_CHANNELS_172 - 1}.")


@dataclass
class Mcc172AcquisitionConfig:
    """Acquisition descriptor for one or more MCC172 boards (single-board for now)."""
    boards: List[Mcc172BoardSelection] = field(default_factory=list)
    sample_rate_hz: float = 10_240.0    # per-channel rate (sigma-delta, multi-board master)
    samples_per_channel: int = 10_000
    scan_mode: "ScanMode" = field(default=None)  # type: ignore[assignment]
    plot_window_seconds: float = 2.0
    record_to_file: bool = False
    record_path: str = ""
    apply_calibration: bool = True

    def __post_init__(self):
        if self.scan_mode is None:
            self.scan_mode = ScanMode.CONTINUOUS

    def channel_labels(self) -> List[str]:
        out: List[str] = []
        for b in self.boards:
            for ch in b.enabled_channels:
                out.append(f"M172#{b.address}:CH{ch}")
        return out

    @property
    def total_channels(self) -> int:
        return sum(len(b.enabled_channels) for b in self.boards)

    def validate(self) -> None:
        if not self.boards:
            raise ValueError("At least one MCC172 board must be selected.")
        seen = set()
        for b in self.boards:
            if b.address in seen:
                raise ValueError(f"Duplicate MCC172 address {b.address}.")
            seen.add(b.address)
            b.validate()
        if not (MIN_RATE_172_HZ <= self.sample_rate_hz <= MAX_RATE_172_HZ):
            raise ValueError(
                f"MCC172 sample rate {self.sample_rate_hz:.0f} Hz out of "
                f"range {MIN_RATE_172_HZ}..{MAX_RATE_172_HZ}.")
        if self.scan_mode is ScanMode.FINITE and self.samples_per_channel <= 0:
            raise ValueError("Samples per channel must be positive in finite mode.")




# Convenience for tests / docs / migration (legacy alias)
NUM_CHANNELS = NUM_CHANNELS_118
