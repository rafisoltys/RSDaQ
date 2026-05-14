"""Integration tests for PlotPanel (Qt-headless).

These would have caught two regressions:
- when all channels are GAUGE/BAR the line plot still hogged 4/5 of the width
  and the user's bar/gauge widgets looked tiny ("covered by graph");
- the legend / y-axis didn't surface the engineering unit when the user had
  configured an EU mapping.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import numpy as np
import pytest

# Skip the whole module if Qt won't import (e.g. CI without libGL).
qtwidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = qtwidgets.QApplication

from rsdaq.core.ringbuffer import RingBuffer  # noqa: E402
from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle  # noqa: E402
from rsdaq.ui.gauge_widget import BarWidget, GaugeWidget  # noqa: E402
from rsdaq.ui.plot_panel import PlotPanel  # noqa: E402


_app = None


@pytest.fixture(scope="module")
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


def _ds_with(*entries):
    """Helper to build a DisplayStore with given (addr, ch, ChannelDisplay) triples."""
    s = DisplayStore()
    for addr, ch, d in entries:
        s.set(addr, ch, d)
    return s


def test_all_graph_channels_hide_side_strip(qapp):
    panel = PlotPanel()
    rb = RingBuffer(1024, 2)
    panel.configure(
        channel_order=[(0, 0), (0, 1)],
        labels=["B0:CH0", "B0:CH1"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=DisplayStore(),  # all defaults -> GRAPH
    )
    assert panel._plot.isVisible() or not panel.isVisible()  # always visible
    assert panel._plot.isVisibleTo(panel)
    # No bar/gauge widgets configured
    assert all(w is None for w in panel._side_widgets)
    # Side strip must be hidden when no bar/gauge channel is in use.
    assert not panel._side_scroll.isVisibleTo(panel)


def test_all_gauge_channels_hide_line_plot(qapp):
    """If every channel is gauge/bar, the line plot must NOT be visible -
    otherwise it covers the side strip and dwarfs the gauges."""
    ds = _ds_with(
        (0, 0, ChannelDisplay(viz_style=VizStyle.GAUGE)),
        (0, 1, ChannelDisplay(viz_style=VizStyle.BAR)),
    )
    panel = PlotPanel()
    rb = RingBuffer(1024, 2)
    panel.configure(
        channel_order=[(0, 0), (0, 1)],
        labels=["B0:CH0", "B0:CH1"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=ds,
    )
    panel.show()
    panel.resize(900, 500)
    qapp.processEvents()

    # Line plot must be hidden when no GRAPH channel exists.
    assert not panel._plot.isVisibleTo(panel), \
        "line plot must be hidden when every channel is gauge/bar"
    assert panel._side_scroll.isVisibleTo(panel)
    # Both side widgets actually constructed.
    assert isinstance(panel._side_widgets[0], GaugeWidget)
    assert isinstance(panel._side_widgets[1], BarWidget)


def test_mixed_graph_and_gauge_keeps_both_visible(qapp):
    ds = _ds_with(
        (0, 0, ChannelDisplay(viz_style=VizStyle.GAUGE, use_eu=True, unit="bar",
                              raw_min_v=0, raw_max_v=5, eu_min=0, eu_max=6)),
        (0, 1, ChannelDisplay(viz_style=VizStyle.GRAPH)),
    )
    panel = PlotPanel()
    rb = RingBuffer(1024, 2)
    panel.configure(
        channel_order=[(0, 0), (0, 1)],
        labels=["B0:CH0", "B0:CH1"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=ds,
    )
    panel.show()
    panel.resize(900, 500)
    qapp.processEvents()

    assert panel._plot.isVisibleTo(panel)
    assert panel._side_scroll.isVisibleTo(panel)
    # Curve created only for the GRAPH channel.
    assert panel._curves[0] is None
    assert panel._curves[1] is not None
    assert isinstance(panel._side_widgets[0], GaugeWidget)


def test_eu_mapping_propagates_to_gauge_value(qapp):
    """A 0-5 V signal mapped to 0-6 bar must read 6 bar at 5 V on the gauge."""
    ds = _ds_with(
        (0, 0, ChannelDisplay(viz_style=VizStyle.GAUGE, use_eu=True, unit="bar",
                              raw_min_v=0, raw_max_v=5, eu_min=0, eu_max=6,
                              label="Pressure")),
    )
    panel = PlotPanel()
    rb = RingBuffer(1024, 1)
    panel.configure(
        channel_order=[(0, 0)],
        labels=["B0:CH0"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=ds,
    )
    # Drive a constant 5 V signal.
    rb.write(np.full((10, 1), 5.0))
    panel.refresh()
    gauge = panel._side_widgets[0]
    assert isinstance(gauge, GaugeWidget)
    assert gauge.value() == pytest.approx(6.0)
    assert gauge._unit == "bar"
    assert gauge._minimum == 0.0 and gauge._maximum == 6.0


def test_legend_label_includes_unit(qapp):
    """Legend should show the unit so a glance at the plot reveals it."""
    ds = _ds_with(
        (0, 0, ChannelDisplay(viz_style=VizStyle.GRAPH, use_eu=True, unit="bar",
                              raw_min_v=0, raw_max_v=5, eu_min=0, eu_max=6,
                              label="Pressure")),
    )
    panel = PlotPanel()
    rb = RingBuffer(1024, 1)
    panel.configure(
        channel_order=[(0, 0)],
        labels=["B0:CH0"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=ds,
    )
    # Walk the plot's items to find the curve and read its legend name.
    curve = panel._curves[0]
    assert curve is not None
    name = curve.name() if hasattr(curve, "name") else getattr(curve, "_legendName", None)
    assert name is not None
    assert "bar" in name, f"legend label should include unit, got: {name!r}"
    assert "Pressure" in name


def test_yaxis_label_uses_eu_when_all_graph_channels_share_unit(qapp):
    ds = _ds_with(
        (0, 0, ChannelDisplay(viz_style=VizStyle.GRAPH, use_eu=True, unit="bar",
                              raw_min_v=0, raw_max_v=5, eu_min=0, eu_max=6)),
        (0, 1, ChannelDisplay(viz_style=VizStyle.GRAPH, use_eu=True, unit="bar",
                              raw_min_v=0, raw_max_v=5, eu_min=0, eu_max=6)),
    )
    panel = PlotPanel()
    rb = RingBuffer(1024, 2)
    panel.configure(
        channel_order=[(0, 0), (0, 1)],
        labels=["B0:CH0", "B0:CH1"],
        sample_rate_hz=1000.0,
        buffer=rb,
        display_store=ds,
    )
    label = panel._plot.getAxis("left").labelString()
    assert "bar" in label, f"y-axis label should mention unit; got {label!r}"
