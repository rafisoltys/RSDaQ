"""Streaming recorders for CSV and HDF5."""
from __future__ import annotations

import csv
import os
from abc import ABC, abstractmethod
from typing import List

import numpy as np


class Recorder(ABC):
    """Base streaming recorder. Subclasses append samples without buffering all of them."""

    def __init__(self, path: str, channels: List[int], sample_rate_hz: float):
        self.path = path
        self.channels = list(channels)
        self.sample_rate_hz = float(sample_rate_hz)

    @abstractmethod
    def open(self) -> None: ...

    @abstractmethod
    def write(self, samples: np.ndarray) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @staticmethod
    def for_path(path: str, channels: List[int], sample_rate_hz: float) -> "Recorder":
        ext = os.path.splitext(path)[1].lower()
        if ext in (".h5", ".hdf5"):
            return HDF5Recorder(path, channels, sample_rate_hz)
        # Default to CSV otherwise.
        if not ext:
            path = path + ".csv"
        return CSVRecorder(path, channels, sample_rate_hz)


class CSVRecorder(Recorder):
    def __init__(self, path: str, channels, sample_rate_hz: float):
        super().__init__(path, channels, sample_rate_hz)
        self._fh = None
        self._writer = None
        self._sample_index = 0

    def open(self) -> None:
        self._fh = open(self.path, "w", newline="")
        self._writer = csv.writer(self._fh)
        header = ["sample", "time_s"] + [f"CH{ch}_V" for ch in self.channels]
        self._writer.writerow(header)

    def write(self, samples: np.ndarray) -> None:
        if self._writer is None:
            return
        n = samples.shape[0]
        idx = np.arange(self._sample_index, self._sample_index + n)
        t = idx / self.sample_rate_hz
        rows = np.column_stack((idx, t, samples))
        # csv module is faster than np.savetxt for streaming small chunks.
        self._writer.writerows(rows.tolist())
        self._sample_index += n

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
            self._writer = None


class HDF5Recorder(Recorder):
    """Streaming HDF5 writer with one resizable dataset per channel."""

    CHUNK = 4096

    def __init__(self, path: str, channels, sample_rate_hz: float):
        super().__init__(path, channels, sample_rate_hz)
        self._h5 = None
        self._datasets = []
        self._sample_index = 0

    def open(self) -> None:
        import h5py  # local import; optional dep at runtime
        self._h5 = h5py.File(self.path, "w")
        self._h5.attrs["sample_rate_hz"] = self.sample_rate_hz
        self._h5.attrs["channels"] = np.asarray(self.channels, dtype=np.int32)
        self._datasets = []
        for ch in self.channels:
            ds = self._h5.create_dataset(
                f"CH{ch}", shape=(0,), maxshape=(None,),
                dtype="f8", chunks=(self.CHUNK,), compression="gzip",
                compression_opts=4)
            ds.attrs["unit"] = "V"
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
