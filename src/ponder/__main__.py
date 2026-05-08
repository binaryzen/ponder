"""CLI entry point: ponder "some input" """

import sys

from ponder.audit import (
    current_parent_span_id,
    current_trace_id,
    emit_pipeline_event,
    new_id,
)
from ponder.blackboard import initial_state
from ponder.graph.pipeline import build_pipeline
from ponder.regions.hippocampus import store_memory

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


def run(raw_input: str, operator_context: str = "", rules_of_engagement: str = "") -> str:
    # One trace_id per turn. Every audit event in this turn carries it.
    current_trace_id.set(new_id())

    # Turn-start event becomes the parent for everything else this turn.
    turn_span = emit_pipeline_event("turn_start", payload={"raw_input": raw_input})
    current_parent_span_id.set(turn_span)

    state = initial_state(raw_input, operator_context, rules_of_engagement)
    result = _get_pipeline().invoke(state)

    store_memory(
        text=f"Q: {raw_input}\nA: {result['response_draft']}",
        metadata={"input_type": result["input_type"]},
    )
    emit_pipeline_event("memory_stored", region="hippocampus")

    emit_pipeline_event(
        "turn_end",
        payload={
            "input_type": result["input_type"],
            "response_length": len(result["response_draft"]),
        },
    )

    return result["response_draft"]


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: ponder <input>", file=sys.stderr)
        sys.exit(1)

    raw_input = " ".join(sys.argv[1:])
    response = run(raw_input)
    print(response)


if __name__ == "__main__":
    main()
