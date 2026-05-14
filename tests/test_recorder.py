import csv
import os

import numpy as np

from rsdaq.io.recorder import CSVRecorder, HDF5Recorder, Recorder


def test_csv_recorder_roundtrip(tmp_path):
    path = tmp_path / "out.csv"
    rec = CSVRecorder(str(path), labels=["B0:CH0", "B0:CH1"], sample_rate_hz=100.0)
    rec.open()
    rec.write(np.array([[1.0, 10.0], [2.0, 20.0]]))
    rec.write(np.array([[3.0, 30.0]]))
    rec.close()

    with open(path) as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert rows[0] == ["sample", "time_s", "B0:CH0_V", "B0:CH1_V"]
    assert len(rows) == 4
    # First time stamp should be 0.0, third should be 2/100=0.02
    assert float(rows[1][1]) == 0.0
    assert float(rows[3][1]) == 0.02


def test_for_path_picks_recorder_by_extension(tmp_path):
    csv_rec = Recorder.for_path(str(tmp_path / "x.csv"), ["a"], 1.0)
    assert isinstance(csv_rec, CSVRecorder)
    h5_rec = Recorder.for_path(str(tmp_path / "x.h5"), ["a"], 1.0)
    assert isinstance(h5_rec, HDF5Recorder)


def test_h5_recorder_roundtrip(tmp_path):
    h5py = __import__("h5py")
    path = tmp_path / "out.h5"
    rec = HDF5Recorder(str(path), labels=["B0:CH0", "B1:CH3"], sample_rate_hz=200.0)
    rec.open()
    rec.write(np.array([[1.0, -1.0], [2.0, -2.0]]))
    rec.write(np.array([[3.0, -3.0]]))
    rec.close()
    with h5py.File(path, "r") as f:
        assert f.attrs["sample_rate_hz"] == 200.0
        np.testing.assert_array_equal(f["B0_CH0"][:], [1.0, 2.0, 3.0])
        np.testing.assert_array_equal(f["B1_CH3"][:], [-1.0, -2.0, -3.0])
        unit = f["B0_CH0"].attrs["unit"]
        if isinstance(unit, bytes):
            unit = unit.decode()
        assert unit == "V"
