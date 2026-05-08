import pytest
from unittest.mock import patch
import ponder.regions.broca as broca_module
from ponder.blackboard import initial_state

FAKE_TEMPLATE = (
    "input_type={input_type} "
    "memories={retrieved_memories} "
    "plan={task_plan} "
    "ctx={operator_context} "
    "roe={rules_of_engagement}"
)


@pytest.fixture(autouse=True)
def reset_template():
    original = broca_module._template
    broca_module._template = None
    yield
    broca_module._template = original


def test_returns_response_draft_and_goal_achieved():
    with patch("ponder.regions.broca._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.broca.generate", return_value="Hello, world."):
        state = initial_state("hi")
        result = broca_module.broca_node(state)

    assert set(result.keys()) == {"response_draft", "goal_achieved"}


def test_goal_achieved_always_true():
    with patch("ponder.regions.broca._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.broca.generate", return_value="response"):
        state = initial_state("x")
        result = broca_module.broca_node(state)

    assert result["goal_achieved"] is True


def test_response_draft_is_generate_return_value():
    with patch("ponder.regions.broca._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.broca.generate", return_value="The answer is 42."):
        state = initial_state("x")
        result = broca_module.broca_node(state)

    assert result["response_draft"] == "The answer is 42."


def test_generate_receives_full_cognitive_state():
    captured = {}

    def fake_generate(system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return "response"

    with patch("ponder.regions.broca._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.broca.generate", side_effect=fake_generate):
        state = initial_state("What is 2+2?", operator_context="Bob", rules_of_engagement="be exact")
        state["input_type"] = "question"
        state["retrieved_memories"] = "math facts"
        state["task_plan"] = "compute sum"
        broca_module.broca_node(state)

    assert "input_type=question" in captured["system"]
    assert "memories=math facts" in captured["system"]
    assert "plan=compute sum" in captured["system"]
    assert "ctx=Bob" in captured["system"]
    assert "roe=be exact" in captured["system"]
    assert captured["user"] == "What is 2+2?"


def test_empty_defaults_render_as_none_string():
    captured = {}

    def fake_generate(system_prompt, user_prompt):
        captured["system"] = system_prompt
        return "r"

    with patch("ponder.regions.broca._get_template", return_value=FAKE_TEMPLATE), \
         patch("ponder.regions.broca.generate", side_effect=fake_generate):
        state = initial_state("x")
        broca_module.broca_node(state)

    assert "memories=None" in captured["system"]
    assert "plan=None" in captured["system"]
    assert "ctx=None" in captured["system"]
