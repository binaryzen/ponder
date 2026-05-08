import pytest
from unittest.mock import MagicMock, call
import ponder.regions.hippocampus as hippo_module
from ponder.blackboard import initial_state


@pytest.fixture(autouse=True)
def reset_hippo_globals():
    original_model = hippo_module._model
    original_client = hippo_module._client
    yield
    hippo_module._model = original_model
    hippo_module._client = original_client


def make_mock_model(vec=None):
    import numpy as np
    m = MagicMock()
    m.encode.return_value = np.array([vec or [0.1, 0.2, 0.3]])
    return m


def make_scored_hit(text: str, score: float) -> MagicMock:
    hit = MagicMock()
    hit.score = score
    hit.payload = {"text": text}
    return hit


def make_mock_client(points: list) -> MagicMock:
    """Build a mock QdrantClient where query_points() returns a response with the given .points."""
    mock_client = MagicMock()
    response = MagicMock()
    response.points = points
    mock_client.query_points.return_value = response
    return mock_client


def test_empty_results_returns_empty_string():
    hippo_module._client = make_mock_client([])
    hippo_module._model = make_mock_model()

    state = initial_state("anything")
    result = hippo_module.hippocampus_node(state)

    assert result == {"retrieved_memories": ""}


def test_single_result_formatted_correctly():
    hippo_module._client = make_mock_client([make_scored_hit("Paris is the capital of France", 0.92)])
    hippo_module._model = make_mock_model()

    state = initial_state("What is the capital of France?")
    result = hippo_module.hippocampus_node(state)

    assert result["retrieved_memories"] == "[relevance 0.92] Paris is the capital of France"


def test_multiple_results_joined_by_newline():
    hits = [
        make_scored_hit("Memory A", 0.95),
        make_scored_hit("Memory B", 0.80),
        make_scored_hit("Memory C", 0.71),
    ]
    hippo_module._client = make_mock_client(hits)
    hippo_module._model = make_mock_model()

    state = initial_state("x")
    result = hippo_module.hippocampus_node(state)

    lines = result["retrieved_memories"].split("\n")
    assert len(lines) == 3
    assert lines[0] == "[relevance 0.95] Memory A"
    assert lines[1] == "[relevance 0.8] Memory B"
    assert lines[2] == "[relevance 0.71] Memory C"


def test_hit_with_empty_text_is_skipped():
    hits = [
        make_scored_hit("", 0.99),
        make_scored_hit("Real memory", 0.80),
    ]
    hippo_module._client = make_mock_client(hits)
    hippo_module._model = make_mock_model()

    state = initial_state("x")
    result = hippo_module.hippocampus_node(state)

    assert "Real memory" in result["retrieved_memories"]
    assert result["retrieved_memories"].count("\n") == 0  # only one valid hit


def test_returns_only_retrieved_memories_key():
    hippo_module._client = make_mock_client([])
    hippo_module._model = make_mock_model()

    state = initial_state("x")
    result = hippo_module.hippocampus_node(state)

    assert list(result.keys()) == ["retrieved_memories"]


def test_store_memory_calls_upsert():
    import numpy as np
    mock_client = MagicMock()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3]])
    hippo_module._client = mock_client
    hippo_module._model = mock_model

    hippo_module.store_memory("some text", metadata={"input_type": "question"})

    assert mock_client.upsert.called
    call_kwargs = mock_client.upsert.call_args
    points = call_kwargs.kwargs["points"] if call_kwargs.kwargs else call_kwargs[1]["points"]
    assert len(points) == 1
    assert points[0].payload["text"] == "some text"
    assert points[0].payload["input_type"] == "question"
