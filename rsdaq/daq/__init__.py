"""DAQ backends.

Picks the real MCC118 backend if the daqhats library is importable on the host,
otherwise falls back to the simulator so the GUI is exercisable on any machine.
"""
from __future__ import annotations

import logging

from .backend import DaqBackend  # noqa: F401

log = logging.getLogger(__name__)


def create_backend(prefer: str = "auto") -> DaqBackend:
    """Factory for a DAQ backend.

    prefer: 'auto' | 'mcc118' | 'simulator'
    """
    if prefer in ("auto", "mcc118"):
        try:
            from .mcc118_backend import MCC118Backend
            return MCC118Backend()
        except Exception as exc:  # ImportError, board-not-found, etc.
            if prefer == "mcc118":
                raise
            log.warning("MCC118 backend unavailable (%s); falling back to simulator.", exc)

    from .simulator import SimulatorBackend
    return SimulatorBackend()
