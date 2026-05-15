"""Board discovery and registry.

Probes all 8 SPI addresses and returns a ``BoardInfo`` describing every
detected MCC HAT (MCC118, MCC134 or MCC152). Falls back to a configurable
simulated topology when ``daqhats`` is not importable.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

log = logging.getLogger(__name__)


class BoardKind(str, Enum):
    MCC118 = "MCC118"
    MCC134 = "MCC134"
    MCC152 = "MCC152"
    MCC172 = "MCC172"
    UNKNOWN = "Unknown"

    @property
    def description(self) -> str:
        return {
            BoardKind.MCC118: "Analog input (8 ch, 12-bit, ±10 V, 100 kS/s)",
            BoardKind.MCC134: "Thermocouple input (4 ch, 24-bit)",
            BoardKind.MCC152: "Analog output (2 ch) + DIO (8 ch)",
            BoardKind.MCC172: "IEPE/AC analog input (2 ch, 24-bit, ±5 V, 51.2 kS/s)",
            BoardKind.UNKNOWN: "Unknown / unsupported HAT",
        }[self]

    @property
    def category(self) -> str:
        """Functional category used by the UI."""
        return {
            BoardKind.MCC118: "scan",
            BoardKind.MCC134: "thermocouple",
            BoardKind.MCC152: "output",
            BoardKind.MCC172: "vibration",
            BoardKind.UNKNOWN: "unknown",
        }[self]


@dataclass
class BoardInfo:
    address: int
    kind: BoardKind
    serial: str = ""
    version: str = ""
    simulated: bool = False

    def label(self) -> str:
        tag = " (sim)" if self.simulated else ""
        return f"#{self.address}: {self.kind.value}{tag}"


# Lazy daqhats import — never fails at module load.
def _try_import_daqhats():
    try:
        import daqhats  # type: ignore
        return daqhats
    except Exception as exc:
        log.debug("daqhats not available: %s", exc)
        return None


def _hat_kind_from_id(hat_ids_module, raw_id) -> BoardKind:
    """Map a daqhats HatIDs enum value to our BoardKind.

    The ``raw_id`` can be an int or an enum member. We compare both by value
    and by identity to handle different daqhats versions and Python enum quirks.
    """
    # Build mapping from int value -> BoardKind.
    mapping = {}
    for attr, kind in (
        ("MCC_118", BoardKind.MCC118),
        ("MCC_134", BoardKind.MCC134),
        ("MCC_152", BoardKind.MCC152),
        ("MCC_172", BoardKind.MCC172),
    ):
        val = getattr(hat_ids_module, attr, None)
        if val is not None:
            # Store both the enum member itself and its int value as keys.
            mapping[val] = kind
            try:
                mapping[int(val)] = kind
            except (TypeError, ValueError):
                pass

    # Try direct lookup first (enum identity), then by int coercion.
    result = mapping.get(raw_id)
    if result is not None:
        return result
    try:
        result = mapping.get(int(raw_id))
    except (TypeError, ValueError):
        pass
    if result is not None:
        return result

    # Last resort: match by name substring in the repr (handles edge cases
    # where the daqhats version exposes a different enum structure).
    raw_str = str(raw_id).upper()
    for substr, kind in (("118", BoardKind.MCC118), ("134", BoardKind.MCC134),
                         ("152", BoardKind.MCC152), ("172", BoardKind.MCC172)):
        if substr in raw_str:
            return kind
    log.warning("Unknown HAT ID %r; reporting as UNKNOWN.", raw_id)
    return BoardKind.UNKNOWN


def parse_simulated_topology(spec: str) -> List[BoardInfo]:
    """Parse a topology string like '0:118,1:134,2:152'.

    Each entry is ``address:kind`` where kind is 118/134/152 (or full enum names).
    """
    out: List[BoardInfo] = []
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^\s*(\d+)\s*:\s*([A-Za-z0-9_]+)\s*$", part)
        if not m:
            raise ValueError(f"Bad topology entry: {part!r} (use ADDR:KIND)")
        addr = int(m.group(1))
        if not 0 <= addr <= 7:
            raise ValueError(f"Address {addr} out of range 0..7")
        raw_kind = m.group(2).upper().lstrip("M").lstrip("CC").strip("_")
        kind_map = {
            "118": BoardKind.MCC118,
            "MCC118": BoardKind.MCC118,
            "134": BoardKind.MCC134,
            "MCC134": BoardKind.MCC134,
            "152": BoardKind.MCC152,
            "MCC152": BoardKind.MCC152,
            "172": BoardKind.MCC172,
            "MCC172": BoardKind.MCC172,
        }
        kind = kind_map.get(raw_kind) or kind_map.get(m.group(2).upper())
        if kind is None:
            raise ValueError(f"Unknown board kind: {m.group(2)!r}")
        out.append(BoardInfo(address=addr, kind=kind, simulated=True))
    # Deduplicate addresses, keeping first occurrence.
    seen = set()
    deduped = []
    for b in out:
        if b.address in seen:
            log.warning("Duplicate address %d in topology; ignoring later entry.", b.address)
            continue
        seen.add(b.address)
        deduped.append(b)
    return deduped


def _default_simulated_topology() -> List[BoardInfo]:
    """Topology used when no override is given and daqhats is unavailable."""
    env = os.environ.get("RSDAQ_SIMULATE", "").strip()
    if env:
        try:
            return parse_simulated_topology(env)
        except ValueError as exc:
            log.warning("Bad RSDAQ_SIMULATE=%r (%s); using defaults.", env, exc)
    return [
        BoardInfo(address=0, kind=BoardKind.MCC118, simulated=True),
        BoardInfo(address=1, kind=BoardKind.MCC134, simulated=True),
        BoardInfo(address=2, kind=BoardKind.MCC152, simulated=True),
        BoardInfo(address=3, kind=BoardKind.MCC172, simulated=True),
    ]


def scan_boards(simulate: Optional[str] = None) -> List[BoardInfo]:
    """Discover every connected HAT.

    ``simulate``:
        - ``None`` — try real daqhats; if unavailable AND we're not on a Pi,
          fall back to simulator. If daqhats IS available but finds no boards,
          return an empty list (no auto-simulate on real hardware).
        - ``""`` — force *empty* (no boards).
        - non-empty string — parsed as a simulated topology spec.
    """
    if simulate is not None:
        return parse_simulated_topology(simulate)

    daqhats = _try_import_daqhats()
    if daqhats is None:
        # daqhats not installed — we're definitely not on a Pi with the HAT
        # library. Only then do we fall back to a simulated topology so
        # off-Pi development still works.
        return _default_simulated_topology()

    # daqhats IS available — we're on the Pi (or user has it installed).
    # Never auto-simulate; just report what the hardware scan finds.
    try:
        entries = daqhats.hat_list(filter_by_id=daqhats.HatIDs.ANY)
    except Exception as exc:
        log.error("hat_list() failed: %s. No boards will be available.", exc)
        return []

    boards: List[BoardInfo] = []
    for e in entries:
        kind = _hat_kind_from_id(daqhats.HatIDs, e.id)
        version = getattr(e, "version", "")
        boards.append(BoardInfo(
            address=int(e.address),
            kind=kind,
            serial="",
            version=str(version) if version else "",
            simulated=False,
        ))
    if not boards:
        log.warning(
            "daqhats is installed but hat_list() found 0 boards. "
            "Check that the HAT is seated correctly and /etc/mcc/hats is populated. "
            "Run 'daqhats_list_boards' from a terminal to diagnose.")
    return boards


__all__ = [
    "BoardKind", "BoardInfo", "scan_boards", "parse_simulated_topology",
]
