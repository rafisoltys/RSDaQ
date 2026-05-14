"""Modal dialog: edit per-channel gain/offset for every detected MCC118."""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from rsdaq.calibration import CalibrationStore, ChannelCal
from rsdaq.config import NUM_CHANNELS_118
from rsdaq.daq.boards import BoardInfo, BoardKind


class CalibrationDialog(QDialog):
    HEADERS = ["Board", "Channel", "Gain", "Offset (V)", "Label"]

    def __init__(self, store: CalibrationStore, mcc118_boards: List[BoardInfo],
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Channel calibration  -  V_corrected = gain * V_raw + offset")
        self.resize(640, 500)
        self._store = store
        self._boards = [b for b in mcc118_boards if b.kind is BoardKind.MCC118]
        self._build()
        self._load_into_table()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        info = QLabel(
            "Calibration follows the physical board (by address). "
            "It is applied <b>during acquisition</b> when the "
            "<i>Apply calibration</i> option is enabled."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        n_rows = len(self._boards) * NUM_CHANNELS_118
        self.table = QTableWidget(n_rows, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)

        # Build editor widgets per row
        self._editors = []
        row = 0
        for board in self._boards:
            for ch in range(NUM_CHANNELS_118):
                self.table.setItem(row, 0, _ro(f"#{board.address}"))
                self.table.setItem(row, 1, _ro(f"CH{ch}"))
                gain = QDoubleSpinBox()
                gain.setDecimals(6); gain.setRange(-1000.0, 1000.0); gain.setSingleStep(0.001)
                offset = QDoubleSpinBox()
                offset.setDecimals(6); offset.setRange(-1000.0, 1000.0); offset.setSingleStep(0.001)
                offset.setSuffix(" V")
                label = QLineEdit()
                self.table.setCellWidget(row, 2, gain)
                self.table.setCellWidget(row, 3, offset)
                self.table.setCellWidget(row, 4, label)
                self._editors.append((board.address, ch, gain, offset, label))
                row += 1

        btn_row = QHBoxLayout()
        self.reset_btn = QPushButton("Reset all to identity")
        self.reset_btn.clicked.connect(self._on_reset_all)
        btn_row.addWidget(self.reset_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        bb = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Save")
        bb.accepted.connect(self._on_save)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _load_into_table(self) -> None:
        for addr, ch, gain, offset, label in self._editors:
            cal = self._store.get(addr, ch)
            gain.setValue(cal.gain)
            offset.setValue(cal.offset)
            label.setText(cal.label)

    def _on_reset_all(self) -> None:
        for _addr, _ch, gain, offset, label in self._editors:
            gain.setValue(1.0)
            offset.setValue(0.0)
            label.clear()

    def _on_save(self) -> None:
        for addr, ch, gain, offset, label in self._editors:
            cal = ChannelCal(
                gain=float(gain.value()),
                offset=float(offset.value()),
                label=label.text().strip(),
            )
            self._store.set(addr, ch, cal)
        try:
            self._store.save()
        except OSError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Save failed", f"Could not save calibration:\n{exc}")
            return
        self.accept()


def _ro(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(Qt.AlignCenter)
    return it
