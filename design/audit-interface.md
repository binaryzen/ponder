# Audit & Inspection Interface — v0 contract

The audit event stream and the system state visible through it should be
consumable by **multiple front-ends** — a CLI viewer, a future web viewer,
ad-hoc scripts. Coupling any one consumer directly to Redis would foreclose
that.

This document specifies the service abstraction that mediates between the
substrate (Redis Streams + Hash, Qdrant, schema registry) and the consumers.

---

## Architecture

```
            ┌──────────────────────────────┐
            │    Audit & Inspection API     │
            │      (resource-oriented)      │
            └──────────────┬────────────────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
┌──────▼──────┐    ┌───────▼──────┐    ┌──────▼──────┐
│ CLI viewer  │    │ Web viewer   │    │  Scripts /  │
│  (Textual?) │    │ (later)      │    │   tooling   │
└─────────────┘    └──────────────┘    └─────────────┘

                   API consumes from:
                   - Redis Stream (`ponder:<unit>:audit`)
                   - Redis Hash (blackboard state)
                   - Qdrant (Hippocampus inspection)
                   - In-memory schema registry (later)
```

The API is the contract. CLI and web viewers are two implementations of
*display*; they share the service layer.

---

## Resource model

Every queryable subset of system state is a **named resource**. Resources
are addressable by URL path. The catalog (v0):

| Resource | Path | Description |
|---|---|---|
| Traces (list) | `GET /traces` | Recent traces with metadata. Paginated. |
| Trace detail | `GET /traces/{trace_id}` | Single trace summary (start/end, region count, status). |
| Trace events | `GET /traces/{trace_id}/events` | Tree of events for one trace. Read-forward paginated. |
| All events | `GET /events` | Flat audit stream across all traces. Read-forward paginated. |
| Live event tail | `GET /events/tail` | Server-Sent Events stream, opens a long-lived connection. |
| Blackboard snapshot | `GET /blackboard/{trace_id}` | Current blackboard state for a trace. |
| Schemas (list) | `GET /schemas` | Registered schemas. |
| Schema detail | `GET /schemas/{schema_id}` | Single schema with all entities/relationships/variants. |
| Regions | `GET /regions` | Registered regions and last-activity timestamps. |
| Domains | `GET /domains` | Configured domains and their canonical-predicate sets. |

New resources are added by registering a handler under a new path. The set
is open.

Resource names are stable contracts — once published, they don't get
renamed without a deprecation cycle.

---

## Pagination — read-forward, cursor-based

Event streams are append-only and naturally cursor-paginatable. Use Redis
Stream IDs as cursors directly (`<ms>-<seq>` format, e.g.,
`1715000000000-0`). They are monotonic, opaque to clients, and free.

**Request:**
```
GET /events?after=<cursor>&limit=<n>
```

- `after` — cursor; `0` (or omitted) means "from beginning"
- `limit` — max events to return, default 100, max 1000

**Response:**
```json
{
  "events": [...],          // up to <limit> events
  "next_cursor": "1715...",  // pass back as `after` to continue
  "has_more": true           // false when caught up
}
```

`has_more: false` means the consumer is at the live edge. Polling with
the same cursor will get nothing until new events arrive.

For continuous tailing, use the SSE endpoint instead of polling:
```
GET /events/tail?after=<cursor>
```
Server emits events as they arrive. Connection persists. Reconnect with
the last seen cursor to resume.

The same cursor pattern applies to `/traces/{id}/events`.

For non-stream resources (`/schemas`, `/regions`, `/domains`), pagination
is offset-based or unpaginated depending on expected volume. Default to
unpaginated for v0; introduce pagination per resource only when actual
volume warrants.

---

## OpenTelemetry compatibility

AuditEvent fields should align with OpenTelemetry naming so the same emitter
feeds Redis Stream and any OTel backend (Phoenix, Jaeger, Honeycomb, etc.)
without translation:

| Current name | OTel-aligned name | Notes |
|---|---|---|
| `event_id` | `span_id` | One span per event |
| `parent_event_id` | `parent_span_id` | Parent reference |
| `trace_id` | `trace_id` | Unchanged |
| `event_type` | `attributes.event_type` | OTel uses generic span name + attributes |
| `region` | `service.name` (resource) or `attributes.region` | Service identification in OTel |
| `payload` | `attributes` | Free-form key/value |
| `emitted_at` | `start_time_unix_nano` (with `end_time` for duration) | Required by OTel span shape |

This is a renaming pass on `AuditEvent` in `data-structures.md`. The change
is mechanical; doing it now (before M1 emits the first event) costs almost
nothing. Doing it later costs the price of every persisted event.

---

## CLI viewer UX requirements

Captured from user direction:

- **Nimble.** Simple to navigate. No mouse, no menus to traverse.
- **Single keypress to action where possible.** Vim-style: `j`/`k` for nav, Enter to drill in, `q` to quit, `/` to filter, `t` to tail.
- **Plain output.** Doesn't need to be fancy; clarity over visual polish.

Three primary modes:

1. **Traces list** (default landing) — recent traces, sortable, filterable.
2. **Trace detail / tree** — drill into one trace; show event tree with parent/child indentation; keypress to expand/collapse subtrees.
3. **Live tail** — events as they arrive across all traces; pause/resume.

Single-key bindings (suggested):

| Key | Action |
|---|---|
| `j` / `k` | Move cursor down / up |
| `Enter` | Drill into selected item |
| `Esc` / `Backspace` | Up one level |
| `t` | Toggle live tail |
| `/` | Filter (text input until Enter) |
| `r` | Refresh |
| `q` | Quit |

Implementation candidate: **Textual** (Python TUI framework). Async-native
(matches the streaming model), has built-in tree/table widgets, terminal-
ergonomic, ~clean MVC. Alternatives: `prompt_toolkit`, plain `curses`.
Decision deferred until implementation.

---

## Service implementation — deferred decisions

Decisions that don't need to be made until M1 implementation begins:

- **Transport.** HTTP/JSON is the obvious default; gRPC would be heavier.
- **Framework.** FastAPI fits well (Python, async-native, OpenAPI-spec
  generated for free, Pydantic models reusable from `ponder.config` etc.).
- **Live tail mechanism.** SSE simpler than WebSocket and naturally
  read-forward; preferred unless something forces WebSocket.
- **Auth.** None for POC. Localhost-only. Tighten when networked.
- **Service deployment.** Co-located with the cognitive unit (in-pod) or
  separate? Probably co-located for POC; separable later.

---

## What this enables

- CLI viewer ships first, consuming the service.
- Web viewer ships later, consuming the *same* service. No coupling
  through Redis schema specifics.
- Phoenix or other OTel backends can be added as additional consumers
  (or as an alternative emit path) without touching the CLI.
- Ad-hoc inspection scripts (`curl /traces` | jq) work out of the box.

---

## What's out of scope for v0

- Search across content (e.g., full-text search of payloads). Defer until
  practice demands it.
- Mutations. v0 is read-only; modifying state through the API is a
  separate (and much riskier) design problem.
- Authentication, multi-tenancy, rate limiting. POC-scale only.
- Visualization beyond tree/list views. Waterfalls, timeline charts —
  Phoenix or similar already does these well; build vs. buy is a real
  question if/when we want them.
