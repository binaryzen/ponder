"""Ponder audit subsystem.

Public surface (stable):

    from ponder.audit import (
        AuditEvent, EventType, new_id, now_iso,
        emit, stream_key,
        current_trace_id, current_parent_span_id, current_domain, current_unit,
        audit_wrap, emit_pipeline_event,
    )

Service layer (for consumers — CLI, web viewer):

    from ponder.audit import service
    service.list_events(...)
    service.list_traces(...)
    service.get_trace_events(...)
    service.tail_events(...)
"""

from ponder.audit.context import (
    current_domain,
    current_parent_span_id,
    current_trace_id,
    current_unit,
)
from ponder.audit.emitter import emit, reset_client, stream_key
from ponder.audit.events import AuditEvent, EventType, new_id, now_iso
from ponder.audit.instrumentation import audit_wrap, emit_pipeline_event

__all__ = [
    "AuditEvent",
    "EventType",
    "new_id",
    "now_iso",
    "emit",
    "stream_key",
    "reset_client",
    "current_trace_id",
    "current_parent_span_id",
    "current_domain",
    "current_unit",
    "audit_wrap",
    "emit_pipeline_event",
]
