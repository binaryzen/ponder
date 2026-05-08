"""Tests for ponder.audit.events — type construction, serialization, helpers."""

import re
from datetime import datetime

import pytest

from ponder.audit.events import AuditEvent, EventType, new_id, now_iso


def test_new_id_is_uuid_v4_format():
    val = new_id()
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", val)


def test_new_id_unique():
    assert new_id() != new_id()


def test_now_iso_format():
    val = now_iso()
    assert val.endswith("Z")
    # Parse back
    parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_now_iso_millisecond_precision():
    val = now_iso()
    # YYYY-MM-DDTHH:MM:SS.mmmZ
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", val)


def test_audit_event_to_dict_roundtrip():
    event = AuditEvent(
        trace_id="t-1",
        span_id="s-1",
        parent_span_id="p-1",
        emitted_at="2026-05-07T12:00:00.000Z",
        event_type=EventType.PIPELINE,
        region="thalamus",
        domain="default",
        notation_version=1,
        payload={"boundary": "region_complete", "duration_ms": 12.3},
    )
    d = event.to_dict()
    assert d["trace_id"] == "t-1"
    assert d["span_id"] == "s-1"
    assert d["parent_span_id"] == "p-1"
    assert d["event_type"] == "pipeline"
    assert d["payload"]["boundary"] == "region_complete"


def test_audit_event_parent_span_id_optional():
    event = AuditEvent(
        trace_id="t-1",
        span_id="s-1",
        parent_span_id=None,
        emitted_at="2026-05-07T12:00:00.000Z",
        event_type=EventType.PIPELINE,
        region="orchestrator",
        domain="default",
        notation_version=1,
    )
    assert event.parent_span_id is None
    assert event.payload == {}


def test_event_type_values():
    """Confirm the event_type enum matches design/audit-interface.md."""
    expected = {"recognition", "selection", "slot_fill", "behavior_anticipation", "verdict", "pipeline"}
    assert {e.value for e in EventType} == expected


def test_audit_event_uses_otel_field_names():
    """Per design/audit-interface.md: span_id, parent_span_id, trace_id are the OTel-aligned names."""
    fields = AuditEvent.__dataclass_fields__
    assert "span_id" in fields
    assert "parent_span_id" in fields
    assert "trace_id" in fields
    # Old names should NOT exist:
    assert "event_id" not in fields
    assert "parent_event_id" not in fields
