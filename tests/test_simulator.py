import time

import numpy as np

from rsdaq.config import AcquisitionConfig, BoardSelection, ScanMode
from rsdaq.daq.simulator import (
    SimulatorOutputBackend, SimulatorScanBackend, SimulatorTCBackend,
)


def test_scan_simulator_produces_correct_shape():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 1]), BoardSelection(2, [3])],
        sample_rate_hz=2000.0,
    )
    sim = SimulatorScanBackend()
    sim.start(cfg)
    last = None
    deadline = time.monotonic() + 0.5
    rows = 0
    while time.monotonic() < deadline:
        r = sim.read(0.05)
        if r is not None:
            samples, total = r
            assert samples.shape[1] == 3   # 2+1
            rows = total
            last = samples
        if rows >= 10:
            break
    sim.stop()
    assert rows > 0
    assert last is not None and last.dtype == np.float64


def test_finite_mode_stops_at_target():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0])],
        sample_rate_hz=5000.0,
        scan_mode=ScanMode.FINITE,
        samples_per_channel=200,
    )
    sim = SimulatorScanBackend()
    sim.start(cfg)
    total = 0
    deadline = time.monotonic() + 0.5
    while sim.is_running() and time.monotonic() < deadline:
        r = sim.read(0.05)
        if r is not None:
            total = r[1]
    sim.stop()
    assert total == 200


def test_tc_simulator_disabled_returns_none():
    tc = SimulatorTCBackend()
    tc.open(1)
    # Default: all DISABLED
    temps = tc.read_temperatures()
    assert temps == [None, None, None, None]
    tc.set_tc_type(0, "K")
    temps = tc.read_temperatures()
    assert temps[0] is not None and 0 < temps[0] < 100
    tc.close()


def test_output_simulator_ao_clamps_to_range():
    ob = SimulatorOutputBackend()
    ob.open(2)
    ob.set_ao(0, 10.0)
    assert ob.get_ao(0) == 5.0
    ob.set_ao(0, -1.0)
    assert ob.get_ao(0) == 0.0
    ob.close()


def test_output_simulator_dio_direction_gates_writes():
    ob = SimulatorOutputBackend()
    ob.open(2)
    # Bit 0 input (default, dir=False after setting input) -- write should be ignored
    ob.set_dio_direction(0, output=False)
    ob.set_dio(0, True)
    assert ob.get_dio(0) is False
    # Now switch to output and write
    ob.set_dio_direction(0, output=True)
    ob.set_dio(0, True)
    assert ob.get_dio(0) is True
    ob.close()
