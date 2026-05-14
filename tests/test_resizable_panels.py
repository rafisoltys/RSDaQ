"""Tests for the user-resizable panels.

The user must be able to drag the dividers between:
  - the left control panel and the right tab area,
  - the line plot and the bar/gauge strip on the Acquire tab,
  - the plot and the stats table on the Acquire tab.

These tests also lock in that splitter sizes survive a save/restore cycle.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import pytest

qtwidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = qtwidgets.QApplication
QSplitter = qtwidgets.QSplitter

from rsdaq.core.ringbuffer import RingBuffer  # noqa: E402
from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle  # noqa: E402
from rsdaq.ui.main_window import MainWindow  # noqa: E402
from rsdaq.ui.plot_panel import PlotPanel  # noqa: E402


_app = None


@pytest.fixture(scope="module")
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


def test_main_window_uses_splitters(qapp):
    w = MainWindow(prefer_backend="simulator")
    assert isinstance(w.main_splitter, QSplitter)
    assert isinstance(w.acquire_splitter, QSplitter)
    # The control panel must be the left widget of the main splitter.
    assert w.main_splitter.widget(0) is w.control_panel
    assert w.main_splitter.widget(1) is w.tabs
    # Both splitters must allow dragging (handle width > 0).
    assert w.main_splitter.handleWidth() > 0
    assert w.acquire_splitter.handleWidth() > 0


def test_control_panel_has_no_fixed_width(qapp):
    """Regression: previously setFixedWidth(440) prevented dragging."""
    w = MainWindow(prefer_backend="simulator")
    cp = w.control_panel
    # Min/max define the drag range; fixed width would set them equal.
    assert cp.minimumWidth() < cp.maximumWidth(), (
        "control panel min/max must differ so the splitter can move it")


def test_main_splitter_is_draggable(qapp):
    """The splitter must accept setSizes() without artificial constraints."""
    w = MainWindow(prefer_backend="simulator")
    w.show()
    w.resize(1500, 860)
    qapp.processEvents()
    # The splitter accepts the request; on a real desktop platform this is
    # what a user mouse drag does. We verify the API isn't gated by a
    # fixed width or other constraint.
    w.main_splitter.setSizes([560, 800])
    qapp.processEvents()
    sizes = w.main_splitter.sizes()
    # Both sides got non-zero space.
    assert sizes[0] > 0 and sizes[1] > 0
    # Control panel size is within its declared range (the user can drag
    # within this range freely).
    assert w.control_panel.minimumWidth() <= sizes[0] <= w.control_panel.maximumWidth()


def test_main_splitter_respects_min_max_widths(qapp):
    w = MainWindow(prefer_backend="simulator")
    cp = w.control_panel
    # Try to make the control panel smaller than its min - clamped.
    w.main_splitter.setSizes([50, 1500])
    qapp.processEvents()
    assert w.main_splitter.sizes()[0] >= cp.minimumWidth()
    # Try to make it larger than its max - also clamped.
    w.main_splitter.setSizes([2000, 200])
    qapp.processEvents()
    assert w.main_splitter.sizes()[0] <= cp.maximumWidth()


def test_acquire_splitter_can_resize_stats(qapp):
    """Stats can be made larger than its old fixed cap (was 220 px max)."""
    w = MainWindow(prefer_backend="simulator")
    # The previous design used setMaximumHeight(220); a draggable splitter
    # must have no such cap so the user can grow the stats table.
    assert w.stats_panel.maximumHeight() > 1000  # effectively unlimited
    assert w.stats_panel.minimumHeight() < w.stats_panel.maximumHeight()
    # The splitter accepts size requests beyond the old cap.
    w.show()
    w.resize(1500, 860)
    qapp.processEvents()
    w.acquire_splitter.setSizes([200, 500])
    qapp.processEvents()
    sizes = w.acquire_splitter.sizes()
    # Both sides got non-zero space.
    assert sizes[0] > 0 and sizes[1] > 0


def test_plot_panel_has_internal_splitter(qapp):
    panel = PlotPanel()
    assert isinstance(panel._splitter, QSplitter)
    # Both children present even before configure(): plot + side scroll.
    assert panel._splitter.count() == 2


def test_plot_panel_splitter_is_draggable_when_both_visible(qapp):
    """When the user has graph + gauge mixed, both children are visible
    and the divider must be movable."""
    ds = DisplayStore()
    ds.set(0, 0, ChannelDisplay(viz_style=VizStyle.GAUGE))
    ds.set(0, 1, ChannelDisplay(viz_style=VizStyle.GRAPH))
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
    # User drags the divider to give the gauges more room.
    panel._splitter.setSizes([300, 600])
    qapp.processEvents()
    sizes = panel._splitter.sizes()
    assert sizes[1] > sizes[0], (
        "after dragging the divider, the side strip must take the larger "
        f"share; got plot={sizes[0]}, side={sizes[1]}")


def test_layout_persists_via_qsettings(qapp, tmp_path):
    """Closing the window should save splitter state; the next instance
    can restore it. We test the round-trip via the splitter's own
    saveState/restoreState which is what _save_layout uses internally."""
    w1 = MainWindow(prefer_backend="simulator")
    w1.show()
    w1.resize(1500, 860)
    qapp.processEvents()
    w1.main_splitter.setSizes([560, 940])
    w1.acquire_splitter.setSizes([400, 250])
    qapp.processEvents()
    main_state = w1.main_splitter.saveState()
    acq_state = w1.acquire_splitter.saveState()
    main_sizes_before = w1.main_splitter.sizes()
    acq_sizes_before = w1.acquire_splitter.sizes()

    # Build a fresh MainWindow and apply the saved state.
    w2 = MainWindow(prefer_backend="simulator")
    w2.show()
    w2.resize(1500, 860)
    qapp.processEvents()
    assert w2.main_splitter.restoreState(main_state)
    assert w2.acquire_splitter.restoreState(acq_state)
    qapp.processEvents()
    assert w2.main_splitter.sizes() == main_sizes_before
    assert w2.acquire_splitter.sizes() == acq_sizes_before
