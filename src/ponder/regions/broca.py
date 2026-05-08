"""Broca — voice of the system. Produces the final response."""

import os
from ponder.blackboard import BlackboardState
from ponder.config import get_config
from ponder.model_client import generate

_template: str | None = None


def _get_template() -> str:
    global _template
    if _template is None:
        path = os.path.join(get_config().prompts_dir, "broca_v1.txt")
        with open(path) as f:
            _template = f.read()
    return _template


def broca_node(state: BlackboardState) -> dict:
    template = _get_template()

    system_prompt = template.format(
        input_type=state["input_type"],
        retrieved_memories=state["retrieved_memories"] or "None",
        task_plan=state["task_plan"] or "None",
        operator_context=state["operator_context"] or "None",
        rules_of_engagement=state["rules_of_engagement"] or "None",
    )

    response = generate(system_prompt=system_prompt, user_prompt=state["raw_input"])
    return {"response_draft": response, "goal_achieved": True}
