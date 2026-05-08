"""AuditEvent type and helpers.

Field names align with OpenTelemetry conventions (span_id, parent_span_id,
trace_id) so the same emitter can later feed Phoenix / Jaeger / other
OTel-compatible backends without translation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Event types per design/audit-interface.md."""

    RECOGNITION = "recognition"
    SELECTION = "selection"
    SLOT_FILL = "slot_fill"
    BEHAVIOR_ANTICIPATION = "behavior_anticipation"
    VERDICT = "verdict"
    PIPELINE = "pipeline"


@dataclass
class AuditEvent:
    """A single auditable event in the system.

    See design/data-structures.md (v1) and design/audit-interface.md.
    """

    trace_id: str                 # UUID v4 — one per turn
    span_id: str                  # UUID v4 — this event's id
    parent_span_id: str | None    # parent event's span_id, or None for root
    emitted_at: str               # ISO 8601 UTC, millisecond precision
    event_type: EventType
    region: str                   # ponder region or "orchestrator"
    domain: str                   # bare or namespaced
    notation_version: int         # current data-structures.md is v1
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "emitted_at": self.emitted_at,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "region": self.region,
            "domain": self.domain,
            "notation_version": self.notation_version,
            "payload": self.payload,
        }


def new_id() -> str:
    """Generate a UUID v4 string. Used for both trace_id and span_id."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """UTC timestamp, ISO 8601 with millisecond precision, Z suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
