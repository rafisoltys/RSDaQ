"""Abstract backend interfaces.

Three independent ABCs because the boards do completely different things:

    ScanBackend         - streaming analog input (MCC118)
    ThermocoupleBackend - polled slow temperature read (MCC134)
    OutputBackend       - analog output + DIO (MCC152)

For backwards compatibility, ``DaqBackend`` is an alias for ``ScanBackend``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Sequence, Tuple

import numpy as np

from rsdaq.config import AcquisitionConfig


# --------------------------------------------------------------------- scan
class ScanBackend(ABC):
    """Streaming analog-input backend (used by MCC118)."""

    name: str = "abstract-scan"

    @abstractmethod
    def start(self, cfg: AcquisitionConfig) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        """Return ``(samples, total_count)`` or ``None`` if no data yet.

        ``samples`` shape ``(n, total_channels)`` in volts. Channel order is
        determined by ``cfg.channel_labels()`` (board-by-board, ascending
        channel index within each board). ``total_count`` is the per-channel
        count read so far in the active acquisition.
        """

    @abstractmethod
    def is_running(self) -> bool: ...

    @property
    def board_info(self) -> str:
        return self.name


# Backwards-compatible alias.
DaqBackend = ScanBackend


# ------------------------------------------------------------ thermocouple
class ThermocoupleBackend(ABC):
    """Slow polled thermocouple read (used by MCC134)."""

    name: str = "abstract-tc"

    @abstractmethod
    def open(self, address: int) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def set_tc_type(self, channel: int, tc_type: str) -> None:
        """``tc_type`` is one of 'J','K','T','E','R','S','B','N' or 'DISABLED'."""

    @abstractmethod
    def read_temperatures(self) -> List[Optional[float]]:
        """Return list of 4 temperatures in degrees Celsius (or ``None`` if open/disabled)."""

    @abstractmethod
    def read_cjc(self) -> List[Optional[float]]:
        """Return cold-junction temperatures (one per channel, deg C)."""


# ------------------------------------------------------------------ output
class OutputBackend(ABC):
    """Analog output + DIO (used by MCC152)."""

    name: str = "abstract-out"

    @abstractmethod
    def open(self, address: int) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    # Analog out
    @abstractmethod
    def set_ao(self, channel: int, voltage: float) -> None: ...

    @abstractmethod
    def get_ao(self, channel: int) -> float: ...

    # Digital IO
    @abstractmethod
    def set_dio_direction(self, bit: int, output: bool) -> None: ...

    @abstractmethod
    def get_dio_direction(self, bit: int) -> bool: ...

    @abstractmethod
    def set_dio(self, bit: int, value: bool) -> None: ...

    @abstractmethod
    def get_dio(self, bit: int) -> bool: ...
