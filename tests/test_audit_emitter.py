"""Tests for ponder.audit.emitter — verifies the Redis Stream wire format and resilience."""

import json
from unittest.mock import MagicMock, patch

import pytest
import redis

import ponder.audit.emitter as emitter_module
from ponder.audit.context import current_unit
from ponder.audit.emitter import emit, reset_client, stream_key
from ponder.audit.events import AuditEvent, EventType


@pytest.fixture(autouse=True)
def reset_audit_client():
    reset_client()
    yield
    reset_client()


def _sample_event() -> AuditEvent:
    return AuditEvent(
        trace_id="trace-x",
        span_id="span-y",
        parent_span_id="parent-z",
        emitted_at="2026-05-07T12:00:00.000Z",
        event_type=EventType.PIPELINE,
        region="thalamus",
        domain="default",
        notation_version=1,
        payload={"boundary": "region_complete", "duration_ms": 12.3, "writes": ["input_type"]},
    )


def test_stream_key_default_unit():
    assert stream_key() == "ponder:default:audit"


def test_stream_key_uses_context_unit():
    token = current_unit.set("alpha")
    try:
        assert stream_key() == "ponder:alpha:audit"
    finally:
        current_unit.reset(token)


def test_stream_key_explicit_overrides_context():
    assert stream_key(unit="beta") == "ponder:beta:audit"


def test_emit_writes_flat_fields_to_stream():
    mock_client = MagicMock()
    mock_client.xadd.return_value = "1715000000000-0"

    with patch("ponder.audit.emitter._get_client", return_value=mock_client):
        result = emit(_sample_event())

    assert result == "1715000000000-0"
    args, kwargs = mock_client.xadd.call_args
    stream_arg, fields_arg = args
    assert stream_arg == "ponder:default:audit"
    assert fields_arg["trace_id"] == "trace-x"
    assert fields_arg["span_id"] == "span-y"
    assert fields_arg["parent_span_id"] == "parent-z"
    assert fields_arg["event_type"] == "pipeline"
    assert fields_arg["region"] == "thalamus"
    assert fields_arg["notation_version"] == "1"
    # Payload is JSON-encoded for inspection-friendly storage
    assert json.loads(fields_arg["payload"]) == _sample_event().payload


def test_emit_handles_null_parent_as_empty_string():
    event = _sample_event()
    event.parent_span_id = None
    mock_client = MagicMock()
    mock_client.xadd.return_value = "1-0"

    with patch("ponder.audit.emitter._get_client", return_value=mock_client):
        emit(event)

    fields = mock_client.xadd.call_args[0][1]
    assert fields["parent_span_id"] == ""


def test_emit_returns_none_on_redis_error_and_does_not_raise(capsys):
    mock_client = MagicMock()
    mock_client.xadd.side_effect = redis.ConnectionError("connection refused")

    with patch("ponder.audit.emitter._get_client", return_value=mock_client):
        result = emit(_sample_event())

    assert result is None
    captured = capsys.readouterr()
    assert "audit" in captured.err.lower()
    assert "emit failed" in captured.err.lower()
