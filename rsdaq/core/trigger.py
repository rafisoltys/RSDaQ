"""Software trigger: level-crossing detector with pre/post sample window.

Operates on a single channel of the streaming sample matrix. The detector
maintains a small ring buffer of "pre" samples; once a level crossing fires,
it collects ``post`` samples and emits a complete capture event.

Modes:
    FREE_RUN: trigger never fires (used for live free-running display).
    NORMAL:   re-arms after each capture; emits one event per crossing.
    SINGLE:   captures once and disables itself.

The detector is intentionally pure-Python / NumPy: zero Qt deps so it is
trivially unit-testable.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, Optional

import numpy as np

from rsdaq.config import SoftwareTriggerConfig, TriggerRunMode, TriggerSlope


class TriggerState(str, Enum):
    DISABLED = "disabled"
    ARMED = "armed"
    CAPTURING = "capturing"
    DONE = "done"


@dataclass
class TriggerEvent:
    sample_index: int       # global sample index of the crossing point
    pre: np.ndarray         # shape (pre_samples, n_channels)
    post: np.ndarray        # shape (post_samples, n_channels)

    @property
    def waveform(self) -> np.ndarray:
        return np.concatenate([self.pre, self.post], axis=0)

    @property
    def n_pre(self) -> int:
        return self.pre.shape[0]


@dataclass
class SoftwareTrigger:
    cfg: SoftwareTriggerConfig
    n_channels: int
    state: TriggerState = TriggerState.ARMED
    _pre: Deque[np.ndarray] = field(default_factory=deque, repr=False)
    _pre_count: int = 0
    _post_collected: List[np.ndarray] = field(default_factory=list, repr=False)
    _post_count: int = 0
    _trigger_sample_index: int = 0
    _last_value: Optional[float] = None
    _holdoff_remaining: int = 0
    _samples_seen: int = 0

    def __post_init__(self):
        if not self.cfg.enabled or self.cfg.run_mode is TriggerRunMode.FREE_RUN:
            self.state = TriggerState.DISABLED
        else:
            self.state = TriggerState.ARMED

    # ----------------------------------------------------- helpers
    def reset(self) -> None:
        self._pre.clear()
        self._pre_count = 0
        self._post_collected.clear()
        self._post_count = 0
        self._last_value = None
        self._holdoff_remaining = 0
        if self.cfg.enabled and self.cfg.run_mode is not TriggerRunMode.FREE_RUN:
            self.state = TriggerState.ARMED
        else:
            self.state = TriggerState.DISABLED

    def _push_pre(self, samples: np.ndarray) -> None:
        cap = max(0, self.cfg.pre_samples)
        if cap == 0:
            return
        self._pre.append(samples)
        self._pre_count += samples.shape[0]
        # Trim oldest blocks until we hold at most `cap` samples.
        while self._pre_count - self._pre[0].shape[0] >= cap:
            dropped = self._pre.popleft()
            self._pre_count -= dropped.shape[0]
        # Trim leading rows of the oldest block if still too many.
        if self._pre_count > cap:
            excess = self._pre_count - cap
            head = self._pre[0]
            self._pre[0] = head[excess:]
            self._pre_count -= excess

    def _take_pre(self) -> np.ndarray:
        if not self._pre:
            return np.empty((0, self.n_channels), dtype=np.float64)
        out = np.concatenate(list(self._pre), axis=0)
        # Truncate to configured pre length (just in case).
        cap = max(0, self.cfg.pre_samples)
        if out.shape[0] > cap:
            out = out[-cap:]
        return out

    def _check_crossing(self, col: np.ndarray) -> int:
        """Return relative index of the first crossing in ``col`` or -1.

        A "rising crossing" happens at the first index ``i`` such that the
        previous value ``< level`` and ``col[i] >= level`` (analogous for
        falling). The previous value is either ``self._last_value`` (if the
        detector has already seen samples), or there is no detectable crossing
        for the very first sample of the very first feed.
        """
        if col.size == 0:
            return -1
        level = self.cfg.level_v
        if self._last_value is None:
            # No "previous" yet: first detectable crossing involves col[0..1].
            search = col
            base = 1
        else:
            search = np.concatenate(([self._last_value], col))
            base = 0

        if self.cfg.slope is TriggerSlope.RISING:
            mask = (search[:-1] < level) & (search[1:] >= level)
        else:
            mask = (search[:-1] > level) & (search[1:] <= level)

        if not mask.any():
            return -1
        return int(np.argmax(mask)) + base

    # ------------------------------------------------------ feed
    def feed(self, samples: np.ndarray) -> List[TriggerEvent]:
        """Feed a chunk of samples; return any completed trigger events."""
        events: List[TriggerEvent] = []
        if samples.size == 0 or self.state is TriggerState.DISABLED:
            self._samples_seen += samples.shape[0]
            if samples.size:
                self._last_value = float(samples[-1, self.cfg.source])
            return events

        idx_in_block = 0
        n = samples.shape[0]

        while idx_in_block < n:
            chunk = samples[idx_in_block:]

            if self.state is TriggerState.ARMED:
                if self._holdoff_remaining > 0:
                    take = min(self._holdoff_remaining, chunk.shape[0])
                    self._push_pre(chunk[:take])
                    self._holdoff_remaining -= take
                    self._last_value = float(chunk[take - 1, self.cfg.source])
                    idx_in_block += take
                    self._samples_seen += take
                    continue

                col = chunk[:, self.cfg.source]
                rel = self._check_crossing(col)
                if rel < 0:
                    # No crossing in this whole chunk — push it all to pre.
                    self._push_pre(chunk)
                    self._last_value = float(col[-1])
                    self._samples_seen += chunk.shape[0]
                    idx_in_block += chunk.shape[0]
                    continue

                # Push everything up to and including the crossing into pre.
                upto = rel + 1
                self._push_pre(chunk[:upto])
                self._trigger_sample_index = self._samples_seen + rel
                self._last_value = float(col[rel])
                idx_in_block += upto
                self._samples_seen += upto
                self.state = TriggerState.CAPTURING
                self._post_collected.clear()
                self._post_count = 0
                continue

            if self.state is TriggerState.CAPTURING:
                need = self.cfg.post_samples - self._post_count
                take = min(need, chunk.shape[0])
                if take > 0:
                    self._post_collected.append(chunk[:take])
                    self._post_count += take
                    self._last_value = float(chunk[take - 1, self.cfg.source])
                    idx_in_block += take
                    self._samples_seen += take
                if self._post_count >= self.cfg.post_samples:
                    pre = self._take_pre()
                    post = (np.concatenate(self._post_collected, axis=0)
                            if self._post_collected else
                            np.empty((0, self.n_channels), dtype=np.float64))
                    events.append(TriggerEvent(
                        sample_index=self._trigger_sample_index,
                        pre=pre, post=post[: self.cfg.post_samples],
                    ))
                    # Re-arm or finish.
                    self._post_collected.clear()
                    self._post_count = 0
                    if self.cfg.run_mode is TriggerRunMode.SINGLE:
                        self.state = TriggerState.DONE
                        # consume any remaining samples without further triggers
                        rem = n - idx_in_block
                        if rem > 0:
                            self._samples_seen += rem
                            idx_in_block = n
                            self._last_value = float(samples[-1, self.cfg.source])
                    else:
                        self.state = TriggerState.ARMED
                        self._holdoff_remaining = max(0, self.cfg.rearm_holdoff_samples)
                continue

            # state DONE: pass-through
            rem = n - idx_in_block
            self._samples_seen += rem
            self._last_value = float(samples[-1, self.cfg.source])
            idx_in_block = n

        return events

    @property
    def gating_active(self) -> bool:
        """True if normal/single mode is gating live display."""
        return self.cfg.enabled and self.cfg.run_mode is not TriggerRunMode.FREE_RUN
