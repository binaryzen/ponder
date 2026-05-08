"""Chatter demo — exercises the orchestration substrate.

Runs five mock specialists for ~10 seconds and exits. Validates:

  - Tick-driven activation                      (InputReceiver)
  - State-change-driven activation              (IntentClassifier, SocialStateTracker)
  - Concurrent activation on same key           (both fire on raw_input)
  - Priority-based dispatch                     (Speaker priority 90, Classifier priority 10)
  - Limited model resource (semaphore)          (Speaker, Classifier need_model=True)
  - Cascading state changes                     (input -> intent -> comm goal -> speaker)
  - Orderly exit                                (IdleMonitor sets EXIT_KEY)

Mock work uses configurable LatencyProfile instances — see simulated.py.

Run:
    python -m ponder.orchestrator.demos.chatter

Inspect with:
    python -m ponder.audit.cli traces
    python -m ponder.audit.cli trace <trace_id>
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ponder.audit import current_trace_id, new_id
from ponder.orchestrator import EXIT_KEY, Blackboard, Runtime, Specialist
from ponder.orchestrator.simulated import LatencyProfile, TYPICAL_MODEL


INPUTS = [
    "Hi there, what's up?",
    "Can you explain X?",
    "I'd like to think about something.",
    "What do you remember about me?",
    "Let's change topics.",
]


@dataclass
class ChatterConfig:
    """All knobs in one place so scenarios can sweep them."""

    input_tick_seconds: float = 1.5
    classifier_latency: LatencyProfile = None
    social_latency: LatencyProfile = None
    speaker_latency: LatencyProfile = None
    max_inputs: int = 5

    def __post_init__(self) -> None:
        if self.classifier_latency is None:
            self.classifier_latency = LatencyProfile(fixed_ms=400, jitter_ms=80)
        if self.social_latency is None:
            self.social_latency = LatencyProfile(fixed_ms=100, jitter_ms=20)
        if self.speaker_latency is None:
            self.speaker_latency = LatencyProfile(fixed_ms=600, jitter_ms=80)


# ── Specialists ──────────────────────────────────────────────────────────────


def make_input_receiver(tick_seconds: float) -> Specialist:
    counter = {"n": 0}

    async def run(bb: Blackboard) -> dict | None:
        counter["n"] += 1
        return {
            "raw_input": INPUTS[counter["n"] % len(INPUTS)],
            "input_count": counter["n"],
        }

    return Specialist(
        name="input_receiver",
        watches=[],
        priority=20,
        needs_model=False,
        tick_seconds=tick_seconds,
        run=run,
    )


def make_intent_classifier(latency: LatencyProfile) -> Specialist:
    intents = ["greet", "ask", "muse", "recall", "redirect"]

    async def run(bb: Blackboard) -> dict | None:
        await latency.wait()
        text = bb.get("raw_input") or ""
        return {"intent": intents[hash(text) % len(intents)]}

    return Specialist(
        name="intent_classifier",
        watches=["raw_input"],
        priority=10,
        needs_model=True,
        run=run,
    )


def make_social_tracker(latency: LatencyProfile) -> Specialist:
    async def run(bb: Blackboard) -> dict | None:
        await latency.wait()
        return {"user_observations": (bb.get("user_observations") or 0) + 1}

    return Specialist(
        name="social_tracker",
        watches=["raw_input"],
        priority=15,
        needs_model=False,
        run=run,
    )


def make_comm_goal_manager() -> Specialist:
    async def run(bb: Blackboard) -> dict | None:
        intent = bb.get("intent")
        if intent is None:
            return None
        goals = list(bb.get("comm_goals") or [])
        goals.append(f"respond to:{intent}")
        return {"comm_goals": goals}

    return Specialist(
        name="comm_goal_manager",
        watches=["intent"],
        priority=30,
        needs_model=False,
        run=run,
    )


def make_speaker(latency: LatencyProfile) -> Specialist:
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
        priority=90,
        needs_model=True,
        should_activate=lambda bb, change: bool(change.new_value),
        run=run,
    )


def make_idle_monitor(max_inputs: int) -> Specialist:
    async def run(bb: Blackboard) -> dict | None:
        if (bb.get("input_count") or 0) >= max_inputs:
            await asyncio.sleep(2.0)
            return {EXIT_KEY: True}
        return None

    return Specialist(
        name="idle_monitor",
        watches=["input_count"],
        priority=99,
        needs_model=False,
        run=run,
    )


def build_runtime(config: ChatterConfig | None = None) -> Runtime:
    cfg = config or ChatterConfig()
    specialists = [
        make_input_receiver(cfg.input_tick_seconds),
        make_intent_classifier(cfg.classifier_latency),
        make_social_tracker(cfg.social_latency),
        make_comm_goal_manager(),
        make_speaker(cfg.speaker_latency),
        make_idle_monitor(cfg.max_inputs),
    ]
    return Runtime(specialists, worker_count=4, model_concurrency=1)


# ── Entry point ──────────────────────────────────────────────────────────────


async def main_async() -> None:
    current_trace_id.set(new_id())
    rt = build_runtime()
    await rt.run(max_runtime_seconds=20.0)

    bb = rt.blackboard
    print("\n=== blackboard at exit ===")
    print(f"input_count        : {bb.get('input_count')}")
    print(f"user_observations  : {bb.get('user_observations')}")
    print(f"intent (last)      : {bb.get('intent')}")
    print(f"comm_goals pending : {bb.get('comm_goals')}")
    print(f"spoken_log         : {bb.get('spoken_log')}")
    print(f"trace_id           : {current_trace_id.get()}")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
