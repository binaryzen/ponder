from typing import Optional
from typing_extensions import TypedDict


class BlackboardState(TypedDict):
    """Full cognitive state for one turn. All regions read from and write to this."""

    # Input
    raw_input: str

    # Tier 1 signals
    input_type: str           # Thalamus: question | command | statement | greeting | clarification
    urgency_score: float      # Amygdala: 0.0–1.0 (Phase 2)

    # Tier 2 signals
    retrieved_memories: str   # Hippocampus: formatted context string
    task_plan: str            # Prefrontal: decomposed goal + must-convey concepts
    semantic_parse: str       # Wernicke (Phase 2)
    active_routine: str       # Basal Ganglia (Phase 2); empty string = no match

    # Operator layer (populated externally; read by all regions)
    operator_context: str
    rules_of_engagement: str

    # Output
    response_draft: str       # Broca's current output

    # Control
    goal_achieved: bool


def initial_state(raw_input: str, operator_context: str = "", rules_of_engagement: str = "") -> BlackboardState:
    return BlackboardState(
        raw_input=raw_input,
        input_type="",
        urgency_score=0.0,
        retrieved_memories="",
        task_plan="",
        semantic_parse="",
        active_routine="",
        operator_context=operator_context,
        rules_of_engagement=rules_of_engagement,
        response_draft="",
        goal_achieved=False,
    )
