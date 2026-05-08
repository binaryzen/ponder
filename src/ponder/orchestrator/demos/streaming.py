"""Streaming cogitation with interrupt handling.

Validates the orchestration patterns the user described:

  - Long-running specialists that produce output incrementally over time
    rather than all at once
  - Bursty queue fill (cogitator emits 4 chunks during a single ~5s run)
  - Chunked drain (speaker emits one chunk at a time, paced)
  - User interrupt mid-flow that clears the pending queue and inserts a
    ack-style message
  - Output specialists treated as a separate resource from cognitive
    specialists (speaker uses voice latency, not the model semaphore)

What this is *not*: a real cognitive system. The cogitator does not actually
think. Patterns are validated; content is mock.

Run:
    python -m ponder.orchestrator.demos.streaming

Inspect:
    python -m ponder.audit.cli traces
    python -m ponder.audit.cli trace <trace_id>
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ponder.audit import current_trace_id, new_id
from ponder.orchestrator import EXIT_KEY, Blackboard, Runtime, Specialist
from ponder.orchestrator.simulated import LatencyProfile, PacingProfile


@dataclass
class StreamingConfig:
    """Knobs for iterating on the scenario."""

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
                chunk_count=4, inter_chunk_ms=900, inter_chunk_jitter=150
            )
        if self.speaker_latency is None:
            self.speaker_latency = LatencyProfile(fixed_ms=600, jitter_ms=80)


# ── Specialists ──────────────────────────────────────────────────────────────


def make_input_receiver() -> Specialist:
    """One-shot: writes a single input at startup, then never again."""
    fired = {"yes": False}

    async def run(bb: Blackboard) -> dict | None:
        if fired["yes"]:
            return None
        fired["yes"] = True
        return {"raw_input": "Help me think through a decision."}

    return Specialist(
        name="input_receiver",
        watches=[],
        priority=10,
        needs_model=False,
        tick_seconds=0.2,  # fire once shortly after start
        run=run,
    )


def make_cogitator(pacing: PacingProfile, chunks: list[str]) -> Specialist:
    """Long-running. Holds the model semaphore. Writes chunks to comm_goals one at a time."""

    async def run(bb: Blackboard) -> dict | None:
        # Snapshot the input that triggered us; if it changes mid-run, we don't restart.
        topic = bb.get("raw_input")
        bb.set("cogitator_state", "thinking")

        async def append_chunk(idx: int, chunk: str) -> None:
            # Stop if user interrupted while we were paced-mid-run.
            if bb.get("user_interrupt"):
                return
            existing = list(bb.get("comm_goals") or [])
            existing.append(f"[on '{topic}'] {chunk}")
            bb.set("comm_goals", existing)

        await pacing.stream(chunks, append_chunk)

        # Mark cogitation complete only if not interrupted.
        if not bb.get("user_interrupt"):
            return {"cogitator_state": "done"}
        return {"cogitator_state": "interrupted"}

    return Specialist(
        name="cogitator",
        watches=["raw_input"],
        priority=20,
        needs_model=True,
        # Don't re-fire if raw_input is reset to the same value or while running.
        should_activate=lambda bb, change: bb.get("cogitator_state") in (None, "done", "interrupted"),
        run=run,
    )


def make_speaker(latency: LatencyProfile) -> Specialist:
    """Drains comm_goals one chunk at a time. Independent of model resource (voice)."""

    async def run(bb: Blackboard) -> dict | None:
        goals = list(bb.get("comm_goals") or [])
        if not goals:
            return None
        spoken = goals.pop(0)
        await latency.wait()
        spoken_log = list(bb.get("spoken_log") or [])
        spoken_log.append(spoken)
        return {"comm_goals": goals, "spoken_log": spoken_log}

    return Specialist(
        name="speaker",
        watches=["comm_goals"],
        priority=50,
        needs_model=False,  # voice synthesis, not the cognitive model
        should_activate=lambda bb, change: bool(change.new_value),
        run=run,
    )


def make_interrupt_handler() -> Specialist:
    """Highest priority. On user_interrupt, clears the pending queue and queues an ack."""

    async def run(bb: Blackboard) -> dict | None:
        interrupt = bb.get("user_interrupt")
        if not interrupt:
            return None
        # Discard whatever was about to be said; replace with an acknowledgment.
        return {
            "comm_goals": [f"[ack] You interrupted: {interrupt!r}. Listening."],
            "interrupt_acknowledged": interrupt,
        }

    return Specialist(
        name="interrupt_handler",
        watches=["user_interrupt"],
        priority=1,  # preempts everything else queued
        needs_model=False,
        should_activate=lambda bb, change: bool(change.new_value),
        run=run,
    )


def make_idle_monitor(max_seconds_idle: float = 1.5) -> Specialist:
    """Sets EXIT_KEY when cogitator is done AND the spoken queue is empty."""

    async def run(bb: Blackboard) -> dict | None:
        cog_state = bb.get("cogitator_state")
        if cog_state not in ("done", "interrupted"):
            return None
        # Wait for the speaker to drain.
        elapsed = 0.0
        step = 0.2
        while elapsed < max_seconds_idle:
            if not bb.get("comm_goals"):
                return {EXIT_KEY: True}
            await asyncio.sleep(step)
            elapsed += step
        return {EXIT_KEY: True}

    return Specialist(
        name="idle_monitor",
        watches=["cogitator_state"],
        priority=80,
        needs_model=False,
        run=run,
    )


def build_runtime(config: StreamingConfig | None = None) -> Runtime:
    cfg = config or StreamingConfig()
    specialists = [
        make_input_receiver(),
        make_cogitator(cfg.cogitator_pacing, cfg.chunks),
        make_speaker(cfg.speaker_latency),
        make_interrupt_handler(),
        make_idle_monitor(),
    ]
    return Runtime(specialists, worker_count=4, model_concurrency=1)


# ── Entry point ──────────────────────────────────────────────────────────────


async def main_async() -> None:
    current_trace_id.set(new_id())
    cfg = StreamingConfig()
    rt = build_runtime(cfg)

    async def maybe_interrupt() -> None:
        if cfg.interrupt_at_seconds is None:
            return
        await asyncio.sleep(cfg.interrupt_at_seconds)
        rt.blackboard.set("user_interrupt", "wait — I have a question first")

    await asyncio.gather(
        rt.run(max_runtime_seconds=15.0),
        maybe_interrupt(),
    )

    bb = rt.blackboard
    print("\n=== blackboard at exit ===")
    print(f"cogitator_state        : {bb.get('cogitator_state')}")
    print(f"interrupt_acknowledged : {bb.get('interrupt_acknowledged')}")
    print(f"comm_goals pending     : {bb.get('comm_goals')}")
    print(f"spoken_log             :")
    for s in bb.get("spoken_log") or []:
        print(f"  - {s}")
    print(f"trace_id               : {current_trace_id.get()}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
