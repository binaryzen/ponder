from ponder.blackboard import BlackboardState, initial_state


def test_initial_state_required_keys():
    state = initial_state("hello")
    expected_keys = {
        "raw_input",
        "input_type",
        "urgency_score",
        "retrieved_memories",
        "task_plan",
        "semantic_parse",
        "active_routine",
        "operator_context",
        "rules_of_engagement",
        "response_draft",
        "goal_achieved",
    }
    assert set(state.keys()) == expected_keys


def test_initial_state_raw_input():
    state = initial_state("test input")
    assert state["raw_input"] == "test input"


def test_initial_state_string_fields_empty():
    state = initial_state("x")
    for field in ("input_type", "retrieved_memories", "task_plan", "semantic_parse",
                  "active_routine", "operator_context", "rules_of_engagement", "response_draft"):
        assert state[field] == "", f"{field} should default to empty string"


def test_initial_state_numeric_defaults():
    state = initial_state("x")
    assert state["urgency_score"] == 0.0
    assert state["goal_achieved"] is False


def test_initial_state_operator_context():
    state = initial_state("x", operator_context="Alice", rules_of_engagement="be concise")
    assert state["operator_context"] == "Alice"
    assert state["rules_of_engagement"] == "be concise"


def test_initial_state_is_typed_dict():
    state = initial_state("x")
    assert isinstance(state, dict)
