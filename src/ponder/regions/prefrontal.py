"""Prefrontal Cortex — goal decomposition and task planning."""

import os
from ponder.blackboard import BlackboardState
from ponder.config import get_config
from ponder.model_client import generate

_template: str | None = None


def _get_template() -> str:
    global _template
    if _template is None:
        path = os.path.join(get_config().prompts_dir, "prefrontal_v1.txt")
        with open(path) as f:
            _template = f.read()
    return _template


def prefrontal_node(state: BlackboardState) -> dict:
    template = _get_template()

    system_prompt = template.format(
        input_type=state["input_type"],
        retrieved_memories=state["retrieved_memories"] or "None",
        operator_context=state["operator_context"] or "None",
        rules_of_engagement=state["rules_of_engagement"] or "None",
    )

    task_plan = generate(system_prompt=system_prompt, user_prompt=state["raw_input"])
    return {"task_plan": task_plan}
