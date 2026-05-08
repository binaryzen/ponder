"""Panel-friendly runtime factory.

Mirrors the streaming_v2 demo (cogitator + speaker + interrupt_handler with
StateStore + ContextService) but adapted for interactive use:

  - No auto-firing input_receiver. Input arrives via panel.
  - Input-bridge specialist forwards `component:panel:request` writes into
    the existing pipeline's input URN.
  - No auto-exit. Runtime runs until externally stopped.
  - No auto-interrupt. Interrupts come from panel via `component:user:interrupt`.

The diagnostics CLI uses this. Other panel-driven runtimes can follow the
same shape.
"""

from __future__ import annotations

import asyncio

from ponder.orchestrator import Blackboard, Runtime, Specialist
from ponder.orchestrator.simulated import LatencyProfile, PacingProfile
from ponder.orchestrator.state import (
    ContextService,
    StateStore,
    component_urn,
    composite,
    context_urn,
    default_if_unset,
    passthrough,
)


def build_panel_runtime() -> tuple[Runtime, StateStore, ContextService]:
    bb = Blackboard()
    state = StateStore(bb)
    context = ContextService(state, publish_changes_via=bb)

    register_providers(context)
    specialists = build_specialists(state, context)

    rt = Runtime(specialists, worker_count=4, model_concurrency=1)
    rt.blackboard = bb
    rt.dispatcher._bb = bb
    return rt, state, context


def register_providers(context: ContextService) -> None:
    context.register(
        context_urn("current_input"),
        passthrough(component_urn("input_receiver", "raw")),
    )
    context.register(
        context_urn("user_interrupt"),
        passthrough(component_urn("user", "interrupt")),
    )
    context.register(
        context_urn("cogitator_state"),
        default_if_unset(component_urn("cogitator", "state"), default="idle"),
    )

    def active_message_fn(store):
        if store.read(component_urn("interrupt_handler", "override_clear_chunks")):
            cog_chunks = []
        else:
            cog_chunks = list(store.read(component_urn("cogitator", "chunks"), []))
        ack = store.read(component_urn("interrupt_handler", "ack_message"))
        spoken = list(store.read(component_urn("speaker", "spoken_log"), []))
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


def build_specialists(state: StateStore, context: ContextService) -> list[Specialist]:
    chunks = [
        "First, the relevant background:",
        "There are three main considerations to weigh.",
        "The trade-offs depend on your priorities.",
        "On balance, I'd suggest the second option.",
    ]
    pacing = PacingProfile(chunk_count=4, inter_chunk_ms=900, inter_chunk_jitter=150, seed=1)
    speaker_latency = LatencyProfile(fixed_ms=600, jitter_ms=80, seed=2)

    # Input bridge: panel writes to component:panel:request; we forward the
    # value to component:input_receiver:raw, which the cogitator watches.
    # Each new request resets the cogitator's state so it can re-fire.
    async def input_bridge_run(bb):
        text = state.read(component_urn("panel", "request"))
        if not text:
            return None
        # Reset everything from the prior turn that might block re-firing.
        state.write("cogitator", "state", None)
        state.write("cogitator", "chunks", [])
        state.write("interrupt_handler", "override_clear_chunks", False)
        state.write("interrupt_handler", "ack_message", None)
        state.write("user", "interrupt", None)
        state.write("speaker", "spoken_log", [])
        # Now fire the pipeline.
        state.write("input_receiver", "raw", text)
        return None

    input_bridge = Specialist(
        name="input_bridge",
        watches=[component_urn("panel", "request")],
        priority=5,
        needs_model=False,
        run=input_bridge_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    # Cogitator: long-running, holds model semaphore, streams chunks.
    async def cogitator_run(bb):
        topic = state.read(component_urn("input_receiver", "raw"))
        state.write("cogitator", "state", "thinking")

        async def append_chunk(idx, chunk):
            if state.read(component_urn("user", "interrupt")):
                return
            existing = list(state.read(component_urn("cogitator", "chunks"), []))
            existing.append(f"[on '{topic}'] {chunk}")
            state.write("cogitator", "chunks", existing)

        await pacing.stream(chunks, append_chunk)
        new_state = "interrupted" if state.read(component_urn("user", "interrupt")) else "done"
        state.write("cogitator", "state", new_state)
        return None

    cogitator = Specialist(
        name="cogitator",
        watches=[component_urn("input_receiver", "raw")],
        priority=20,
        needs_model=True,
        run=cogitator_run,
        should_activate=lambda bb, ch: state.read(component_urn("cogitator", "state")) in (None, "done", "interrupted"),
    )

    # Speaker: drains comm queue (via context:active_message). Independent of model.
    async def speaker_run(bb):
        queue = list(context.get(context_urn("active_message")) or [])
        if not queue:
            return None
        spoken = queue[0]
        await speaker_latency.wait()
        spoken_log = list(state.read(component_urn("speaker", "spoken_log"), []))
        spoken_log.append(spoken)
        state.write("speaker", "spoken_log", spoken_log)
        return None

    speaker = Specialist(
        name="speaker",
        watches=[context_urn("active_message")],
        priority=50,
        needs_model=False,
        run=speaker_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    # Interrupt handler: clears pending chunks, queues an ack.
    async def interrupt_run(bb):
        interrupt = state.read(component_urn("user", "interrupt"))
        if not interrupt:
            return None
        state.write("interrupt_handler", "ack_message", f"[ack] You interrupted: {interrupt!r}. Listening.")
        state.write("interrupt_handler", "override_clear_chunks", True)
        return None

    interrupt_handler = Specialist(
        name="interrupt_handler",
        watches=[context_urn("user_interrupt")],
        priority=1,
        needs_model=False,
        run=interrupt_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    return [input_bridge, cogitator, speaker, interrupt_handler]
