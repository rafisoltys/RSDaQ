import pytest

from rsdaq.config import (
    AcquisitionConfig, BoardSelection, FFTConfig, MAX_AGGREGATE_RATE_HZ,
    ScanMode, SoftwareTriggerConfig, TriggerRunMode,
)


def test_basic_validate_ok():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 1, 2])],
        sample_rate_hz=1000.0,
    )
    cfg.validate()


def test_aggregate_rate_per_board():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 1])],
        sample_rate_hz=80_000.0,  # 2*80k = 160k > 100k -> reject
    )
    with pytest.raises(ValueError, match="exceeds MCC118"):
        cfg.validate()


def test_multi_board_aggregate_uses_max_per_board():
    """Two boards with 4 channels each: per-board rate is 4*20k=80k - OK."""
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 1, 2, 3]),
                BoardSelection(1, [0, 1])],
        sample_rate_hz=20_000.0,
    )
    cfg.validate()
    assert cfg.aggregate_rate_hz_per_board == 80_000


def test_duplicate_board_addresses_rejected():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0]), BoardSelection(0, [1])],
        sample_rate_hz=1000.0,
    )
    with pytest.raises(ValueError, match="Duplicate"):
        cfg.validate()


def test_channel_labels():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 2]), BoardSelection(3, [7])],
        sample_rate_hz=1000.0,
    )
    assert cfg.channel_labels() == ["B0:CH0", "B0:CH2", "B3:CH7"]


def test_sw_trigger_source_must_be_in_range():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0, 1])],
        sample_rate_hz=1000.0,
        software_trigger=SoftwareTriggerConfig(enabled=True, source=3,
                                              pre_samples=4, post_samples=4),
    )
    with pytest.raises(ValueError, match="trigger source"):
        cfg.validate()


def test_fft_size_must_be_power_of_two():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0])],
        sample_rate_hz=1000.0,
        fft=FFTConfig(size=1000),
    )
    with pytest.raises(ValueError, match="power of two"):
        cfg.validate()


def test_finite_mode_requires_positive_samples():
    cfg = AcquisitionConfig(
        boards=[BoardSelection(0, [0])],
        sample_rate_hz=1000.0,
        scan_mode=ScanMode.FINITE,
        samples_per_channel=0,
    )
    with pytest.raises(ValueError, match="positive in finite"):
        cfg.validate()


def test_back_compat_enabled_channels_setter():
    cfg = AcquisitionConfig()
    cfg.enabled_channels = [0, 3, 7]
    assert cfg.boards[0].address == 0
    assert cfg.boards[0].enabled_channels == [0, 3, 7]
