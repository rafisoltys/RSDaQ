"""Tests for the per-channel display configuration."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from rsdaq.display import ChannelDisplay, DisplayStore, VizStyle


def test_default_is_identity_volts():
    d = ChannelDisplay()
    assert d.viz_style is VizStyle.GRAPH
    assert d.use_eu is False
    assert d.display_unit == "V"
    np.testing.assert_array_equal(
        d.to_display(np.array([0.0, 1.0, 2.5, 5.0])),
        np.array([0.0, 1.0, 2.5, 5.0]),
    )


def test_eu_mapping_linear():
    # 0-5 V -> 0-6 bar
    d = ChannelDisplay(use_eu=True, unit="bar",
                       raw_min_v=0.0, raw_max_v=5.0,
                       eu_min=0.0, eu_max=6.0)
    np.testing.assert_allclose(
        d.to_display(np.array([0.0, 2.5, 5.0])),
        np.array([0.0, 3.0, 6.0]),
    )
    assert d.scalar_to_display(0.0) == 0.0
    assert d.scalar_to_display(2.5) == 3.0
    assert d.scalar_to_display(5.0) == 6.0
    assert d.display_unit == "bar"


def test_eu_mapping_inverted_range():
    # 0-5 V -> 100-0 deg C (inverted thermistor for example)
    d = ChannelDisplay(use_eu=True, unit="degC",
                       raw_min_v=0.0, raw_max_v=5.0,
                       eu_min=100.0, eu_max=0.0)
    np.testing.assert_allclose(
        d.to_display(np.array([0.0, 2.5, 5.0])),
        np.array([100.0, 50.0, 0.0]),
    )


def test_eu_mapping_zero_range_returns_min_safely():
    d = ChannelDisplay(use_eu=True, raw_min_v=1.0, raw_max_v=1.0,
                       eu_min=42.0, eu_max=99.0)
    out = d.to_display(np.array([0.0, 1.0, 2.0]))
    np.testing.assert_array_equal(out, np.array([42.0, 42.0, 42.0]))


def test_store_save_and_load_roundtrip(tmp_path: Path):
    p = tmp_path / "display.json"
    s = DisplayStore(path=p)
    s.set(0, 3, ChannelDisplay(
        viz_style=VizStyle.GAUGE, use_eu=True, unit="bar",
        raw_min_v=0.0, raw_max_v=5.0, eu_min=0.0, eu_max=6.0,
        label="Pressure",
    ))
    s.set(1, 0, ChannelDisplay(viz_style=VizStyle.BAR))  # default values otherwise
    s.save()
    raw = json.loads(p.read_text())
    assert raw["version"] == 1
    assert any(e["address"] == 0 and e["channel"] == 3 and e["unit"] == "bar"
               for e in raw["channels"])

    s2 = DisplayStore.load(p)
    d = s2.get(0, 3)
    assert d.viz_style is VizStyle.GAUGE
    assert d.unit == "bar"
    assert d.eu_max == 6.0
    assert d.label == "Pressure"
    # Default-valued entry round-trips too
    d2 = s2.get(1, 0)
    assert d2.viz_style is VizStyle.BAR


def test_default_entry_pruned_on_set():
    s = DisplayStore(path=Path("/tmp/_unused.json"))
    s.set(0, 0, ChannelDisplay())  # all defaults
    assert (0, 0) not in s.entries
    # Non-default style should be kept.
    s.set(0, 0, ChannelDisplay(viz_style=VizStyle.BAR))
    assert (0, 0) in s.entries
    # Setting back to default removes it.
    s.set(0, 0, ChannelDisplay())
    assert (0, 0) not in s.entries
