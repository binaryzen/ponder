"""Publishes AuditEvents to a Redis Stream.

Stream key convention: ``ponder:<unit>:audit`` (per design/audit-interface.md).
Events are stored as flat field/value entries on the stream so redis-cli
inspection (XRANGE) is human-readable; the ``payload`` field holds JSON
for the event-type-specific body.
"""

from __future__ import annotations

import json
import sys
from typing import Optional

import redis

from ponder.audit.context import current_unit
from ponder.audit.events import AuditEvent
from ponder.config import get_config


_client: Optional[redis.Redis] = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_config().redis_url, decode_responses=True)
    return _client


def stream_key(unit: Optional[str] = None) -> str:
    """Compute the Redis Stream key for a given unit (or the active context unit)."""
    return f"ponder:{unit or current_unit.get()}:audit"


def emit(event: AuditEvent) -> Optional[str]:
    """Publish ``event`` to the audit stream.

    Returns the Redis-assigned stream entry ID on success, ``None`` on failure.
    Failures are logged to stderr but do not raise — audit must not crash the
    turn it's observing.
    """
    fields = {
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "parent_span_id": event.parent_span_id or "",
        "emitted_at": event.emitted_at,
        "event_type": event.event_type.value,
        "region": event.region,
        "domain": event.domain,
        "notation_version": str(event.notation_version),
        "payload": json.dumps(event.payload),
    }
    try:
        return _get_client().xadd(stream_key(), fields)
    except redis.RedisError as e:
        print(f"[audit] emit failed: {e}", file=sys.stderr)
        return None


def reset_client() -> None:
    """Reset the singleton client. Test helper."""
    global _client
    _client = None
