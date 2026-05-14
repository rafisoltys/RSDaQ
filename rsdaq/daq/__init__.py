"""DAQ backends: factory + board discovery.

Public surface:
    scan_boards() / parse_simulated_topology() / BoardKind / BoardInfo
    create_scan_backend(addresses, prefer)        - MCC118
    create_thermocouple_backend(prefer)           - MCC134
    create_output_backend(prefer)                 - MCC152
    create_backend(prefer)                        - back-compat MCC118 alias

``prefer`` is one of ``'auto' | 'real' | 'simulator'``. ``'auto'`` tries the
real implementation first and falls back to the simulator if daqhats isn't
available or no matching board is present.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from .backend import OutputBackend, ScanBackend, ThermocoupleBackend, DaqBackend  # noqa: F401
from .boards import BoardInfo, BoardKind, parse_simulated_topology, scan_boards  # noqa: F401

log = logging.getLogger(__name__)


# --------------------------------------------------------------- factories
def create_scan_backend(
    addresses: Optional[List[int]] = None,
    prefer: str = "auto",
) -> ScanBackend:
    """Build an MCC118 (multi-board) scan backend."""
    if prefer in ("auto", "real", "mcc118"):
        try:
            from .mcc118_backend import MCC118Backend
            return MCC118Backend(addresses=addresses)
        except Exception as exc:
            if prefer in ("real", "mcc118"):
                raise
            log.warning("MCC118 backend unavailable (%s); using simulator.", exc)
    from .simulator import SimulatorScanBackend
    return SimulatorScanBackend(addresses=addresses)


def create_thermocouple_backend(prefer: str = "auto") -> ThermocoupleBackend:
    if prefer in ("auto", "real", "mcc134"):
        try:
            from .mcc134_backend import MCC134Backend
            return MCC134Backend()
        except Exception as exc:
            if prefer in ("real", "mcc134"):
                raise
            log.warning("MCC134 backend unavailable (%s); using simulator.", exc)
    from .simulator import SimulatorTCBackend
    return SimulatorTCBackend()


def create_output_backend(prefer: str = "auto") -> OutputBackend:
    if prefer in ("auto", "real", "mcc152"):
        try:
            from .mcc152_backend import MCC152Backend
            return MCC152Backend()
        except Exception as exc:
            if prefer in ("real", "mcc152"):
                raise
            log.warning("MCC152 backend unavailable (%s); using simulator.", exc)
    from .simulator import SimulatorOutputBackend
    return SimulatorOutputBackend()


def create_vibration_backend(
    addresses: Optional[List[int]] = None,
    prefer: str = "auto",
) -> ScanBackend:
    """Build an MCC172 (IEPE / vibration) backend."""
    if prefer in ("auto", "real", "mcc172"):
        try:
            from .mcc172_backend import MCC172Backend
            return MCC172Backend(addresses=addresses)
        except Exception as exc:
            if prefer in ("real", "mcc172"):
                raise
            log.warning("MCC172 backend unavailable (%s); using simulator.", exc)
    from .simulator import SimulatorMcc172Backend
    return SimulatorMcc172Backend(addresses=addresses)


# Back-compat: original API was create_backend(prefer) for MCC118.
def create_backend(prefer: str = "auto") -> ScanBackend:
    p = "real" if prefer == "mcc118" else prefer
    return create_scan_backend(prefer=p)
