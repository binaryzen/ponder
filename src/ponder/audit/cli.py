"""Command-line viewer for the audit stream.

Modes (v0):
  ponder-audit tail              live event tail (Ctrl+C to stop)
  ponder-audit traces            list recent traces
  ponder-audit trace <trace_id>  events for one trace

This is the first consumer of the service abstraction in
`ponder.audit.service`. The same service backs the future web viewer, so
swapping or adding consumers does not require Redis-specific code here.
"""

from __future__ import annotations

import sys

from ponder.audit.service import (
    get_trace_events,
    list_traces,
    stream_info,
    tail_events,
)


def _short_ts(emitted_at: str) -> str:
    """Trim a full ISO timestamp to HH:MM:SS.mmm for compact display."""
    if not emitted_at or "T" not in emitted_at:
        return "?"
    return emitted_at.split("T", 1)[1].rstrip("Z")[:12]


def _format_event(event: dict) -> str:
    ts = _short_ts(event.get("emitted_at", ""))
    trace = (event.get("trace_id") or "?")[:8]
    region = event.get("region") or "?"
    etype = event.get("event_type") or "?"
    payload = event.get("payload") or {}

    extras = []
    if "boundary" in payload:
        extras.append(payload["boundary"])
    if "duration_ms" in payload:
        extras.append(f"{payload['duration_ms']}ms")
    if "writes" in payload and payload["writes"]:
        extras.append(f"writes={','.join(payload['writes'])}")
    extra = "  ".join(extras)

    return f"{ts}  trace:{trace}  {region:14s}  {etype:14s}  {extra}"


def cmd_tail() -> int:
    info = stream_info()
    if not info.get("reachable"):
        print(f"audit stream unreachable: {info.get('error')}", file=sys.stderr)
        return 2
    print(f"tail {info['stream_key']}  (length={info['length']})  Ctrl+C to stop")
    print("=" * 100)
    try:
        for event in tail_events(after="$"):
            print(_format_event(event))
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


def cmd_traces() -> int:
    result = list_traces(limit=20)
    if not result["traces"]:
        print("(no traces)")
        return 0
    print(f"{'TRACE':<10}  {'STARTED':<14}  {'EVENTS':>6}  {'REGIONS':<48}  STATUS")
    print("-" * 100)
    for t in result["traces"]:
        print(
            f"{t['trace_id'][:8]:<10}  "
            f"{_short_ts(t['first_event_at']):<14}  "
            f"{t['event_count']:>6}  "
            f"{','.join(t['regions'])[:46]:<48}  "
            f"{t['status']}"
        )
    return 0


def cmd_trace(trace_id: str) -> int:
    result = get_trace_events(trace_id)
    if not result["events"]:
        print(f"(no events for trace {trace_id})")
        return 1
    first_ts = result["events"][0]["emitted_at"]
    last_ts = result["events"][-1]["emitted_at"]
    print(f"trace: {trace_id}")
    print(f"{first_ts} -> {last_ts}  ({len(result['events'])} events)")
    print("=" * 100)
    for e in result["events"]:
        print(_format_event(e))
    return 0


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: ponder-audit <tail | traces | trace <trace_id>>", file=sys.stderr)
        sys.exit(2)

    cmd = args[0]
    if cmd == "tail":
        sys.exit(cmd_tail())
    if cmd == "traces":
        sys.exit(cmd_traces())
    if cmd == "trace" and len(args) == 2:
        sys.exit(cmd_trace(args[1]))

    print("Usage: ponder-audit <tail | traces | trace <trace_id>>", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
