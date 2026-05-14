import numpy as np

from rsdaq.config import SoftwareTriggerConfig, TriggerRunMode, TriggerSlope
from rsdaq.core.trigger import SoftwareTrigger, TriggerState


def _ramp(n: int, start: float, end: float, n_channels: int = 1) -> np.ndarray:
    x = np.linspace(start, end, n)
    return np.column_stack([x] * n_channels)


def test_rising_crossing_detected_at_correct_index():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.NORMAL,
        source=0, level_v=0.0, slope=TriggerSlope.RISING,
        pre_samples=4, post_samples=8,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    # values: -3,-2,-1,0,1,2,3,4   -> crossing at index 3 (first >= 0 after <0)
    arr = np.linspace(-3, 4, 8).reshape(-1, 1)
    events = trig.feed(arr)
    # post_samples=8 needs more data first; feed extra
    events += trig.feed(np.linspace(5, 12, 8).reshape(-1, 1))
    assert len(events) == 1
    ev = events[0]
    assert ev.sample_index == 3
    assert ev.pre.shape[0] <= cfg.pre_samples
    assert ev.post.shape[0] == cfg.post_samples


def test_falling_crossing():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.NORMAL,
        source=0, level_v=0.5, slope=TriggerSlope.FALLING,
        pre_samples=2, post_samples=4,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    arr = np.array([[2.0], [1.0], [0.6], [0.5], [0.4], [0.0], [-1.0],
                    [-2.0], [-3.0]])
    events = trig.feed(arr)
    assert len(events) == 1
    # First falling crossing reaches <=0.5 at index 3 (value 0.5).
    assert events[0].sample_index == 3


def test_normal_rearms_after_each_event():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.NORMAL,
        source=0, level_v=0.0, slope=TriggerSlope.RISING,
        pre_samples=2, post_samples=2,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    # Make two distinct rising crossings: -1,1,-1,1,-1,1
    arr = np.array([-1, 1, -1, 1, -1, 1, -1, 1, 1, 1], dtype=float).reshape(-1, 1)
    events = trig.feed(arr)
    assert len(events) >= 2


def test_single_mode_disables_after_event():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.SINGLE,
        source=0, level_v=0.0, slope=TriggerSlope.RISING,
        pre_samples=2, post_samples=2,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    arr = np.array([-1, 1, -1, 1, -1, 1, 2, 3], dtype=float).reshape(-1, 1)
    events = trig.feed(arr)
    assert len(events) == 1
    assert trig.state is TriggerState.DONE


def test_free_run_emits_nothing():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.FREE_RUN,
        source=0, level_v=0.0,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    arr = np.array([-1, 1, -1, 1], dtype=float).reshape(-1, 1)
    assert trig.feed(arr) == []
    assert trig.state is TriggerState.DISABLED


def test_pre_window_size_capped():
    cfg = SoftwareTriggerConfig(
        enabled=True, run_mode=TriggerRunMode.NORMAL,
        source=0, level_v=0.0, slope=TriggerSlope.RISING,
        pre_samples=3, post_samples=2,
    )
    trig = SoftwareTrigger(cfg, n_channels=1)
    # Feed many samples below zero, then a crossing.
    arr = np.concatenate([
        np.full((20, 1), -1.0),
        np.array([[1.0]]),
        np.array([[2.0]]),
        np.array([[3.0]]),
    ])
    events = trig.feed(arr)
    assert len(events) == 1
    assert events[0].pre.shape[0] == 3  # capped, even though we sent many
