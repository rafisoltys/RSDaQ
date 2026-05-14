"""Per-channel live statistics table."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from rsdaq.core.stats import StatsTracker
from .plot_panel import CHANNEL_COLORS


class StatsPanel(QTableWidget):
    HEADERS = ["Ch", "Last", "Min", "Max", "Mean", "RMS", "Samples"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(self.NoSelection)
        self.setEditTriggers(self.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.HEADERS.index("Samples"), QHeaderView.ResizeToContents)
        self._channels: List[int] = []
        self._stats: Optional[StatsTracker] = None

    def configure(self, channels: List[int], stats: StatsTracker) -> None:
        self._channels = list(channels)
        self._stats = stats
        self.setRowCount(len(channels))
        for row, ch in enumerate(channels):
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            name_item = QTableWidgetItem(f"CH {ch}")
            name_item.setForeground(color)
            name_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 0, name_item)
            for col in range(1, len(self.HEADERS)):
                it = QTableWidgetItem("--")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.setItem(row, col, it)

    def refresh(self) -> None:
        if self._stats is None:
            return
        for row, s in enumerate(self._stats.stats):
            if s.count == 0:
                continue
            self.item(row, 1).setText(f"{s.last:+.4f} V")
            self.item(row, 2).setText(f"{s.minimum:+.4f} V")
            self.item(row, 3).setText(f"{s.maximum:+.4f} V")
            self.item(row, 4).setText(f"{s.mean:+.4f} V")
            self.item(row, 5).setText(f"{s.rms:.4f} V")
            self.item(row, 6).setText(f"{s.count:,}")
