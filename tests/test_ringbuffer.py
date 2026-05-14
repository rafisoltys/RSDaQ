import numpy as np
import pytest

from rsdaq.core.ringbuffer import RingBuffer


def test_basic_write_and_snapshot():
    rb = RingBuffer(capacity=4, n_channels=2)
    rb.write(np.array([[1.0, 10.0], [2.0, 20.0]]))
    data, total = rb.snapshot()
    assert total == 2
    np.testing.assert_array_equal(data, np.array([[1.0, 10.0], [2.0, 20.0]]))


def test_wraparound_preserves_chronological_order():
    rb = RingBuffer(capacity=4, n_channels=1)
    rb.write(np.arange(1, 4).reshape(-1, 1).astype(float))   # 1,2,3
    rb.write(np.arange(4, 8).reshape(-1, 1).astype(float))   # 4,5,6,7
    data, total = rb.snapshot()
    assert total == 7
    np.testing.assert_array_equal(data.ravel(), np.array([4, 5, 6, 7]))


def test_oversized_write_keeps_only_tail():
    rb = RingBuffer(capacity=3, n_channels=1)
    rb.write(np.arange(1, 11).reshape(-1, 1).astype(float))  # 1..10
    data, total = rb.snapshot()
    assert total == 10
    np.testing.assert_array_equal(data.ravel(), np.array([8, 9, 10]))


def test_shape_validation():
    rb = RingBuffer(capacity=4, n_channels=2)
    with pytest.raises(ValueError):
        rb.write(np.zeros((2, 3)))


def test_reset_clears():
    rb = RingBuffer(capacity=4, n_channels=1)
    rb.write(np.array([[1.0]]))
    rb.reset()
    data, total = rb.snapshot()
    assert total == 0
    assert data.shape[0] == 0
