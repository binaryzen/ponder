# Post-POC Anatomy Review — Punch List

Items deferred during POC build. Reviewed once POC validation is complete,
before the v1 product spec is drafted. Each entry is a rough edge or
known-shortcut surfaced during construction.

The discipline: we accepted these consciously to keep POC velocity. The
review reads this list, decides which deserve a proper redesign vs. which
are fine to keep as-is in v1, and which go on a longer-term backlog.

---

## Orchestrator substrate

- **Specialist contract still takes a `Blackboard`, not a `SpecialistView`.**
  The `streaming_v2` demo works around this with a `_make_specialist_with_view`
  helper — verbose. Cleanest fix: change the run signature. Backward-compat
  break for existing tests; do once the dust settles.
- **`Runtime` doesn't directly accept `StateStore` / `ContextService`.**
  Currently wired externally by demos that share the underlying blackboard.
  Add proper constructor parameters.
- **No specialist failure recovery.** A specialist that raises emits a
  `specialist_failed` audit event and is dropped. There's no retry policy,
  circuit breaker, or quarantine. Unhealthy specialists could silently
  lose work.
- **No specialist timeout / hang detection.** A specialist whose `run()`
  blocks forever holds its worker. No watchdog cancels it.
- **Activation queue doesn't deduplicate.** If a watched key changes 10
  times in rapid succession, the same specialist is queued 10 times.
  Coalescing — "if this specialist is already queued or running, drop the
  new activation" — would reduce wasted work.
- **Tick scheduling is recurring-only.** The `tick_seconds` field fires
  forever. There's no "tick once and stop" or "tick until condition" or
  "tick adaptively." The streaming demos work around this with a `fired`
  flag in a closure. Worth a proper primitive.
- **Cogitator-style specialists hold the model semaphore for the entire
  run, even when streaming chunks.** A real LLM streaming call should
  release the model between chunks so other model-bound specialists can
  interleave. The substrate doesn't currently let a specialist release the
  semaphore mid-run.
- **Priority doesn't propagate past dequeue.** Once a worker has pulled an
  activation from the priority queue, ordering at the model semaphore is
  FIFO of acquire calls, not priority-aware. Real preemption requires a
  custom semaphore.
- **No separate resource pools.** One semaphore for "the model." If we
  wanted per-resource pools (LLM, vector index, tool API), the Specialist
  contract would need a list of resource tags.

## Audit

- **`audit_wrap` only emits on success.** Region failures don't currently
  produce `region_failed` audit events. Trivial: try/except in the wrapper
  with a `boundary: "region_failed"` event.
- **No `semaphore_acquired` / `semaphore_released` events.** Observability
  gap — a specialist with a long `duration_ms` could be doing real work
  or waiting on the semaphore. We can't distinguish from the trace.
- **Audit volume.** A 10-second run with 5 specialists produces 70+ events.
  For longer runs we'll want sampling, severity filtering, or per-event-type
  toggles.
- **Service exposed via Python only.** The HTTP/FastAPI wrapper described
  in `design/audit-interface.md` was deferred. CLI viewer imports the
  service module directly. Add the HTTP layer when the web viewer comes.
- **No retention policy.** The Redis Stream grows unbounded. `XTRIM MAXLEN`
  or time-based trimming on a schedule will be needed before the stream
  becomes operationally large.
- **Audit emit failures degrade silently.** `emit()` logs to stderr but
  returns None. For production-style auditability, failures should be
  surfaced to a metric and possibly cause backpressure.
- **No test specifically validates OTel field naming.** The renames (`event_id` → `span_id` etc.) are in the dataclass and there's a sanity test, but no end-to-end test confirms an event sent through the emitter is OTel-spec-compatible. Worth adding once we actually plug a Phoenix or Jaeger backend.

## Phase 1 pipeline

- **Two `SentenceTransformer` instances in memory.** Thalamus and
  Hippocampus each lazy-load their own. Cheap fix: a shared module-level
  encoder singleton.
- **Redis is provisioned but unused.** `CONTEXT.md` says Redis backs the
  blackboard; in practice the LangGraph state is dict-only. M1's audit
  emitter is the first real Redis consumer. The blackboard claim is
  aspirational; reconcile in the v1 spec.
- **Hippocampus collection is created in-process at first invoke.** Each
  `python -m ponder` cold-starts the collection check. A health-check or
  separate setup step would be cleaner.
- **No streaming output from the LangGraph pipeline.** Phase 1 is one-shot
  request/response. Phase 2's promise of token-streaming Broca isn't here
  yet.

## State / Context

- **Provider `depends_on` is prefix-matched only.** No exact-match flag.
  Predicate-based dependency declarations (per the user's note) would
  give finer control if needed.
- **`ContextService.snapshot()` recomputes all providers.** Fine for small
  catalogs; if context has hundreds of URNs and providers are expensive,
  this is wasteful. Add caching tied to `_cached`.
- **No tooling for inspecting "what sources contributed to this context
  URN."** A provider can have N sources but the consumer sees only the
  output. For audit/debugging, a "provenance trace" — which sources fed
  this output, with which weights or rationale — would be valuable.
- **No URN schema validation.** URNs are just strings; we don't validate
  that a context URN's name matches a documented namespace. As the catalog
  grows, a registry document would help (`design/urn-catalog.md`?).

## Schema-driven inference (Phase 2 work, not yet started)

- **Notation version never bumped past v1.** The whole versioning machinery
  is unexercised. First substantive change to the schema notation will
  exercise it.
- **Domain identification is single-domain-per-unit.** Multi-domain
  arbitration deferred per design notes. Will need real consideration
  during M2 if a single POC unit needs to span domains.
- **`comm_goals` is currently a flat list.** Should become a structured
  priority queue with metadata (priority, age, related_facts) once
  consolidation/revision policies are in scope (per user's vision).

## Documentation / discipline

- **Drift-check practice is informal.** Saved to memory; relies on Claude
  noticing pause points. A scheduled trigger (cron / hook) would
  institutionalize it.
- **Several deferred design questions live across multiple files.**
  `interview.md`, `concepts.md`, `data-structures.md`, `audit-interface.md`,
  this doc. The v1 product spec is the consolidation point.

---

## Process for the review

When POC is declared complete:

1. Re-read this list end-to-end in one sitting.
2. For each item: keep / fix-now / fix-in-v1 / drop. Tag inline.
3. Group the "fix-now" items into a focused work plan; the "fix-in-v1"
   items become sections of the v1 product spec.
4. Migrate any "drop" items to a CHANGELOG-style record so the rationale
   for not doing them is preserved.
