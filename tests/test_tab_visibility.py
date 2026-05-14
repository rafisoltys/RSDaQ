"""Tests for tab visibility behaviour.

Locks in the fix for the regression where toggling a tab on caused Qt to
leave stale labels around and the tab text appeared to overlap a neighbour.
The fix uses ``QTabWidget.setTabVisible()`` instead of removing/adding tabs.
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import pytest

qtwidgets = pytest.importorskip("PySide6.QtWidgets")
QApplication = qtwidgets.QApplication

from rsdaq.ui.main_window import MainWindow  # noqa: E402


_app = None


@pytest.fixture(scope="module")
def qapp():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
    return _app


def _tab_count_visible(tabs) -> int:
    return sum(1 for i in range(tabs.count()) if tabs.isTabVisible(i))


def test_default_visibility_shows_every_tab(qapp):
    w = MainWindow(prefer_backend="simulator")
    # Default sim topology: MCC118+MCC134+MCC152+MCC172
    visible_titles = [
        w.tabs.tabText(i) for i in range(w.tabs.count())
        if w.tabs.isTabVisible(i)
    ]
    assert "Acquire" in visible_titles
    assert "Spectrum" in visible_titles
    assert "Trigger captures" in visible_titles
    assert "Thermocouples" in visible_titles
    assert "Outputs" in visible_titles
    assert "Vibration (MCC172)" in visible_titles


def test_tabs_are_never_removed_or_re_added(qapp):
    """Toggling a tab off then on must keep the same QWidget object, not a copy."""
    w = MainWindow(prefer_backend="simulator")
    spectrum_page = w.fft_panel
    initial_idx = w.tabs.indexOf(spectrum_page)
    assert initial_idx >= 0

    # Hide Spectrum
    w.control_panel.set_tab_visible("spectrum", False)
    qapp.processEvents()
    assert not w.tabs.isTabVisible(w.tabs.indexOf(spectrum_page))
    # The same widget is still in the tab bar at the same index.
    assert w.tabs.indexOf(spectrum_page) == initial_idx

    # Show Spectrum
    w.control_panel.set_tab_visible("spectrum", True)
    qapp.processEvents()
    assert w.tabs.isTabVisible(w.tabs.indexOf(spectrum_page))
    # Same object identity preserved.
    assert w.fft_panel is spectrum_page
    assert w.tabs.indexOf(spectrum_page) == initial_idx


def test_unique_titles_after_toggling(qapp):
    """Symptom of the old bug: after toggle, two tabs might end up with
    overlapping text. Each visible tab title must be unique."""
    w = MainWindow(prefer_backend="simulator")

    # Toggle every tab off then on a few times.
    for key in ("acquire", "spectrum", "captures",
                "thermocouples", "outputs", "vibration"):
        w.control_panel.set_tab_visible(key, False)
        qapp.processEvents()
        w.control_panel.set_tab_visible(key, True)
        qapp.processEvents()

    titles = [
        w.tabs.tabText(i) for i in range(w.tabs.count())
        if w.tabs.isTabVisible(i)
    ]
    assert len(titles) == len(set(titles)), \
        f"duplicate tab titles after toggling: {titles}"


def test_unavailable_function_tabs_grey_out(qapp):
    """When a board kind isn't present, its checkbox must be disabled
    (and stays so until a rescan with that board)."""
    w = MainWindow(prefer_backend="simulator")
    # All four kinds are simulated by default, so checkboxes should be enabled.
    assert w.control_panel._tab_checks["thermocouples"].isEnabled()
    assert w.control_panel._tab_checks["outputs"].isEnabled()
    assert w.control_panel._tab_checks["vibration"].isEnabled()


def test_function_tabs_remain_after_re_scan(qapp):
    """After a board re-scan we must still have exactly one tab per available kind."""
    w = MainWindow(prefer_backend="simulator")
    w._do_scan_boards()
    qapp.processEvents()
    titles = [w.tabs.tabText(i) for i in range(w.tabs.count())]
    # No duplicate "Thermocouples" or "Outputs" or "Vibration" entries.
    assert titles.count("Thermocouples") == 1
    assert titles.count("Outputs") == 1
    assert titles.count("Vibration (MCC172)") == 1
