"""Abstract backend interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import numpy as np

from rsdaq.config import AcquisitionConfig


class DaqBackend(ABC):
    """Interface every concrete backend must implement.

    All read calls must be non-blocking-ish (block at most a short timeout)
    and return as soon as samples are available.
    """

    name: str = "abstract"

    @abstractmethod
    def start(self, cfg: AcquisitionConfig) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def read(self, timeout_s: float = 0.1) -> Optional[Tuple[np.ndarray, int]]:
        """Return ``(samples, total_count)`` or ``None`` if no data yet.

        ``samples`` is a 2-D ndarray of shape ``(n_samples, n_enabled_channels)``
        in volts. ``total_count`` is the per-channel count read so far in
        the active acquisition.
        """

    @abstractmethod
    def is_running(self) -> bool: ...

    @property
    def board_info(self) -> str:
        return self.name
