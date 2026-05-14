"""Per-channel running statistics computed incrementally."""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass
class ChannelStats:
    count: int = 0
    last: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf
    sum_: float = 0.0
    sum_sq: float = 0.0

    @property
    def mean(self) -> float:
        return self.sum_ / self.count if self.count else 0.0

    @property
    def rms(self) -> float:
        return math.sqrt(self.sum_sq / self.count) if self.count else 0.0

    def reset(self) -> None:
        self.count = 0
        self.last = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf
        self.sum_ = 0.0
        self.sum_sq = 0.0


class StatsTracker:
    """Holds one ChannelStats per enabled channel."""

    def __init__(self, n_channels: int):
        self.stats = [ChannelStats() for _ in range(n_channels)]

    def reset(self) -> None:
        for s in self.stats:
            s.reset()

    def update(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        for i, s in enumerate(self.stats):
            col = samples[:, i]
            s.count += col.size
            s.last = float(col[-1])
            s.minimum = float(min(s.minimum, col.min()))
            s.maximum = float(max(s.maximum, col.max()))
            s.sum_ += float(col.sum())
            s.sum_sq += float(np.dot(col, col))
