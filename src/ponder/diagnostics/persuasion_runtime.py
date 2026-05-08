"""Persuasion demo runtime — real-LLM speaker with canned argument queue.

Scenario: the speaker advocates that remote work is superior to office work.
The user argues the opposite. The strategist releases ArgumentUnits (structured
semantic content) onto a shared queue. The speaker voices them via LLM —
natural register, appropriate segues — without synthesising new claims.
The goal tracker watches for user agreement signals.

Async cases exercised:

  Reactive ordering: on each user input, strategist (priority=10) is
  dispatched before speaker (priority=20). Strategist finishes in
  microseconds; speaker's first act is reading the queue, so it reliably
  sees the new unit.

  Tick enrichment: strategist fires every 8s independent of user turns.
  On second tick it enriches a pending unit in-place. If the speaker has
  already delivered that unit the enrichment arrives too late — visible
  in component state but not in spoken_log. If it arrives before the next
  user turn the speaker voices the richer version.

  Turn-taking: speaker only fires on user input (not on queue additions).
  Units accumulated between turns are delivered in the next speaker turn.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ponder.model_client import generate_streaming
from ponder.orchestrator import Blackboard, Runtime, Specialist
from ponder.orchestrator.state import (
    ContextService,
    StateStore,
    component_urn,
    context_urn,
    default_if_unset,
    passthrough,
)


# ── Scenario ──────────────────────────────────────────────────────────────────

SPEAKER_POSITION = (
    "Remote work is more productive, healthier, and more sustainable than office work."
)

_AGREEMENT_TOKENS = frozenset({
    "agree", "agreed", "you're right", "fair point", "convinced",
    "that's true", "i see", "makes sense", "ok fine", "you've got",
    "good point", "touché", "alright",
})

# ── ArgumentUnit ──────────────────────────────────────────────────────────────


@dataclass
class ArgumentUnit:
    id: str
    type: Literal["assertion", "relation", "concession", "reframe", "question"]
    content: str
    manner: Literal["direct", "hedged", "empathetic", "rhetorical"]
    responds_to: str | None = None  # keyword in user text; bumped to front if matched

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "manner": self.manner,
            "responds_to": self.responds_to,
        }


# ── Canned sequence ───────────────────────────────────────────────────────────
# Released one per strategist activation (reactive or tick).
# Arc: establish evidence → connect to lived cost → reframe opposition term
# → concede-and-pivot → broaden to systemic stakes.

_SEQUENCE: tuple[ArgumentUnit, ...] = (
    ArgumentUnit(
        "a1", "assertion",
        "Productivity research consistently shows remote workers are 13–20% more "
        "productive, with fewer interruptions and better sustained focus.",
        "direct",
    ),
    ArgumentUnit(
        "a2", "relation",
        "Commuting absorbs 1–2 hours of cognitive and physical energy before the "
        "work day even begins — that deficit compounds across a career.",
        "empathetic",
    ),
    ArgumentUnit(
        "a3", "reframe",
        "What gets called 'collaboration' in offices is often unscheduled interruption. "
        "Deep work — the kind that creates real value — requires focused solitude.",
        "rhetorical",
        responds_to="collaboration",
    ),
    ArgumentUnit(
        "a4", "concession",
        "Social bonds genuinely matter. But async tools create richer, documented "
        "communication than hallway conversations — and they scale across time zones.",
        "hedged",
        responds_to="culture",
    ),
    ArgumentUnit(
        "a5", "assertion",
        "The environmental cost of daily commutes is measurable. Remote work is one "
        "of the highest-leverage individual contributions to reducing emissions.",
        "direct",
    ),
)

# Late-arriving enrichment for a2 — simulates an async context retrieval completing.
_ENRICHMENT_FOR_A2 = (
    " In software specifically, each context switch from an unplanned meeting "
    "costs an average of 23 minutes of recovery time."
)

# ── Speaker prompt ─────────────────────────────────────────────────────────────

_SPEAKER_SYSTEM = (
    "You are an advocate for the position: " + SPEAKER_POSITION + "\n\n"
    "You have been given specific points to make this turn. "
    "Voice them naturally — conversational register, good segues, persuasive tone. "
    "Do not invent claims beyond what you are given. "
    "Speak directly to the user. Keep your response to 2–4 sentences."
)


def _build_speaker_prompt(
    units: list[dict],
    user_input: str,
    history: list[str],
) -> str:
    units_text = "\n".join(
        f"  [{u['type']}, {u['manner']}] {u['content']}" for u in units
    )
    history_text = (
        "\n".join(f"  {line}" for line in history[-6:])
        or "  (start of conversation)"
    )
    return (
        f'The user just said: "{user_input}"\n\n'
        f"Points to make this turn:\n{units_text}\n\n"
        f"Prior exchange:\n{history_text}\n\n"
        "Deliver the points. Briefly acknowledge the user's argument "
        "if it is relevant to what you have to say."
    )


# ── Runtime factory ───────────────────────────────────────────────────────────


def build_persuasion_runtime() -> tuple[Runtime, StateStore, ContextService]:
    bb = Blackboard()
    state = StateStore(bb)
    context = ContextService(state, publish_changes_via=bb)

    _register_providers(context)
    specialists = _build_specialists(state, context)

    # worker_count=2: one slot for the model-gated speaker, one for fast
    # specialists (strategist, goal_tracker) so they can run in parallel
    # without blocking each other.
    rt = Runtime(specialists, worker_count=2, model_concurrency=1)
    rt.blackboard = bb
    rt.dispatcher._bb = bb
    return rt, state, context


def _register_providers(context: ContextService) -> None:
    context.register(
        context_urn("current_input"),
        passthrough(component_urn("input_receiver", "raw")),
    )
    context.register(
        context_urn("argument_queue"),
        passthrough(component_urn("strategist", "queue"), default=[]),
    )
    context.register(
        context_urn("user_interrupt"),
        passthrough(component_urn("user", "interrupt")),
    )
    context.register(
        context_urn("goal_achieved"),
        default_if_unset(component_urn("goal_tracker", "achieved"), default=False),
    )
    context.register(
        context_urn("persuasion_state"),
        default_if_unset(component_urn("goal_tracker", "state"), default="advocating"),
    )


def _build_specialists(
    state: StateStore, context: ContextService
) -> list[Specialist]:

    # ── input_bridge ──────────────────────────────────────────────────────────
    # Forwards panel input into the pipeline; appends to cumulative history.
    # Does NOT reset persuasion state — the conversation accumulates across turns.

    async def input_bridge_run(bb):
        text = state.read(component_urn("panel", "request"))
        if not text:
            return None
        history = list(state.read(component_urn("input_receiver", "history"), []))
        history.append(f"User: {text}")
        state.write("input_receiver", "history", history)
        # Clear any prior interrupt so the speaker isn't killed on the new turn.
        state.write("user", "interrupt", None)
        # Write raw last so strategist/speaker/goal_tracker fire after history is ready.
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

    # ── strategist ────────────────────────────────────────────────────────────
    # Releases one ArgumentUnit per activation onto the shared queue.
    # Reactive (priority=10): fires on each new user input before speaker.
    # Proactive (tick=8s): fires between turns — simulates async context
    # arriving (e.g., a memory retrieval or evidence lookup completing).
    # On second tick it enriches a2 in-place if still undelivered.
    # Responsive prioritisation: if user's input mentions a unit's responds_to
    # keyword, that unit jumps ahead in release order.

    async def strategist_run(bb):
        queue = list(state.read(component_urn("strategist", "queue"), []))
        released_ids: list[str] = list(
            state.read(component_urn("strategist", "released_ids"), [])
        )
        enrichment_applied: bool = state.read(
            component_urn("strategist", "enrichment_applied"), False
        )

        # Apply late enrichment to a2 if it is still in the queue.
        if not enrichment_applied and len(released_ids) >= 2:
            for unit in queue:
                if unit["id"] == "a2":
                    unit["content"] += _ENRICHMENT_FOR_A2
                    state.write("strategist", "queue", queue)
                    break
            state.write("strategist", "enrichment_applied", True)

        # Release the next unit; prefer responsive units when user raised
        # a matching keyword.
        released_set = set(released_ids)
        unreleased = [u for u in _SEQUENCE if u.id not in released_set]
        if not unreleased:
            return None

        user_input = state.read(component_urn("input_receiver", "raw"), "").lower()
        responsive = [
            u for u in unreleased
            if u.responds_to and u.responds_to in user_input
        ]
        next_unit = responsive[0] if responsive else unreleased[0]

        queue.append(next_unit.to_dict())
        released_ids.append(next_unit.id)
        state.write("strategist", "queue", queue)
        state.write("strategist", "released_ids", released_ids)
        return None

    strategist = Specialist(
        name="strategist",
        watches=[component_urn("input_receiver", "raw")],
        priority=10,
        needs_model=False,
        tick_seconds=8.0,
        run=strategist_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    # ── speaker ───────────────────────────────────────────────────────────────
    # Voices undelivered ArgumentUnits via real LLM. Fires on each new user
    # input — not on queue additions (turn-taking: speaker responds, not
    # initiates). Delivers up to 2 units per turn; stays silent if queue
    # has nothing new. Falls back to a bracketed message if LLM is unreachable.

    async def speaker_run(bb):
        user_input = state.read(component_urn("input_receiver", "raw"), "")
        if not user_input:
            return None

        queue = list(state.read(component_urn("strategist", "queue"), []))
        delivered: set[str] = set(
            state.read(component_urn("speaker", "delivered_ids"), [])
        )
        pending = [u for u in queue if u["id"] not in delivered]

        if not pending:
            return None

        history = list(state.read(component_urn("input_receiver", "history"), []))
        units_to_deliver = pending[:2]
        prompt = _build_speaker_prompt(units_to_deliver, user_input, history)

        # Open a placeholder entry in spoken_log so the Output section starts
        # rendering immediately. Each chunk updates that entry in place — the
        # SSE stream pushes every write to the panel, so the user sees text
        # building up word by word.
        spoken_log = list(state.read(component_urn("speaker", "spoken_log"), []))
        spoken_log.append("")
        state.write("speaker", "spoken_log", list(spoken_log))

        buffer = ""
        interrupted = False
        try:
            async for chunk in generate_streaming(_SPEAKER_SYSTEM, prompt):
                if state.read(component_urn("user", "interrupt")):
                    interrupted = True
                    break
                buffer += chunk
                spoken_log[-1] = buffer
                state.write("speaker", "spoken_log", list(spoken_log))
        except Exception as exc:
            buffer = buffer or f"[speaker unavailable — {exc}]"

        if interrupted:
            buffer = (buffer or "…") + " [—]"

        if buffer:
            spoken_log[-1] = buffer
            state.write("speaker", "spoken_log", list(spoken_log))

            new_delivered = list(delivered | {u["id"] for u in units_to_deliver})
            state.write("speaker", "delivered_ids", new_delivered)

            history.append(f"Speaker: {buffer}")
            state.write("input_receiver", "history", history)
        else:
            # Nothing generated — remove the placeholder.
            spoken_log.pop()
            state.write("speaker", "spoken_log", list(spoken_log))

        return None

    speaker = Specialist(
        name="speaker",
        watches=[component_urn("input_receiver", "raw")],
        priority=20,
        needs_model=True,
        run=speaker_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    # ── goal_tracker ──────────────────────────────────────────────────────────
    # Simple token-match agreement detector. Writes goal signal on first hit.
    # Latches — once achieved, ignores further input.

    async def goal_tracker_run(bb):
        if state.read(component_urn("goal_tracker", "achieved"), False):
            return None
        user_input = state.read(component_urn("input_receiver", "raw"), "").lower()
        tokens = set(user_input.replace(",", " ").replace(".", " ").split())
        if tokens & _AGREEMENT_TOKENS:
            state.write("goal_tracker", "achieved", True)
            state.write("goal_tracker", "state", "persuaded")
        return None

    goal_tracker = Specialist(
        name="goal_tracker",
        watches=[component_urn("input_receiver", "raw")],
        priority=30,
        needs_model=False,
        run=goal_tracker_run,
        should_activate=lambda bb, ch: bool(ch.new_value),
    )

    return [input_bridge, strategist, speaker, goal_tracker]
