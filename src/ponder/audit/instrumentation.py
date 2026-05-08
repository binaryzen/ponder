"""Audit instrumentation helpers.

`audit_wrap` wraps a region node function so that completion of that region
emits a ``pipeline`` event with timing and write metadata. ``emit_pipeline_event``
is the one-shot helper used at turn boundaries (turn_start, turn_end, etc.).
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from ponder.audit.context import (
    current_domain,
    current_parent_span_id,
    current_trace_id,
)
from ponder.audit.emitter import emit
from ponder.audit.events import AuditEvent, EventType, new_id, now_iso


def audit_wrap(node_fn: Callable[..., dict], region_name: str) -> Callable[..., dict]:
    """Wrap a region node so it emits a ``pipeline.region_complete`` event after running.

    The wrapped function preserves the LangGraph node contract: takes a state
    dict, returns a state-update dict.
    """

    def wrapped(state: Any) -> dict:
        start = time.monotonic()
        result = node_fn(state)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        event = AuditEvent(
            trace_id=current_trace_id.get(),
            span_id=new_id(),
            parent_span_id=current_parent_span_id.get() or None,
            emitted_at=now_iso(),
            event_type=EventType.PIPELINE,
            region=region_name,
            domain=current_domain.get(),
            notation_version=1,
            payload={
                "boundary": "region_complete",
                "duration_ms": elapsed_ms,
                "writes": list(result.keys()) if isinstance(result, dict) else [],
            },
        )
        emit(event)
        return result

    return wrapped


def emit_pipeline_event(
    boundary: str,
    region: str = "orchestrator",
    payload: Optional[dict] = None,
) -> str:
    """Emit a one-shot ``pipeline`` event for a turn boundary or other lifecycle marker.

    Returns the new event's span_id so the caller can use it as a parent for
    subsequent child events.
    """
    full_payload: dict = dict(payload) if payload else {}
    full_payload["boundary"] = boundary

    span_id = new_id()
    event = AuditEvent(
        trace_id=current_trace_id.get(),
        span_id=span_id,
        parent_span_id=current_parent_span_id.get() or None,
        emitted_at=now_iso(),
        event_type=EventType.PIPELINE,
        region=region,
        domain=current_domain.get(),
        notation_version=1,
        payload=full_payload,
    )
    emit(event)
    return span_id
