import os

import pytest

from rsdaq.daq.boards import BoardKind, parse_simulated_topology, scan_boards


def test_parse_topology_basic():
    boards = parse_simulated_topology("0:118,1:134,3:152")
    assert [(b.address, b.kind) for b in boards] == [
        (0, BoardKind.MCC118),
        (1, BoardKind.MCC134),
        (3, BoardKind.MCC152),
    ]


def test_parse_topology_rejects_bad_address():
    with pytest.raises(ValueError):
        parse_simulated_topology("9:118")


def test_parse_topology_rejects_bad_kind():
    with pytest.raises(ValueError):
        parse_simulated_topology("0:foo")


def test_parse_topology_handles_full_names():
    boards = parse_simulated_topology("2:MCC134")
    assert boards[0].kind is BoardKind.MCC134


def test_scan_boards_with_simulate_arg():
    boards = scan_boards(simulate="0:118,4:152")
    assert [(b.address, b.kind) for b in boards] == [
        (0, BoardKind.MCC118),
        (4, BoardKind.MCC152),
    ]
    for b in boards:
        assert b.simulated is True


def test_scan_boards_empty_simulate():
    assert scan_boards(simulate="") == []


def test_scan_boards_default_returns_simulated_when_no_hw(monkeypatch):
    # When daqhats is unavailable, scan_boards() returns a default sim topology.
    monkeypatch.delenv("RSDAQ_SIMULATE", raising=False)
    boards = scan_boards()
    # In CI we don't have daqhats - we should get the default sim topology.
    if all(b.simulated for b in boards):
        assert {b.kind for b in boards} >= {BoardKind.MCC118}
