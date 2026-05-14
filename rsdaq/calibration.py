"""Per-channel calibration: V_corrected = gain * V_raw + offset.

Stored in JSON at ``$RSDAQ_CONFIG_DIR/calibration.json`` (default
``~/.config/rsdaq/calibration.json``). The store is keyed by ``(address, channel)``
so calibration follows the physical board, not its position in any specific
acquisition.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class ChannelCal:
    gain: float = 1.0
    offset: float = 0.0
    label: str = ""

    def apply(self, raw: np.ndarray) -> np.ndarray:
        if self.gain == 1.0 and self.offset == 0.0:
            return raw
        return raw * self.gain + self.offset

    def is_identity(self) -> bool:
        return self.gain == 1.0 and self.offset == 0.0


def _default_path() -> Path:
    base = os.environ.get("RSDAQ_CONFIG_DIR")
    if base:
        return Path(base) / "calibration.json"
    return Path.home() / ".config" / "rsdaq" / "calibration.json"


@dataclass
class CalibrationStore:
    """Mapping ``(address, channel) -> ChannelCal`` with JSON persistence."""

    path: Path = field(default_factory=_default_path)
    entries: Dict[Tuple[int, int], ChannelCal] = field(default_factory=dict)

    # ----------------------------------------------------- IO
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "CalibrationStore":
        p = Path(path) if path is not None else _default_path()
        store = cls(path=p)
        if not p.exists():
            return store
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed reading calibration %s: %s", p, exc)
            return store
        for entry in data.get("channels", []):
            try:
                key = (int(entry["address"]), int(entry["channel"]))
                store.entries[key] = ChannelCal(
                    gain=float(entry.get("gain", 1.0)),
                    offset=float(entry.get("offset", 0.0)),
                    label=str(entry.get("label", "")),
                )
            except (KeyError, ValueError, TypeError):
                log.warning("Skipping malformed calibration entry: %r", entry)
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "channels": [
                {
                    "address": addr,
                    "channel": ch,
                    "gain": cal.gain,
                    "offset": cal.offset,
                    "label": cal.label,
                }
                for (addr, ch), cal in sorted(self.entries.items())
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --------------------------------------------------- access
    def get(self, address: int, channel: int) -> ChannelCal:
        return self.entries.get((address, channel), ChannelCal())

    def set(self, address: int, channel: int, cal: ChannelCal) -> None:
        if cal.is_identity() and not cal.label:
            self.entries.pop((address, channel), None)
        else:
            self.entries[(address, channel)] = cal

    def reset(self, address: int, channel: int) -> None:
        self.entries.pop((address, channel), None)

    def all_for_address(self, address: int) -> Dict[int, ChannelCal]:
        return {ch: cal for (a, ch), cal in self.entries.items() if a == address}

    # ----------------------------------------- bulk apply (worker)
    def apply_columns(
        self,
        samples: np.ndarray,
        order: Iterable[Tuple[int, int]],
    ) -> np.ndarray:
        """Apply calibration column-wise.

        ``samples`` shape ``(n, k)``, ``order`` lists ``(address, channel)`` for
        every column in left-to-right order. Returns a new array (or the same
        array if every column is identity).
        """
        order = list(order)
        if samples.size == 0:
            return samples
        cals = [self.get(a, c) for (a, c) in order]
        if all(c.is_identity() for c in cals):
            return samples
        out = samples.astype(np.float64, copy=True)
        for i, cal in enumerate(cals):
            if not cal.is_identity():
                out[:, i] = out[:, i] * cal.gain + cal.offset
        return out


__all__ = ["ChannelCal", "CalibrationStore"]
