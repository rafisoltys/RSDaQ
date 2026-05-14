"""Per-channel display configuration: visualisation style + engineering-unit mapping.

A user might wire CH0 of board 0 to a 0-5 V pressure transducer with 0-6 bar
range. This module captures that mapping (raw V -> EU) plus the user's choice
of visual style (line graph / vertical bar / radial gauge).

The mapping is purely cosmetic - calibration (gain/offset) still happens in
``rsdaq.calibration`` and is applied first by the worker. ``ChannelDisplay``
operates on the already-calibrated voltage that lands on the plot/stats.

Persisted as JSON at ``$RSDAQ_CONFIG_DIR/display.json`` (default
``~/.config/rsdaq/display.json``), keyed by ``(address, channel)``.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


class VizStyle(str, Enum):
    GRAPH = "Graph"
    BAR = "Vertical bar"
    GAUGE = "Gauge"


@dataclass
class ChannelDisplay:
    """How to visualise one (address, channel)."""
    viz_style: VizStyle = VizStyle.GRAPH
    use_eu: bool = False                # if False: raw V, ignore mapping below
    unit: str = "V"                     # engineering unit label, e.g. "bar"
    raw_min_v: float = 0.0              # raw V at eu_min
    raw_max_v: float = 5.0              # raw V at eu_max
    eu_min: float = 0.0
    eu_max: float = 5.0
    label: str = ""                     # optional human label, e.g. "Pressure"

    # ----- mapping -----
    def to_display(self, v: np.ndarray) -> np.ndarray:
        """Convert raw volts to whatever the user wants to *see*."""
        if not self.use_eu:
            return v
        rng = self.raw_max_v - self.raw_min_v
        if rng == 0:
            return np.full_like(v, self.eu_min, dtype=np.float64)
        return (v - self.raw_min_v) / rng * (self.eu_max - self.eu_min) + self.eu_min

    def scalar_to_display(self, v: float) -> float:
        if not self.use_eu:
            return float(v)
        rng = self.raw_max_v - self.raw_min_v
        if rng == 0:
            return self.eu_min
        return (float(v) - self.raw_min_v) / rng * (self.eu_max - self.eu_min) + self.eu_min

    # ----- helpers -----
    @property
    def display_unit(self) -> str:
        return self.unit if self.use_eu else "V"

    @property
    def display_min(self) -> float:
        return self.eu_min if self.use_eu else -10.0  # full MCC118 range default

    @property
    def display_max(self) -> float:
        return self.eu_max if self.use_eu else 10.0

    @property
    def is_default(self) -> bool:
        return (
            self.viz_style is VizStyle.GRAPH
            and not self.use_eu
            and not self.label
        )


def _default_path() -> Path:
    base = os.environ.get("RSDAQ_CONFIG_DIR")
    if base:
        return Path(base) / "display.json"
    return Path.home() / ".config" / "rsdaq" / "display.json"


@dataclass
class DisplayStore:
    """``(address, channel) -> ChannelDisplay`` with JSON persistence."""

    path: Path = field(default_factory=_default_path)
    entries: Dict[Tuple[int, int], ChannelDisplay] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "DisplayStore":
        p = Path(path) if path is not None else _default_path()
        store = cls(path=p)
        if not p.exists():
            return store
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed reading display config %s: %s", p, exc)
            return store
        for entry in data.get("channels", []):
            try:
                key = (int(entry["address"]), int(entry["channel"]))
                store.entries[key] = ChannelDisplay(
                    viz_style=VizStyle(entry.get("viz_style", VizStyle.GRAPH.value)),
                    use_eu=bool(entry.get("use_eu", False)),
                    unit=str(entry.get("unit", "V")),
                    raw_min_v=float(entry.get("raw_min_v", 0.0)),
                    raw_max_v=float(entry.get("raw_max_v", 5.0)),
                    eu_min=float(entry.get("eu_min", 0.0)),
                    eu_max=float(entry.get("eu_max", 5.0)),
                    label=str(entry.get("label", "")),
                )
            except (KeyError, ValueError, TypeError):
                log.warning("Skipping malformed display entry: %r", entry)
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "channels": [
                {
                    "address": addr,
                    "channel": ch,
                    "viz_style": d.viz_style.value,
                    "use_eu": d.use_eu,
                    "unit": d.unit,
                    "raw_min_v": d.raw_min_v,
                    "raw_max_v": d.raw_max_v,
                    "eu_min": d.eu_min,
                    "eu_max": d.eu_max,
                    "label": d.label,
                }
                for (addr, ch), d in sorted(self.entries.items())
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ----- access -----
    def get(self, address: int, channel: int) -> ChannelDisplay:
        return self.entries.get((address, channel), ChannelDisplay())

    def set(self, address: int, channel: int, d: ChannelDisplay) -> None:
        if d.is_default:
            self.entries.pop((address, channel), None)
        else:
            self.entries[(address, channel)] = d

    def reset(self, address: int, channel: int) -> None:
        self.entries.pop((address, channel), None)


__all__ = ["VizStyle", "ChannelDisplay", "DisplayStore"]
