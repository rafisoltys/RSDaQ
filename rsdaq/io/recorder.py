"""Streaming recorders for CSV and HDF5."""
from __future__ import annotations

import csv
import os
import re
from abc import ABC, abstractmethod
from typing import List, Sequence

import numpy as np


def _safe_dataset_name(label: str) -> str:
    """HDF5 dataset names may not contain '/'."""
    return re.sub(r"[^A-Za-z0-9_.\-]", "_", label)


class Recorder(ABC):
    """Base streaming recorder."""

    def __init__(self, path: str, labels: Sequence[str], sample_rate_hz: float):
        self.path = path
        self.labels = list(labels)
        self.sample_rate_hz = float(sample_rate_hz)

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def write(self, samples: np.ndarray) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @staticmethod
    def for_path(path: str, labels: Sequence[str], sample_rate_hz: float) -> "Recorder":
        ext = os.path.splitext(path)[1].lower()
        if ext in (".h5", ".hdf5"):
            return HDF5Recorder(path, labels, sample_rate_hz)
        if not ext:
            path = path + ".csv"
        return CSVRecorder(path, labels, sample_rate_hz)


class CSVRecorder(Recorder):
    def __init__(self, path: str, labels, sample_rate_hz: float):
        super().__init__(path, labels, sample_rate_hz)
        self._fh = None
        self._writer = None
        self._sample_index = 0

    def open(self) -> None:
        self._fh = open(self.path, "w", newline="")
        self._writer = csv.writer(self._fh)
        header = ["sample", "time_s"] + [f"{lbl}_V" for lbl in self.labels]
        self._writer.writerow(header)

    def write(self, samples: np.ndarray) -> None:
        if self._writer is None:
            return
        n = samples.shape[0]
        idx = np.arange(self._sample_index, self._sample_index + n)
        t = idx / self.sample_rate_hz
        rows = np.column_stack((idx, t, samples))
        self._writer.writerows(rows.tolist())
        self._sample_index += n

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None


class HDF5Recorder(Recorder):
    """Streaming HDF5: one resizable dataset per channel."""

    CHUNK = 4096

    def __init__(self, path: str, labels, sample_rate_hz: float):
        super().__init__(path, labels, sample_rate_hz)
        self._h5 = None
        self._datasets = []
        self._sample_index = 0

    def open(self) -> None:
        import h5py
        self._h5 = h5py.File(self.path, "w")
        self._h5.attrs["sample_rate_hz"] = self.sample_rate_hz
        self._h5.attrs["labels"] = np.asarray(self.labels, dtype="S64")
        self._datasets = []
        for lbl in self.labels:
            ds = self._h5.create_dataset(
                _safe_dataset_name(lbl),
                shape=(0,), maxshape=(None,),
                dtype="f8", chunks=(self.CHUNK,),
                compression="gzip", compression_opts=4)
            ds.attrs["unit"] = "V"
            ds.attrs["label"] = lbl
            self._datasets.append(ds)

    def write(self, samples: np.ndarray) -> None:
        if self._h5 is None:
            return
        n = samples.shape[0]
        for i, ds in enumerate(self._datasets):
            old = ds.shape[0]
            ds.resize((old + n,))
            ds[old:] = samples[:, i]
        self._sample_index += n

    def close(self) -> None:
        if self._h5 is not None:
            self._h5.close()
            self._h5 = None
            self._datasets = []
