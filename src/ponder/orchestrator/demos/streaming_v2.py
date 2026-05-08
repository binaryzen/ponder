"""Streaming demo, v2 — wired through StateStore + ContextService.

Same scenario as streaming.py (long-running cogitation, chunked output,
interrupt handling), but state is component-namespaced and reads happen
through provider-backed context URNs.

Three deliberate provider patterns demonstrated:

  context:current_input    — passthrough from the input_receiver component
  context:cogitator_state  — passthrough with default ("idle" until cogitator runs)
  context:active_intent    — prefer_highest_confidence over multiple sources
                             (here, only one writer, but the structure is
                             ready for multiple intent-classifying components)
  context:active_message   — composite that joins owner-tagged comm-goal
                             entries from across all goal-producing components

Specialists write only under their own ``component:<owner>:<key>`` URNs;
they read via ``view.get("context:...")``.

Run:
    python -m ponder.orchestrator.demos.streaming_v2

Inspect:
    python -m ponder.audit.cli traces
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ponder.audit import current_trace_id, new_id
from ponder.orchestrator import EXIT_KEY, Blackboard, Runtime, Specialist
from ponder.orchestrator.simulated import LatencyProfile, PacingProfile
from ponder.orchestrator.state import (
    ContextService,
    SpecialistView,
    StateStore,
    component_urn,
    composite,
    context_urn,
    default_if_unset,
    passthrough,
    prefer_highest_confidence,
)


@dataclass
class StreamingV2Config:
    cogitator_pacing: PacingProfile = None
    speaker_latency: LatencyProfile = None
    interrupt_at_seconds: float | None = 2.5
    chunks: list[str] = field(default_factory=lambda: [
        "First, the relevant background:",
        "There are three main considerations to weigh.",
        "The trade-offs depend on your priorities.",
        "On balance, I'd suggest the second option.",
    ])

    def __post_init__(self) -> None:
        if self.cogitator_pacing is None:
            self.cogitator_pacing = PacingProfile(
                chunk_count=4, inter_chunk_ms=900, inter_chunk_jitter=150, seed=1
            )
        if self.speaker_latency is None:
            self.speaker_latency = LatencyProfile(fixed_ms=600, jitter_ms=80, seed=2)


# ── Specialists (each declares its own owner; writes go to that namespace) ──


def _make_specialist_with_view(
    *,
    name: str,
    state: StateStore,
    context: ContextService,
    watches: list[str],
    priority: int,
    needs_model: bool,
    body: callable,
    should_activate: callable | None = None,
    tick_seconds: float | None = None,
) -> Specialist:
    """Wrap a body that takes a SpecialistView in the standard Specialist contract."""
    view = SpecialistView(owner=name, state=state, context=context)

    async def run(_blackboard) -> dict | None:
        # The Specialist contract still passes a Blackboard, but we ignore it
        # in favor of the view object closed over here. Returning None keeps
        # the runtime from auto-applying any updates — components write
        # through the view directly.
        result = body(view)
        if asyncio.iscoroutine(result):
            await result
        return None

    return Specialist(
        name=name,
        watches=watches,
        priority=priority,
        needs_model=needs_model,
        tick_seconds=tick_seconds,
        run=run,
        should_activate=should_activate or (lambda bb, change: True),
    )


def build_specialists(state: StateStore, context: ContextService, cfg: StreamingV2Config) -> list[Specialist]:
    fired_input = {"yes": False}

    async def input_body(view: SpecialistView) -> None:
        if fired_input["yes"]:
            return
        fired_input["yes"] = True
        view.write("raw", "Help me think through a decision.")

    async def cogitator_body(view: SpecialistView) -> None:
        topic = view.get(context_urn("current_input"))
        view.write("state", "thinking")

        async def append_chunk(idx: int, chunk: str) -> None:
            if view.get(context_urn("user_interrupt")):
                return
            existing = list(view.state.read(component_urn("cogitator", "chunks"), []))
            existing.append(f"[on '{topic}'] {chunk}")
            view.write("chunks", existing)

        await cfg.cogitator_pacing.stream(cfg.chunks, append_chunk)

        if view.get(context_urn("user_interrupt")):
            view.write("state", "interrupted")
        else:
            view.write("state", "done")

    async def speaker_body(view: SpecialistView) -> None:
        # Read the merged outgoing queue from context.
        queue = list(view.get(context_urn("active_message")) or [])
        if not queue:
            return
        spoken = queue[0]  # take the head
        await cfg.speaker_latency.wait()

        # Mark the head as spoken in our own namespace; the provider will
        # recompute active_message excluding spoken items.
        spoken_log = list(view.state.read(component_urn("speaker", "spoken_log"), []))
        spoken_log.append(spoken)
        view.write("spoken_log", spoken_log)

        # Also signal which item we consumed so producers can clear theirs.
        view.write("last_consumed", spoken)

    async def interrupt_body(view: SpecialistView) -> None:
        interrupt = view.get(context_urn("user_interrupt"))
        if not interrupt:
            return
        # Override: discard pending cogitator chunks, queue an ack under our own URN.
        view.write("ack_message", f"[ack] You interrupted: {interrupt!r}. Listening.")
        view.write("override_clear_chunks", True)

    async def idle_body(view: SpecialistView) -> None:
        cog_state = view.get(context_urn("cogitator_state"))
        if cog_state not in ("done", "interrupted"):
            return
        # Drain wait — give speaker a chance to clear active_message.
        elapsed = 0.0
        step = 0.2
        while elapsed < 1.5:
            if not view.get(context_urn("active_message")):
                break
            await asyncio.sleep(step)
            elapsed += step
        # Set EXIT_KEY on the underlying blackboard so the Runtime detects exit.
        state.blackboard.set(EXIT_KEY, True)

    return [
        _make_specialist_with_view(
            name="input_receiver", state=state, context=context,
            watches=[], priority=10, needs_model=False, tick_seconds=0.2,
            body=input_body,
        ),
        _make_specialist_with_view(
            name="cogitator", state=state, context=context,
            watches=[component_urn("input_receiver", "raw")],
            priority=20, needs_model=True,
            body=cogitator_body,
            should_activate=lambda bb, ch: state.read(component_urn("cogitator", "state")) in (None, "done", "interrupted"),
        ),
        _make_specialist_with_view(
            name="speaker", state=state, context=context,
            watches=[context_urn("active_message")],
            priority=50, needs_model=False,
            body=speaker_body,
            should_activate=lambda bb, ch: bool(ch.new_value),
        ),
        _make_specialist_with_view(
            name="interrupt_handler", state=state, context=context,
            watches=[context_urn("user_interrupt")],
            priority=1, needs_model=False,
            body=interrupt_body,
            should_activate=lambda bb, ch: bool(ch.new_value),
        ),
        _make_specialist_with_view(
            name="idle_monitor", state=state, context=context,
            watches=[context_urn("cogitator_state")],
            priority=80, needs_model=False,
            body=idle_body,
        ),
    ]


# ── Provider registration ────────────────────────────────────────────────────


def register_providers(context: ContextService) -> None:
    # Pure passthroughs.
    context.register(
        context_urn("current_input"),
        passthrough(component_urn("input_receiver", "raw")),
    )
    context.register(
        context_urn("user_interrupt"),
        passthrough(component_urn("user", "interrupt")),
    )

    # Default-if-unset: until the cogitator writes its state, treat as "idle".
    context.register(
        context_urn("cogitator_state"),
        default_if_unset(component_urn("cogitator", "state"), default="idle"),
    )

    # Composite: merge cogitator's pending chunks (minus spoken) plus any
    # ack message from the interrupt handler. If interrupt fired, drop chunks.
    def active_message_fn(store):
        if store.read(component_urn("interrupt_handler", "override_clear_chunks")):
            cog_chunks = []
        else:
            cog_chunks = list(store.read(component_urn("cogitator", "chunks"), []))
        ack = store.read(component_urn("interrupt_handler", "ack_message"))
        spoken = list(store.read(component_urn("speaker", "spoken_log"), []))
        # Filter out anything already spoken.
        outgoing = [m for m in cog_chunks if m not in spoken]
        if ack and ack not in spoken:
            outgoing = [ack] + outgoing
        return outgoing

    context.register(
        context_urn("active_message"),
        composite(
            active_message_fn,
            depends_on=[
                component_urn("cogitator", "chunks"),
                component_urn("interrupt_handler", "ack_message"),
                component_urn("interrupt_handler", "override_clear_chunks"),
                component_urn("speaker", "spoken_log"),
            ],
        ),
    )


# ── Wiring ───────────────────────────────────────────────────────────────────


def build_runtime(config: StreamingV2Config | None = None) -> tuple[Runtime, ContextService]:
    cfg = config or StreamingV2Config()
    bb = Blackboard()
    state = StateStore(bb)
    context = ContextService(state, publish_changes_via=bb)
    register_providers(context)

    specialists = build_specialists(state, context, cfg)
    rt = Runtime(specialists, worker_count=4, model_concurrency=1)
    # Replace the runtime's blackboard with our shared instance so the state
    # store and the runtime see the same writes.
    rt.blackboard = bb
    rt.dispatcher._bb = bb

    return rt, context


# ── Entry point ──────────────────────────────────────────────────────────────


async def main_async() -> None:
    current_trace_id.set(new_id())
    cfg = StreamingV2Config()
    rt, context = build_runtime(cfg)
    await context.start()

    async def maybe_interrupt() -> None:
        if cfg.interrupt_at_seconds is None:
            return
        await asyncio.sleep(cfg.interrupt_at_seconds)
        # Write under the user namespace; the user_interrupt context URN
        # passthroughs from there.
        rt.blackboard.set(component_urn("user", "interrupt"), "wait, I have a question first")

    try:
        await asyncio.gather(
            rt.run(max_runtime_seconds=15.0),
            maybe_interrupt(),
        )
    finally:
        await context.stop()

    print("\n=== context snapshot at exit ===")
    for urn, val in context.snapshot().items():
        print(f"  {urn:<32s} = {val!r}")
    print("\n=== component state at exit ===")
    bb = rt.blackboard
    for k in sorted(bb.keys()):
        if k.startswith("component:") or k == EXIT_KEY:
            print(f"  {k:<48s} = {bb.get(k)!r}")
    print(f"\ntrace_id: {current_trace_id.get()}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
