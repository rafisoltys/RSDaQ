"""Modal dialog: scan SPI bus, show detected boards, allow user override."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from rsdaq.daq.boards import BoardInfo, BoardKind, scan_boards


class BoardsDialog(QDialog):
    """Show all 8 SPI addresses; let the user accept the detected layout
    or manually override the kind for any address (useful for testing)."""

    def __init__(self, current: Optional[List[BoardInfo]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detected boards")
        self.resize(560, 380)
        self._boards: List[BoardInfo] = list(current or [])
        self._build()
        self._populate(self._boards)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Scan probes all 8 SPI addresses on the Pi 5 stack header. "
            "If you swap HATs, click <b>Rescan</b>. You can also force a "
            "specific kind (useful before connecting hardware)."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.table = QTableWidget(8, 3)
        self.table.setHorizontalHeaderLabels(["Address", "Kind", "Description"])
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.clicked.connect(self._on_rescan)
        row.addWidget(self.rescan_btn)
        row.addStretch(1)
        self.summary_label = QLabel()
        self.summary_label.setProperty("role", "muted")
        row.addWidget(self.summary_label)
        layout.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _populate(self, boards: List[BoardInfo]) -> None:
        self._boards = list(boards)
        by_addr = {b.address: b for b in boards}
        for addr in range(8):
            self.table.setItem(addr, 0, _readonly(str(addr)))
            combo = QComboBox()
            for k in (BoardKind.UNKNOWN, BoardKind.MCC118, BoardKind.MCC134,
                      BoardKind.MCC152, BoardKind.MCC172):
                combo.addItem(k.value, k.name)   # store enum name (plain str, unambiguous)
            existing = by_addr.get(addr)
            kind = existing.kind if existing else BoardKind.UNKNOWN
            idx = combo.findData(kind.name)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.table.setCellWidget(addr, 1, combo)
            desc = _readonly(
                kind.description if kind is not BoardKind.UNKNOWN else "(no board)"
            )
            self.table.setItem(addr, 2, desc)
            combo.currentIndexChanged.connect(
                lambda _i, a=addr, c=combo: self._on_kind_changed(a, c))
        self._update_summary()

    def _on_kind_changed(self, addr: int, combo: QComboBox) -> None:
        kind = BoardKind[combo.currentData()]
        item = self.table.item(addr, 2)
        if item is not None:
            item.setText(kind.description if kind is not BoardKind.UNKNOWN else "(no board)")
        self._update_summary()

    def _on_rescan(self) -> None:
        self._populate(scan_boards())

    def _update_summary(self) -> None:
        boards = self.selected_boards()
        if not boards:
            self.summary_label.setText("No boards detected.")
        else:
            kinds = ", ".join(f"{b.kind.value}@{b.address}" for b in boards)
            self.summary_label.setText(f"{len(boards)} board(s): {kinds}")

    def selected_boards(self) -> List[BoardInfo]:
        out: List[BoardInfo] = []
        for addr in range(8):
            combo: QComboBox = self.table.cellWidget(addr, 1)  # type: ignore
            kind = BoardKind[combo.currentData()]
            if kind is BoardKind.UNKNOWN:
                continue
            existing_simulated = True
            existing_version = ""
            for b in self._boards:
                if b.address == addr:
                    existing_simulated = b.simulated
                    existing_version = b.version
                    break
            out.append(BoardInfo(address=addr, kind=kind,
                                 simulated=existing_simulated,
                                 version=existing_version))
        return out


def _readonly(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    return it
