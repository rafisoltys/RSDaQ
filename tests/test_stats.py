import numpy as np

from rsdaq.core.stats import StatsTracker


def test_running_stats_match_numpy():
    rng = np.random.default_rng(42)
    data = rng.normal(0.5, 0.2, size=(1000, 3))
    st = StatsTracker(3)
    # feed in three chunks
    for chunk in (data[:300], data[300:700], data[700:]):
        st.update(chunk)
    for i in range(3):
        col = data[:, i]
        s = st.stats[i]
        assert s.count == 1000
        np.testing.assert_allclose(s.mean, col.mean(), atol=1e-10)
        np.testing.assert_allclose(s.minimum, col.min(), atol=1e-10)
        np.testing.assert_allclose(s.maximum, col.max(), atol=1e-10)
        np.testing.assert_allclose(s.rms, np.sqrt(np.mean(col ** 2)), atol=1e-10)
        np.testing.assert_allclose(s.last, col[-1])


def test_reset():
    st = StatsTracker(1)
    st.update(np.array([[1.0], [2.0], [3.0]]))
    st.reset()
    assert st.stats[0].count == 0
