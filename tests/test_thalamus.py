"""
Thalamus tests use controlled embedding geometry to validate classification logic
without loading a real model. We inject fake prototypes and a fake encoder.
"""

import numpy as np
import pytest
import ponder.regions.thalamus as thalamus_module
from ponder.blackboard import initial_state


LABELS = ["question", "command", "statement", "greeting", "clarification"]

# 5 orthogonal unit vectors — one per class. Cosine sim = 1.0 for exact match.
PROTOTYPES = np.eye(5)


@pytest.fixture(autouse=True)
def reset_thalamus_globals():
    original_model = thalamus_module._model
    original_prototypes = thalamus_module._prototypes
    yield
    thalamus_module._model = original_model
    thalamus_module._prototypes = original_prototypes


def make_mock_model(input_vec: np.ndarray):
    """Return a mock encoder whose encode() always returns input_vec."""
    from unittest.mock import MagicMock
    m = MagicMock()
    m.encode.return_value = np.array([input_vec])
    return m


@pytest.mark.parametrize("label_index,label_name", enumerate(LABELS))
def test_classifies_each_label(label_index, label_name):
    """Input aligned with prototype[i] should produce labels[i]."""
    thalamus_module._prototypes = (LABELS, PROTOTYPES)
    thalamus_module._model = make_mock_model(PROTOTYPES[label_index])

    state = initial_state("irrelevant — model is mocked")
    result = thalamus_module.thalamus_node(state)

    assert result == {"input_type": label_name}


def test_returns_dict_with_input_type_key():
    thalamus_module._prototypes = (LABELS, PROTOTYPES)
    thalamus_module._model = make_mock_model(PROTOTYPES[0])

    state = initial_state("x")
    result = thalamus_module.thalamus_node(state)

    assert "input_type" in result
    assert isinstance(result["input_type"], str)
    assert result["input_type"] in LABELS


def test_nearest_prototype_wins():
    """Input slightly closer to 'command' (index 1) than 'question' (index 0)."""
    thalamus_module._prototypes = (LABELS, PROTOTYPES)

    # Halfway between question and command, slightly biased toward command
    vec = np.zeros(5)
    vec[0] = 0.4   # question component
    vec[1] = 0.6   # command component
    thalamus_module._model = make_mock_model(vec)

    state = initial_state("x")
    result = thalamus_module.thalamus_node(state)
    assert result["input_type"] == "command"


def test_does_not_write_other_state_keys():
    thalamus_module._prototypes = (LABELS, PROTOTYPES)
    thalamus_module._model = make_mock_model(PROTOTYPES[0])

    state = initial_state("x")
    result = thalamus_module.thalamus_node(state)

    assert list(result.keys()) == ["input_type"]
