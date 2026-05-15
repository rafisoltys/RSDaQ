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

def _daqhats_available() -> bool:
    """Return True if the daqhats Python module can be imported."""
    try:
        import daqhats  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def create_scan_backend(
    addresses: Optional[List[int]] = None,
    prefer: str = "auto",
) -> ScanBackend:
    """Build an MCC118 (multi-board) scan backend.

    When ``prefer='auto'``:
        - If daqhats is importable, always try the real backend. If that fails
          (e.g. no boards detected), raise — never silently simulate on real
          hardware.
        - If daqhats is NOT importable (off-Pi dev machine), use the simulator.
    """
    if prefer == "simulator":
        from .simulator import SimulatorScanBackend
        return SimulatorScanBackend(addresses=addresses)

    if prefer in ("auto", "real", "mcc118"):
        if _daqhats_available() or prefer in ("real", "mcc118"):
            from .mcc118_backend import MCC118Backend
            return MCC118Backend(addresses=addresses)
        # daqhats not installed -> off-Pi; simulator is fine.
        log.info("daqhats not installed; using MCC118 simulator for development.")
        from .simulator import SimulatorScanBackend
        return SimulatorScanBackend(addresses=addresses)

    from .simulator import SimulatorScanBackend
    return SimulatorScanBackend(addresses=addresses)


def create_thermocouple_backend(prefer: str = "auto") -> ThermocoupleBackend:
    if prefer == "simulator":
        from .simulator import SimulatorTCBackend
        return SimulatorTCBackend()

    if prefer in ("auto", "real", "mcc134"):
        if _daqhats_available() or prefer in ("real", "mcc134"):
            from .mcc134_backend import MCC134Backend
            return MCC134Backend()
        log.info("daqhats not installed; using MCC134 simulator for development.")
        from .simulator import SimulatorTCBackend
        return SimulatorTCBackend()

    from .simulator import SimulatorTCBackend
    return SimulatorTCBackend()


def create_output_backend(prefer: str = "auto") -> OutputBackend:
    if prefer == "simulator":
        from .simulator import SimulatorOutputBackend
        return SimulatorOutputBackend()

    if prefer in ("auto", "real", "mcc152"):
        if _daqhats_available() or prefer in ("real", "mcc152"):
            from .mcc152_backend import MCC152Backend
            return MCC152Backend()
        log.info("daqhats not installed; using MCC152 simulator for development.")
        from .simulator import SimulatorOutputBackend
        return SimulatorOutputBackend()

    from .simulator import SimulatorOutputBackend
    return SimulatorOutputBackend()


def create_vibration_backend(
    addresses: Optional[List[int]] = None,
    prefer: str = "auto",
) -> ScanBackend:
    """Build an MCC172 (IEPE / vibration) backend."""
    if prefer == "simulator":
        from .simulator import SimulatorMcc172Backend
        return SimulatorMcc172Backend(addresses=addresses)

    if prefer in ("auto", "real", "mcc172"):
        if _daqhats_available() or prefer in ("real", "mcc172"):
            from .mcc172_backend import MCC172Backend
            return MCC172Backend(addresses=addresses)
        log.info("daqhats not installed; using MCC172 simulator for development.")
        from .simulator import SimulatorMcc172Backend
        return SimulatorMcc172Backend(addresses=addresses)

    from .simulator import SimulatorMcc172Backend
    return SimulatorMcc172Backend(addresses=addresses)


# Back-compat: original API was create_backend(prefer) for MCC118.
def create_backend(prefer: str = "auto") -> ScanBackend:
    p = "real" if prefer == "mcc118" else prefer
    return create_scan_backend(prefer=p)
