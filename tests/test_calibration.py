import json
from pathlib import Path

import numpy as np

from rsdaq.calibration import CalibrationStore, ChannelCal


def test_apply_columns_identity_short_circuits():
    cs = CalibrationStore(path=Path("/tmp/_unused.json"))
    arr = np.array([[1.0, 2.0], [3.0, 4.0]])
    out = cs.apply_columns(arr, [(0, 0), (0, 1)])
    # Identity should return the same object reference (short-circuit)
    assert out is arr


def test_apply_columns_with_calibration():
    cs = CalibrationStore(path=Path("/tmp/_unused.json"))
    cs.set(0, 0, ChannelCal(gain=2.0, offset=1.0))
    cs.set(1, 3, ChannelCal(gain=10.0))
    arr = np.array([[1.0, 1.0, 1.0]])
    out = cs.apply_columns(arr, [(0, 0), (0, 1), (1, 3)])
    # col0: 1*2+1=3, col1: identity=1, col2: 1*10=10
    np.testing.assert_array_equal(out, [[3.0, 1.0, 10.0]])


def test_save_and_load_roundtrip(tmp_path):
    p = tmp_path / "cal.json"
    cs = CalibrationStore(path=p)
    cs.set(0, 5, ChannelCal(gain=1.5, offset=-0.25, label="probe A"))
    cs.set(2, 0, ChannelCal(gain=0.99))
    cs.save()
    raw = json.loads(p.read_text())
    assert raw["version"] == 1
    assert any(e["address"] == 0 and e["channel"] == 5 for e in raw["channels"])

    cs2 = CalibrationStore.load(p)
    cal = cs2.get(0, 5)
    assert cal.gain == 1.5
    assert cal.offset == -0.25
    assert cal.label == "probe A"


def test_identity_entries_are_pruned_on_set():
    cs = CalibrationStore(path=Path("/tmp/_unused.json"))
    cs.set(0, 0, ChannelCal(gain=2.0))
    assert (0, 0) in cs.entries
    cs.set(0, 0, ChannelCal())  # back to identity, no label
    assert (0, 0) not in cs.entries
