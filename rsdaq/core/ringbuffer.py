"""Lock-protected, fixed-capacity, multi-channel ring buffer.

Stores up to ``capacity`` samples per channel for live plotting. Old samples
are overwritten when full. Reads return the buffer in chronological order.
"""
from __future__ import annotations

import threading
from typing import Tuple

import numpy as np


class RingBuffer:
    def __init__(self, capacity: int, n_channels: int):
        self._cap = int(capacity)
        self._n_ch = int(n_channels)
        self._buf = np.zeros((self._cap, self._n_ch), dtype=np.float64)
        self._head = 0       # next write position
        self._size = 0       # current valid samples
        self._total = 0      # total samples ever written
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._cap

    @property
    def n_channels(self) -> int:
        return self._n_ch

    def reset(self) -> None:
        with self._lock:
            self._head = 0
            self._size = 0
            self._total = 0

    def write(self, samples: np.ndarray) -> None:
        if samples.ndim != 2 or samples.shape[1] != self._n_ch:
            raise ValueError(
                f"expected shape (n,{self._n_ch}), got {samples.shape}")
        n = samples.shape[0]
        if n == 0:
            return
        with self._lock:
            if n >= self._cap:
                # Only the last `cap` samples survive.
                self._buf[:] = samples[-self._cap:]
                self._head = 0
                self._size = self._cap
            else:
                end = self._head + n
                if end <= self._cap:
                    self._buf[self._head:end] = samples
                else:
                    first = self._cap - self._head
                    self._buf[self._head:] = samples[:first]
                    self._buf[: n - first] = samples[first:]
                self._head = end % self._cap
                self._size = min(self._cap, self._size + n)
            self._total += n

    def snapshot(self) -> Tuple[np.ndarray, int]:
        """Return ``(data_in_chronological_order, total_written)``."""
        with self._lock:
            if self._size == 0:
                return np.empty((0, self._n_ch), dtype=np.float64), self._total
            if self._size < self._cap:
                out = self._buf[: self._size].copy()
            else:
                out = np.concatenate(
                    (self._buf[self._head:], self._buf[: self._head]), axis=0)
            return out, self._total
