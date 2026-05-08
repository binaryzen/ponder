"""
Pipeline integration tests. All region nodes are replaced with thin stubs
that record invocation and return controlled state deltas. No models, no
network, no Redis, no Qdrant.

The audit emitter is patched globally for these tests so the audit_wrap
instrumentation in build_pipeline() does not write to a real Redis stream.
"""

import pytest
from unittest.mock import patch
from ponder.blackboard import initial_state


@pytest.fixture(autouse=True)
def silence_audit_emit():
    """Prevent audit_wrap from hitting Redis during pipeline tests."""
    with patch("ponder.audit.instrumentation.emit"):
        yield

# ── Stubs ──────────────────────────────────────────────────────────────────

INVOCATION_LOG: list[str] = []


def stub_thalamus(state):
    INVOCATION_LOG.append("thalamus")
    return {"input_type": "question"}


def stub_hippocampus(state):
    INVOCATION_LOG.append("hippocampus")
    return {"retrieved_memories": "stub memory"}


def stub_prefrontal(state):
    INVOCATION_LOG.append("prefrontal")
    return {"task_plan": "stub plan"}


def stub_broca(state):
    INVOCATION_LOG.append("broca")
    return {"response_draft": "stub response", "goal_achieved": True}


@pytest.fixture(autouse=True)
def reset_log():
    INVOCATION_LOG.clear()
    yield


# ── Tests ──────────────────────────────────────────────────────────────────

@patch("ponder.graph.pipeline.thalamus_node", side_effect=stub_thalamus)
@patch("ponder.graph.pipeline.hippocampus_node", side_effect=stub_hippocampus)
@patch("ponder.graph.pipeline.prefrontal_node", side_effect=stub_prefrontal)
@patch("ponder.graph.pipeline.broca_node", side_effect=stub_broca)
def test_pipeline_builds_and_runs(mock_broca, mock_prefrontal, mock_hippo, mock_thalamus):
    from ponder.graph.pipeline import build_pipeline

    pipeline = build_pipeline()
    state = initial_state("test input")
    result = pipeline.invoke(state)

    assert result["response_draft"] == "stub response"
    assert result["goal_achieved"] is True


@patch("ponder.graph.pipeline.thalamus_node", side_effect=stub_thalamus)
@patch("ponder.graph.pipeline.hippocampus_node", side_effect=stub_hippocampus)
@patch("ponder.graph.pipeline.prefrontal_node", side_effect=stub_prefrontal)
@patch("ponder.graph.pipeline.broca_node", side_effect=stub_broca)
def test_nodes_execute_in_declared_order(mock_broca, mock_prefrontal, mock_hippo, mock_thalamus):
    from ponder.graph.pipeline import build_pipeline

    pipeline = build_pipeline()
    pipeline.invoke(initial_state("x"))

    assert INVOCATION_LOG == ["thalamus", "hippocampus", "prefrontal", "broca"]


@patch("ponder.graph.pipeline.thalamus_node", side_effect=stub_thalamus)
@patch("ponder.graph.pipeline.hippocampus_node", side_effect=stub_hippocampus)
@patch("ponder.graph.pipeline.prefrontal_node", side_effect=stub_prefrontal)
@patch("ponder.graph.pipeline.broca_node", side_effect=stub_broca)
def test_state_propagates_through_pipeline(mock_broca, mock_prefrontal, mock_hippo, mock_thalamus):
    """Verify each node's output is visible to subsequent nodes."""
    received: dict[str, dict] = {}

    def capturing_hippocampus(state):
        received["hippocampus_saw"] = dict(state)
        return stub_hippocampus(state)

    def capturing_prefrontal(state):
        received["prefrontal_saw"] = dict(state)
        return stub_prefrontal(state)

    def capturing_broca(state):
        received["broca_saw"] = dict(state)
        return stub_broca(state)

    mock_hippo.side_effect = capturing_hippocampus
    mock_prefrontal.side_effect = capturing_prefrontal
    mock_broca.side_effect = capturing_broca

    from ponder.graph.pipeline import build_pipeline
    pipeline = build_pipeline()
    pipeline.invoke(initial_state("propagation test"))

    # Hippocampus sees Thalamus output
    assert received["hippocampus_saw"]["input_type"] == "question"

    # Prefrontal sees both Thalamus and Hippocampus output
    assert received["prefrontal_saw"]["input_type"] == "question"
    assert received["prefrontal_saw"]["retrieved_memories"] == "stub memory"

    # Broca sees full upstream state
    assert received["broca_saw"]["input_type"] == "question"
    assert received["broca_saw"]["retrieved_memories"] == "stub memory"
    assert received["broca_saw"]["task_plan"] == "stub plan"


@patch("ponder.graph.pipeline.thalamus_node", side_effect=stub_thalamus)
@patch("ponder.graph.pipeline.hippocampus_node", side_effect=stub_hippocampus)
@patch("ponder.graph.pipeline.prefrontal_node", side_effect=stub_prefrontal)
@patch("ponder.graph.pipeline.broca_node", side_effect=stub_broca)
def test_raw_input_preserved_throughout(mock_broca, mock_prefrontal, mock_hippo, mock_thalamus):
    from ponder.graph.pipeline import build_pipeline

    pipeline = build_pipeline()
    result = pipeline.invoke(initial_state("original question"))

    assert result["raw_input"] == "original question"


@patch("ponder.graph.pipeline.thalamus_node", side_effect=stub_thalamus)
@patch("ponder.graph.pipeline.hippocampus_node", side_effect=stub_hippocampus)
@patch("ponder.graph.pipeline.prefrontal_node", side_effect=stub_prefrontal)
@patch("ponder.graph.pipeline.broca_node", side_effect=stub_broca)
def test_each_node_called_exactly_once(mock_broca, mock_prefrontal, mock_hippo, mock_thalamus):
    from ponder.graph.pipeline import build_pipeline

    pipeline = build_pipeline()
    pipeline.invoke(initial_state("x"))

    mock_thalamus.assert_called_once()
    mock_hippo.assert_called_once()
    mock_prefrontal.assert_called_once()
    mock_broca.assert_called_once()
