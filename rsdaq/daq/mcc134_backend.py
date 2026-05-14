"""Real MCC134 (thermocouple) backend."""
from __future__ import annotations

import logging
from typing import List, Optional

from rsdaq.config import NUM_CHANNELS_134
from .backend import ThermocoupleBackend

log = logging.getLogger(__name__)

try:
    from daqhats import mcc134, TcTypes  # type: ignore
    _HAS_DAQHATS = True
except Exception as _exc:  # pragma: no cover
    _HAS_DAQHATS = False
    _IMPORT_ERROR = _exc


def _tc_enum(name: str):
    """Map our short string ('K', 'J', ...) to daqhats TcTypes enum."""
    name = name.upper()
    if not _HAS_DAQHATS:
        raise RuntimeError("daqhats not available")
    return {
        "DISABLED": TcTypes.DISABLED,
        "J": TcTypes.TYPE_J,
        "K": TcTypes.TYPE_K,
        "T": TcTypes.TYPE_T,
        "E": TcTypes.TYPE_E,
        "R": TcTypes.TYPE_R,
        "S": TcTypes.TYPE_S,
        "B": TcTypes.TYPE_B,
        "N": TcTypes.TYPE_N,
    }.get(name, TcTypes.DISABLED)


class MCC134Backend(ThermocoupleBackend):
    name = "MCC134"

    def __init__(self):
        if not _HAS_DAQHATS:
            raise RuntimeError(f"daqhats not available: {_IMPORT_ERROR}")
        self._addr: Optional[int] = None
        self._hat = None

    def open(self, address: int) -> None:
        self._addr = int(address)
        self._hat = mcc134(self._addr)

    def close(self) -> None:
        self._hat = None
        self._addr = None

    def set_tc_type(self, channel: int, tc_type: str) -> None:
        if self._hat is None:
            raise RuntimeError("MCC134 not open")
        self._hat.tc_type_write(channel, _tc_enum(tc_type))

    def read_temperatures(self) -> List[Optional[float]]:
        if self._hat is None:
            return [None] * NUM_CHANNELS_134
        out: List[Optional[float]] = []
        for ch in range(NUM_CHANNELS_134):
            try:
                v = self._hat.t_in_read(ch)
                # daqhats returns a sentinel for open/over/under-range conditions.
                if v is None or v != v or v <= -1000:  # NaN / sentinel
                    out.append(None)
                else:
                    out.append(float(v))
            except Exception:
                out.append(None)
        return out

    def read_cjc(self) -> List[Optional[float]]:
        if self._hat is None:
            return [None] * NUM_CHANNELS_134
        out: List[Optional[float]] = []
        for ch in range(NUM_CHANNELS_134):
            try:
                out.append(float(self._hat.cjc_read(ch)))
            except Exception:
                out.append(None)
        return out
