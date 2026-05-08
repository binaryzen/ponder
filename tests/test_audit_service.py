"""Tests for ponder.audit.service — the resource layer over Redis Stream."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ponder.audit.service import (
    _exclusive_min,
    _parse_entry,
    get_trace_events,
    list_events,
    list_traces,
    stream_info,
)


def _make_fields(trace_id="t1", span_id="s1", parent="", emitted="2026-05-07T12:00:00.000Z",
                 event_type="pipeline", region="thalamus", domain="default",
                 notation_version="1", payload=None):
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "emitted_at": emitted,
        "event_type": event_type,
        "region": region,
        "domain": domain,
        "notation_version": notation_version,
        "payload": json.dumps(payload or {}),
    }


def test_parse_entry_normalizes_empty_parent_to_none():
    parsed = _parse_entry("123-0", _make_fields(parent=""))
    assert parsed["parent_span_id"] is None


def test_parse_entry_preserves_parent_when_present():
    parsed = _parse_entry("123-0", _make_fields(parent="parent-x"))
    assert parsed["parent_span_id"] == "parent-x"


def test_parse_entry_decodes_payload_json():
    parsed = _parse_entry("1-0", _make_fields(payload={"boundary": "turn_start", "writes": ["a"]}))
    assert parsed["payload"] == {"boundary": "turn_start", "writes": ["a"]}


def test_parse_entry_includes_stream_id():
    parsed = _parse_entry("1715-0", _make_fields())
    assert parsed["stream_id"] == "1715-0"


def test_parse_entry_notation_version_int():
    parsed = _parse_entry("1-0", _make_fields(notation_version="3"))
    assert parsed["notation_version"] == 3


def test_exclusive_min_handles_initial_cursor():
    assert _exclusive_min("0") == "-"
    assert _exclusive_min("") == "-"
    assert _exclusive_min("-") == "-"


def test_exclusive_min_prepends_paren_for_real_cursor():
    assert _exclusive_min("1715-0") == "(1715-0"


def test_list_events_returns_paginated_result():
    mock_client = MagicMock()
    mock_client.xrange.side_effect = [
        # First call: the page itself
        [("1-0", _make_fields(trace_id="t1")), ("2-0", _make_fields(trace_id="t2"))],
        # Second call: the look-ahead for has_more (returns empty)
        [],
    ]

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = list_events(after="0", limit=2)

    assert len(result["events"]) == 2
    assert result["events"][0]["trace_id"] == "t1"
    assert result["next_cursor"] == "2-0"
    assert result["has_more"] is False


def test_list_events_has_more_when_lookahead_finds_entry():
    mock_client = MagicMock()
    mock_client.xrange.side_effect = [
        [("1-0", _make_fields()), ("2-0", _make_fields())],
        [("3-0", _make_fields())],  # look-ahead finds another → has_more
    ]

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = list_events(after="0", limit=2)

    assert result["has_more"] is True


def test_list_events_empty_stream():
    mock_client = MagicMock()
    mock_client.xrange.return_value = []

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = list_events()

    assert result["events"] == []
    assert result["has_more"] is False


def test_get_trace_events_filters_by_trace_id():
    mock_client = MagicMock()
    mock_client.xrange.return_value = [
        ("1-0", _make_fields(trace_id="alpha")),
        ("2-0", _make_fields(trace_id="beta")),
        ("3-0", _make_fields(trace_id="alpha")),
    ]

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = get_trace_events("alpha")

    assert len(result["events"]) == 2
    assert all(e["trace_id"] == "alpha" for e in result["events"])
    assert result["trace_id"] == "alpha"


def test_list_traces_aggregates_by_trace_id():
    mock_client = MagicMock()
    # XREVRANGE returns newest first
    mock_client.xrevrange.return_value = [
        ("3-0", _make_fields(trace_id="t1", region="broca", emitted="2026-05-07T12:00:03.000Z",
                             payload={"boundary": "turn_end"})),
        ("2-0", _make_fields(trace_id="t1", region="thalamus", emitted="2026-05-07T12:00:02.000Z")),
        ("1-0", _make_fields(trace_id="t1", region="orchestrator", emitted="2026-05-07T12:00:01.000Z",
                             payload={"boundary": "turn_start"})),
        ("0-1", _make_fields(trace_id="t2", region="thalamus", emitted="2026-05-07T11:00:00.000Z")),
    ]

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = list_traces()

    traces = result["traces"]
    assert len(traces) == 2
    # Newest trace first
    t1 = traces[0]
    assert t1["trace_id"] == "t1"
    assert t1["event_count"] == 3
    assert set(t1["regions"]) == {"broca", "thalamus", "orchestrator"}
    assert t1["status"] == "complete"
    assert t1["first_event_at"] == "2026-05-07T12:00:01.000Z"
    assert t1["last_event_at"] == "2026-05-07T12:00:03.000Z"

    t2 = traces[1]
    assert t2["status"] == "in_progress"


def test_list_traces_empty():
    mock_client = MagicMock()
    mock_client.xrevrange.return_value = []

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        result = list_traces()

    assert result == {"traces": []}


def test_stream_info_reachable():
    mock_client = MagicMock()
    mock_client.xlen.return_value = 7
    mock_client.xrange.return_value = [("1-0", {})]
    mock_client.xrevrange.return_value = [("9-0", {})]

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        info = stream_info()

    assert info["reachable"] is True
    assert info["length"] == 7
    assert info["first_stream_id"] == "1-0"
    assert info["last_stream_id"] == "9-0"


def test_stream_info_unreachable_does_not_raise():
    import redis as redis_module

    mock_client = MagicMock()
    mock_client.xlen.side_effect = redis_module.ConnectionError("nope")

    with patch("ponder.audit.service._get_client", return_value=mock_client):
        info = stream_info()

    assert info["reachable"] is False
    assert "error" in info
