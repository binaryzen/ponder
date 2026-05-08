"""Service layer over the audit stream and adjacent system state.

This is the abstraction the CLI viewer (and future web viewer) consumes —
resource-named, paginated, read-forward, per `design/audit-interface.md`.

The HTTP wrapper (FastAPI) that exposes these as REST endpoints is a thin
adapter on top of these functions; not built yet.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterator, Optional

import redis

from ponder.audit.emitter import _get_client, stream_key


# ── Internal helpers ─────────────────────────────────────────────────────────

def _parse_entry(entry_id: str, fields: dict[str, str]) -> dict[str, Any]:
    """Convert a Redis Stream entry into the AuditEvent-shaped dict consumers expect."""
    return {
        "stream_id": entry_id,
        "trace_id": fields.get("trace_id", ""),
        "span_id": fields.get("span_id", ""),
        "parent_span_id": fields.get("parent_span_id") or None,
        "emitted_at": fields.get("emitted_at", ""),
        "event_type": fields.get("event_type", ""),
        "region": fields.get("region", ""),
        "domain": fields.get("domain", ""),
        "notation_version": int(fields.get("notation_version", "1")),
        "payload": json.loads(fields.get("payload", "{}")),
    }


def _exclusive_min(cursor: str) -> str:
    """Convert an inclusive cursor to Redis's exclusive-min syntax (prepend '(')."""
    if cursor in ("0", "-", ""):
        return "-"
    return f"({cursor}"


# ── Resource: events ─────────────────────────────────────────────────────────

def list_events(after: str = "0", limit: int = 100) -> dict[str, Any]:
    """Page through events oldest-first, exclusive of ``after``.

    Cursor convention: a Redis Stream ID (or ``"0"`` to start from the beginning).
    """
    client = _get_client()
    entries = client.xrange(stream_key(), min=_exclusive_min(after), count=limit)
    events = [_parse_entry(eid, fields) for eid, fields in entries]
    next_cursor = events[-1]["stream_id"] if events else after

    has_more = False
    if events and len(events) >= limit:
        more = client.xrange(stream_key(), min=f"({next_cursor}", count=1)
        has_more = bool(more)

    return {"events": events, "next_cursor": next_cursor, "has_more": has_more}


def tail_events(after: str = "$", block_ms: int = 5000) -> Iterator[dict[str, Any]]:
    """Live-tail events as they arrive. Yields events forever (caller controls termination).

    ``after="$"`` means start from the live edge (only events arriving after the
    call begins). Pass a specific stream ID to resume from there.
    """
    client = _get_client()
    cursor = after
    while True:
        try:
            response = client.xread({stream_key(): cursor}, count=100, block=block_ms)
        except redis.RedisError:
            time.sleep(1)
            continue
        if not response:
            continue
        for _stream, entries in response:
            for entry_id, fields in entries:
                yield _parse_entry(entry_id, fields)
                cursor = entry_id


# ── Resource: traces ─────────────────────────────────────────────────────────

def list_traces(limit: int = 20, scan_window: int = 1000) -> dict[str, Any]:
    """Recent traces with summary metadata, newest-first.

    Reads the most recent ``scan_window`` events from the stream and aggregates
    by trace_id. ``limit`` caps the returned list. For very long-running systems,
    a dedicated index (e.g., a Redis Hash per trace) would replace this scan.
    """
    client = _get_client()
    entries = client.xrevrange(stream_key(), count=scan_window)

    traces: dict[str, dict[str, Any]] = {}
    for entry_id, fields in entries:
        tid = fields.get("trace_id", "")
        if not tid:
            continue
        emitted_at = fields.get("emitted_at", "")
        if tid not in traces:
            traces[tid] = {
                "trace_id": tid,
                "first_event_at": emitted_at,
                "last_event_at": emitted_at,
                "first_stream_id": entry_id,
                "last_stream_id": entry_id,
                "event_count": 0,
                "regions": set(),
                "domain": fields.get("domain", ""),
                "status": "in_progress",
            }
        t = traces[tid]
        t["event_count"] += 1
        t["regions"].add(fields.get("region", ""))
        if emitted_at and emitted_at < t["first_event_at"]:
            t["first_event_at"] = emitted_at
            t["first_stream_id"] = entry_id
        if emitted_at and emitted_at > t["last_event_at"]:
            t["last_event_at"] = emitted_at
            t["last_stream_id"] = entry_id
        if fields.get("event_type") == "pipeline":
            try:
                payload = json.loads(fields.get("payload", "{}"))
            except json.JSONDecodeError:
                payload = {}
            if payload.get("boundary") == "turn_end":
                t["status"] = "complete"

    result = []
    for t in traces.values():
        t["regions"] = sorted(r for r in t["regions"] if r)
        result.append(t)
    result.sort(key=lambda x: x["last_event_at"], reverse=True)

    return {"traces": result[:limit]}


def get_trace_events(trace_id: str, limit: int = 1000) -> dict[str, Any]:
    """All events for a given trace_id, oldest-first.

    ``trace_id`` is matched as a *prefix*, so passing the first 8 chars (the
    display abbreviation) is sufficient when there's no collision.
    """
    client = _get_client()
    entries = client.xrange(stream_key(), count=limit * 4)
    events = [
        _parse_entry(eid, fields)
        for eid, fields in entries
        if fields.get("trace_id", "").startswith(trace_id) and fields.get("trace_id")
    ]
    return {"trace_id": trace_id, "events": events[:limit]}


# ── Health / introspection ──────────────────────────────────────────────────

def stream_info() -> dict[str, Any]:
    """Basic stream stats — length, first/last IDs."""
    client = _get_client()
    try:
        length = client.xlen(stream_key())
        first = client.xrange(stream_key(), count=1)
        last = client.xrevrange(stream_key(), count=1)
    except redis.RedisError as e:
        return {"reachable": False, "error": str(e)}
    return {
        "reachable": True,
        "stream_key": stream_key(),
        "length": length,
        "first_stream_id": first[0][0] if first else None,
        "last_stream_id": last[0][0] if last else None,
    }
