"""Tests for ponder.audit.instrumentation — wrapping nodes and pipeline events."""

from unittest.mock import patch

import pytest

from ponder.audit.context import current_parent_span_id, current_trace_id
from ponder.audit.events import EventType
from ponder.audit.instrumentation import audit_wrap, emit_pipeline_event


@pytest.fixture(autouse=True)
def reset_audit_context():
    trace_token = current_trace_id.set("test-trace")
    parent_token = current_parent_span_id.set("")
    yield
    current_parent_span_id.reset(parent_token)
    current_trace_id.reset(trace_token)


def test_audit_wrap_calls_underlying_node_and_returns_its_result():
    captured_state = {}

    def fake_node(state):
        captured_state["received"] = state
        return {"output": "ok"}

    wrapped = audit_wrap(fake_node, "thalamus")
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        result = wrapped({"input": "x"})

    assert result == {"output": "ok"}
    assert captured_state["received"] == {"input": "x"}
    mock_emit.assert_called_once()


def test_audit_wrap_emits_pipeline_region_complete_event():
    def fake_node(state):
        return {"input_type": "question"}

    wrapped = audit_wrap(fake_node, "thalamus")
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        wrapped({})

    event = mock_emit.call_args[0][0]
    assert event.event_type == EventType.PIPELINE
    assert event.region == "thalamus"
    assert event.trace_id == "test-trace"
    assert event.payload["boundary"] == "region_complete"
    assert "duration_ms" in event.payload
    assert event.payload["writes"] == ["input_type"]


def test_audit_wrap_inherits_parent_span_from_context():
    current_parent_span_id.set("parent-span-id")

    def fake_node(state):
        return {}

    wrapped = audit_wrap(fake_node, "any")
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        wrapped({})

    event = mock_emit.call_args[0][0]
    assert event.parent_span_id == "parent-span-id"


def test_audit_wrap_handles_non_dict_node_result():
    def weird_node(state):
        return None  # robustness check

    wrapped = audit_wrap(weird_node, "weird")
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        result = wrapped({})

    assert result is None
    event = mock_emit.call_args[0][0]
    assert event.payload["writes"] == []


def test_emit_pipeline_event_returns_span_id():
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        span_id = emit_pipeline_event("turn_start", payload={"raw_input": "hi"})

    event = mock_emit.call_args[0][0]
    assert event.span_id == span_id
    assert event.event_type == EventType.PIPELINE
    assert event.region == "orchestrator"
    assert event.payload["boundary"] == "turn_start"
    assert event.payload["raw_input"] == "hi"


def test_emit_pipeline_event_default_region_is_orchestrator():
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        emit_pipeline_event("turn_end")

    event = mock_emit.call_args[0][0]
    assert event.region == "orchestrator"


def test_emit_pipeline_event_uses_specified_region():
    with patch("ponder.audit.instrumentation.emit") as mock_emit:
        emit_pipeline_event("memory_stored", region="hippocampus")

    event = mock_emit.call_args[0][0]
    assert event.region == "hippocampus"
