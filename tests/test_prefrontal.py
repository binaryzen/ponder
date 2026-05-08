import pytest
from unittest.mock import patch, MagicMock
import ponder.regions.prefrontal as prefrontal_module
from ponder.blackboard import initial_state, BlackboardState

# Template with the same placeholders as the real one — minimal for testing.
FAKE_TEMPLATE = (
    "input_type={input_type} "
    "memories={retrieved_memories} "
    "ctx={operator_context} "
    "roe={rules_of_engagement}"
)


@pytest.fixture(autouse=True)
def reset_template():
    original = prefrontal_module._template
    prefrontal_module._template = None
    yield
    prefrontal_module._template = original


def test_returns_task_plan_key():
    with patch("ponder.regions.prefrontal._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.prefrontal.generate", return_value="GOAL: answer\nMUST-CONVEY: facts\nSUBTASKS: one"):
        state = initial_state("hello")
        result = prefrontal_module.prefrontal_node(state)

    assert "task_plan" in result
    assert list(result.keys()) == ["task_plan"]


def test_generate_receives_rendered_system_prompt():
    captured = {}

    def fake_generate(system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return "plan output"

    with patch("ponder.regions.prefrontal._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.prefrontal.generate", side_effect=fake_generate):
        state = initial_state("What time is it?", operator_context="Alice", rules_of_engagement="be brief")
        state["input_type"] = "question"
        state["retrieved_memories"] = "previous answer"
        prefrontal_module.prefrontal_node(state)

    assert "input_type=question" in captured["system"]
    assert "memories=previous answer" in captured["system"]
    assert "ctx=Alice" in captured["system"]
    assert "roe=be brief" in captured["system"]
    assert captured["user"] == "What time is it?"


def test_none_fields_rendered_as_none_string():
    """Empty string fields (defaults) should appear as 'None' in the prompt."""
    captured = {}

    def fake_generate(system_prompt, user_prompt):
        captured["system"] = system_prompt
        return "plan"

    with patch("ponder.regions.prefrontal._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.prefrontal.generate", side_effect=fake_generate):
        state = initial_state("x")  # all fields default to ""
        prefrontal_module.prefrontal_node(state)

    assert "memories=None" in captured["system"]
    assert "ctx=None" in captured["system"]
    assert "roe=None" in captured["system"]


def test_task_plan_is_generate_return_value():
    with patch("ponder.regions.prefrontal._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.prefrontal.generate", return_value="  trimmed plan  "):
        state = initial_state("x")
        result = prefrontal_module.prefrontal_node(state)

    assert result["task_plan"] == "  trimmed plan  "
