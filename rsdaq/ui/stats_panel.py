"""Per-channel live statistics table.

Values are reported in each channel's chosen unit: raw volts by default, or
engineering units (e.g. bar) when the channel has ``use_eu=True`` in the
display config.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget,
)

from rsdaq.core.stats import StatsTracker
from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle
from .plot_panel import CHANNEL_COLORS


class StatsPanel(QTableWidget):
    HEADERS = ["Channel", "Style", "Unit", "Last", "Min", "Max", "Mean", "RMS", "Samples"]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(0, len(self.HEADERS), parent)
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        h = self.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Stretch)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(self.HEADERS.index("Samples"), QHeaderView.ResizeToContents)
        self._channel_order: List[Tuple[int, int]] = []
        self._stats: Optional[StatsTracker] = None
        self._displays: List[ChannelDisplay] = []

    def configure(self, channel_order: List[Tuple[int, int]],
                  labels: List[str], stats: StatsTracker,
                  display_store: Optional[DisplayStore] = None) -> None:
        self._channel_order = list(channel_order)
        self._stats = stats
        if display_store is None:
            display_store = DisplayStore()
        self._displays = [
            display_store.get(addr, ch) for (addr, ch) in self._channel_order
        ]
        self.setRowCount(len(channel_order))
        for row, ((addr, ch), disp) in enumerate(zip(self._channel_order, self._displays)):
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            base = labels[row] if row < len(labels) else f"B{addr}:CH{ch}"
            text = f"{base}  -  {disp.label}" if disp.label else base
            name_item = QTableWidgetItem(text)
            name_item.setForeground(color)
            name_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 0, name_item)
            style_item = QTableWidgetItem(disp.viz_style.value)
            style_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 1, style_item)
            unit_item = QTableWidgetItem(disp.display_unit)
            unit_item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, 2, unit_item)
            for col in range(3, len(self.HEADERS)):
                it = QTableWidgetItem("--")
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.setItem(row, col, it)

    def refresh(self) -> None:
        if self._stats is None:
            return
        for row, s in enumerate(self._stats.stats):
            if s.count == 0:
                continue
            disp = self._displays[row] if row < len(self._displays) else ChannelDisplay()
            unit = disp.display_unit
            self.item(row, 3).setText(f"{disp.scalar_to_display(s.last):+.4f} {unit}")
            self.item(row, 4).setText(f"{disp.scalar_to_display(s.minimum):+.4f} {unit}")
            self.item(row, 5).setText(f"{disp.scalar_to_display(s.maximum):+.4f} {unit}")
            self.item(row, 6).setText(f"{disp.scalar_to_display(s.mean):+.4f} {unit}")
            # RMS in EU is meaningful only when the mapping has zero offset; we
            # still report the simple (gain-scaled) version so users have a
            # readable engineering-units value.
            self.item(row, 7).setText(f"{disp.scalar_to_display(s.rms):.4f} {unit}")
            self.item(row, 8).setText(f"{s.count:,}")
