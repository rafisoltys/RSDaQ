"""Real-time visualisation: scrolling graph + side strip with bar/gauge widgets.

Each (board, channel) is shown according to its ``ChannelDisplay.viz_style``:
    GRAPH -> a curve on the scrolling pyqtgraph plot
    BAR   -> a vertical bar widget on the right-side strip
    GAUGE -> a radial gauge widget on the right-side strip

Channel values can also be expressed in engineering units (e.g. bar) when the
display config has ``use_eu=True``. Units are surfaced everywhere - axis label,
legend, gauge/bar title - so the operator never has to wonder which channel
carries which unit.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from rsdaq.core.ringbuffer import RingBuffer
from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle
from .gauge_widget import BarWidget, GaugeWidget

# 8 high-contrast colours (one per channel index 0..7).
CHANNEL_COLORS = [
    "#5a8dee", "#ff7043", "#66bb6a", "#ab47bc",
    "#ffca28", "#26c6da", "#ec407a", "#9ccc65",
]


class PlotPanel(QWidget):
    """Top-level acquire-tab visualisation widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True, useOpenGL=False)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Left: scrolling line plot
        self._plot = pg.PlotWidget(background="#15171c")
        self._plot.setLabel("left", "Voltage", units="V",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.setLabel("bottom", "Time", units="s",
                           **{"color": "#c8cdd9", "font-size": "11pt"})
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.addLegend(offset=(10, 10), labelTextColor="#c8cdd9")
        self._plot.getAxis("left").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("bottom").setPen(pg.mkPen("#3a3f50"))
        self._plot.getAxis("left").setTextPen(pg.mkPen("#c8cdd9"))
        self._plot.getAxis("bottom").setTextPen(pg.mkPen("#c8cdd9"))
        outer.addWidget(self._plot, 4)

        # Right: scrolling strip of bar/gauge widgets (created on demand)
        self._side_scroll = QScrollArea()
        self._side_scroll.setWidgetResizable(True)
        self._side_scroll.setFrameShape(QFrame.NoFrame)
        self._side_host = QWidget()
        self._side_layout = QVBoxLayout(self._side_host)
        self._side_layout.setContentsMargins(4, 4, 4, 4)
        self._side_layout.setSpacing(8)
        self._side_layout.addStretch(1)
        self._side_scroll.setWidget(self._side_host)
        # Generous default width so a single gauge or bar reads well even when
        # the scrolling line plot is also visible.
        self._side_scroll.setMinimumWidth(220)
        self._side_scroll.hide()    # only shown if at least one bar/gauge channel exists

        # Track which "stretch" each child widget gets in the outer layout so
        # that when there are no graph channels the side strip takes the
        # whole width and the bar/gauge widgets render at full size.
        self._outer_layout = outer
        outer.addWidget(self._side_scroll, 1)

        # State
        self._curves: List[Optional[pg.PlotDataItem]] = []
        self._side_widgets: List[Optional[object]] = []  # BarWidget | GaugeWidget | None
        self._displays: List[ChannelDisplay] = []
        self._labels: List[str] = []
        self._channel_order: List[Tuple[int, int]] = []
        self._sample_rate: float = 1.0
        self._buffer: Optional[RingBuffer] = None
        self._trigger_line: Optional[pg.InfiniteLine] = None
        self._trigger_level: Optional[pg.InfiniteLine] = None

    # ------------------------------------------------------- public API
    def configure(
        self,
        channel_order: List[Tuple[int, int]],
        labels: List[str],
        sample_rate_hz: float,
        buffer: RingBuffer,
        display_store: Optional[DisplayStore] = None,
        trigger_level_v: Optional[float] = None,
    ) -> None:
        # ---------- reset graph ----------
        self._plot.clear()
        self._curves = [None] * len(labels)
        self._labels = list(labels)
        self._channel_order = list(channel_order)
        self._sample_rate = float(sample_rate_hz)
        self._buffer = buffer

        # Resolve display config per column
        if display_store is None:
            display_store = DisplayStore()
        self._displays = [
            display_store.get(addr, ch) for (addr, ch) in self._channel_order
        ]

        # ---------- clear side strip ----------
        # Remove all but the trailing stretch.
        while self._side_layout.count() > 1:
            item = self._side_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._side_widgets = [None] * len(labels)

        any_side = False
        any_graph = False
        graph_units: List[str] = []
        # Build one curve per GRAPH channel and one widget per BAR/GAUGE channel.
        for i, (lbl, disp) in enumerate(zip(self._labels, self._displays)):
            _addr, ch = self._channel_order[i]
            color = QColor(CHANNEL_COLORS[ch % len(CHANNEL_COLORS)])
            display_label = self._compose_label(lbl, disp)
            if disp.viz_style is VizStyle.GRAPH:
                pen = pg.mkPen(color, width=1.6)
                # Always include the unit in the legend so the user can read
                # mixed-unit graphs without going back to the dialog.
                legend_label = f"{display_label}  [{disp.display_unit}]"
                curve = self._plot.plot([], [], pen=pen, name=legend_label)
                self._curves[i] = curve
                graph_units.append(disp.display_unit)
                any_graph = True
            elif disp.viz_style is VizStyle.BAR:
                w = BarWidget()
                w.set_title(display_label)
                w.set_color(color)
                w.set_unit(disp.display_unit)
                w.set_range(disp.display_min, disp.display_max)
                self._side_widgets[i] = w
                self._side_layout.insertWidget(self._side_layout.count() - 1, w)
                any_side = True
            elif disp.viz_style is VizStyle.GAUGE:
                w = GaugeWidget()
                w.set_title(display_label)
                w.set_color(color)
                w.set_unit(disp.display_unit)
                w.set_range(disp.display_min, disp.display_max)
                self._side_widgets[i] = w
                self._side_layout.insertWidget(self._side_layout.count() - 1, w)
                any_side = True

        # Y-axis label: prefer a single-unit label; else say "(mixed)".
        unique_units = sorted(set(graph_units))
        if len(unique_units) == 1:
            self._plot.setLabel("left", "Value", units=unique_units[0],
                                **{"color": "#c8cdd9", "font-size": "11pt"})
        elif len(unique_units) == 0:
            # No graph channels - blank out the label, plot is hidden anyway.
            self._plot.setLabel("left", "", units="",
                                **{"color": "#c8cdd9", "font-size": "11pt"})
        else:
            self._plot.setLabel(
                "left", "Value (mixed: " + ", ".join(unique_units) + ")",
                units="",
                **{"color": "#c8cdd9", "font-size": "11pt"})

        # ---------- show / hide each side ----------
        # If there are no graph channels, hide the line plot completely so the
        # bar/gauge strip can use the full width of the page.
        self._plot.setVisible(any_graph)
        self._side_scroll.setVisible(any_side)
        # Adjust stretch factors so widgets get the space they deserve.
        if any_graph and any_side:
            self._outer_layout.setStretchFactor(self._plot, 4)
            self._outer_layout.setStretchFactor(self._side_scroll, 2)
            self._side_scroll.setMaximumWidth(420)
        elif any_side:
            self._outer_layout.setStretchFactor(self._side_scroll, 1)
            # Allow the side strip to grow as wide as the page.
            self._side_scroll.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
        elif any_graph:
            self._outer_layout.setStretchFactor(self._plot, 1)

        # Trigger marker housekeeping.
        self._trigger_line = None
        if trigger_level_v is not None and any_graph:
            self._trigger_level = pg.InfiniteLine(
                pos=trigger_level_v, angle=0,
                pen=pg.mkPen("#ff8a65", width=1, style=pg.QtCore.Qt.DashLine))
            self._plot.addItem(self._trigger_level)
        else:
            self._trigger_level = None

    # ------------------------------------------------------- helpers
    @staticmethod
    def _compose_label(label: str, disp: ChannelDisplay) -> str:
        if disp.label:
            return f"{label}  -  {disp.label}"
        return label

    # ------------------------------------------------------- public API
    def clear(self) -> None:
        for c in self._curves:
            if c is not None:
                c.setData([], [])
        for w in self._side_widgets:
            if w is not None:
                w.set_value(0.0)

    def mark_trigger(self, t_seconds: float) -> None:
        if self._trigger_line is not None:
            self._plot.removeItem(self._trigger_line)
        self._trigger_line = pg.InfiniteLine(
            pos=t_seconds, angle=90,
            pen=pg.mkPen("#ff8a65", width=1.5, style=pg.QtCore.Qt.DashLine))
        self._plot.addItem(self._trigger_line)

    def refresh(self) -> None:
        if self._buffer is None:
            return
        data, total = self._buffer.snapshot()
        n = data.shape[0]
        if n == 0:
            return
        t_end = total / self._sample_rate
        t_start = t_end - n / self._sample_rate
        x = np.linspace(t_start, t_end, n, endpoint=False)
        for i, disp in enumerate(self._displays):
            if i >= data.shape[1]:
                continue
            col = data[:, i]
            curve = self._curves[i]
            if curve is not None:
                # Apply EU mapping if requested.
                y = disp.to_display(col)
                curve.setData(x, y)
            side = self._side_widgets[i]
            if side is not None:
                last = float(disp.scalar_to_display(float(col[-1])))
                side.set_value(last)
