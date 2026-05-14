"""Real MCC152 (analog out + DIO) backend."""
from __future__ import annotations

import logging
from typing import Optional

from .backend import OutputBackend

log = logging.getLogger(__name__)

try:
    from daqhats import mcc152, DIOConfigItem  # type: ignore
    _HAS_DAQHATS = True
except Exception as _exc:  # pragma: no cover
    _HAS_DAQHATS = False
    _IMPORT_ERROR = _exc


class MCC152Backend(OutputBackend):
    name = "MCC152"

    def __init__(self):
        if not _HAS_DAQHATS:
            raise RuntimeError(f"daqhats not available: {_IMPORT_ERROR}")
        self._addr: Optional[int] = None
        self._hat = None

    def open(self, address: int) -> None:
        self._addr = int(address)
        self._hat = mcc152(self._addr)
        self._hat.dio_reset()
        self._hat.a_out_write_all([0.0, 0.0])

    def close(self) -> None:
        self._hat = None
        self._addr = None

    # ---------- AO ----------
    def set_ao(self, channel: int, voltage: float) -> None:
        if self._hat is None:
            raise RuntimeError("MCC152 not open")
        self._hat.a_out_write(channel, float(voltage))

    def get_ao(self, channel: int) -> float:
        # MCC152 has no readback; the UI tracks the last commanded value.
        return 0.0

    # ---------- DIO ----------
    def set_dio_direction(self, bit: int, output: bool) -> None:
        if self._hat is None:
            raise RuntimeError("MCC152 not open")
        # daqhats: DIRECTION value 0 = output, 1 = input.
        self._hat.dio_config_write_bit(bit, DIOConfigItem.DIRECTION, 0 if output else 1)

    def get_dio_direction(self, bit: int) -> bool:
        if self._hat is None:
            return False
        return self._hat.dio_config_read_bit(bit, DIOConfigItem.DIRECTION) == 0

    def set_dio(self, bit: int, value: bool) -> None:
        if self._hat is None:
            raise RuntimeError("MCC152 not open")
        self._hat.dio_output_write_bit(bit, 1 if value else 0)

    def get_dio(self, bit: int) -> bool:
        if self._hat is None:
            return False
        return bool(self._hat.dio_input_read_bit(bit))
