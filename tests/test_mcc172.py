import time

import numpy as np
import pytest

from rsdaq.config import (
    CouplingMode, IEPEChannelConfig, MAX_RATE_172_HZ, MIN_RATE_172_HZ,
    Mcc172AcquisitionConfig, Mcc172BoardSelection, ScanMode,
)
from rsdaq.daq import create_vibration_backend
from rsdaq.daq.boards import BoardKind, parse_simulated_topology
from rsdaq.daq.simulator import SimulatorMcc172Backend


def test_topology_parses_172():
    boards = parse_simulated_topology("4:172,5:MCC172")
    assert [b.kind for b in boards] == [BoardKind.MCC172, BoardKind.MCC172]
    assert [b.address for b in boards] == [4, 5]


def test_factory_falls_back_to_simulator():
    b = create_vibration_backend(addresses=[0], prefer="auto")
    assert isinstance(b, SimulatorMcc172Backend)


def test_mcc172_config_validate_rejects_bad_rate():
    cfg = Mcc172AcquisitionConfig(
        boards=[Mcc172BoardSelection(0, [0, 1])],
        sample_rate_hz=MAX_RATE_172_HZ + 1,
    )
    with pytest.raises(ValueError, match="out of"):
        cfg.validate()
    cfg.sample_rate_hz = MIN_RATE_172_HZ - 1
    with pytest.raises(ValueError, match="out of"):
        cfg.validate()


def test_mcc172_config_labels():
    cfg = Mcc172AcquisitionConfig(
        boards=[Mcc172BoardSelection(3, [0, 1])],
        sample_rate_hz=10_240,
    )
    cfg.validate()
    assert cfg.channel_labels() == ["M172#3:CH0", "M172#3:CH1"]
    assert cfg.total_channels == 2


def test_mcc172_simulator_produces_two_columns_with_iepe_bias():
    cfg = Mcc172AcquisitionConfig(
        boards=[Mcc172BoardSelection(
            0, [0, 1],
            channel_configs=[
                IEPEChannelConfig(iepe_enabled=True, coupling=CouplingMode.AC),
                IEPEChannelConfig(iepe_enabled=False, coupling=CouplingMode.DC),
            ])],
        sample_rate_hz=4096,
        scan_mode=ScanMode.CONTINUOUS,
    )
    sim = SimulatorMcc172Backend()
    sim.start(cfg)
    deadline = time.monotonic() + 0.5
    rows = 0
    last = None
    while time.monotonic() < deadline:
        r = sim.read(0.05)
        if r is not None:
            samples, total = r
            assert samples.shape[1] == 2
            rows = total
            last = samples
        if rows >= 200:
            break
    sim.stop()
    assert rows > 0
    # IEPE-on channel should sit higher than DC-coupled non-IEPE on average.
    if last is not None and last.shape[0] >= 50:
        means = last.mean(axis=0)
        assert means[0] > means[1] - 0.1   # bias makes ch0 mean larger


def test_mcc172_finite_mode_stops():
    cfg = Mcc172AcquisitionConfig(
        boards=[Mcc172BoardSelection(0, [0])],
        sample_rate_hz=8000,
        scan_mode=ScanMode.FINITE,
        samples_per_channel=300,
    )
    sim = SimulatorMcc172Backend()
    sim.start(cfg)
    deadline = time.monotonic() + 0.5
    total = 0
    while sim.is_running() and time.monotonic() < deadline:
        r = sim.read(0.05)
        if r is not None:
            total = r[1]
    sim.stop()
    assert total == 300
