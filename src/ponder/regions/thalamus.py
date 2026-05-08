"""Thalamus — classifies input type. Encoder model, no GPU required."""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

from ponder.blackboard import BlackboardState
from ponder.config import get_config

_model: SentenceTransformer | None = None

# Representative phrases per class; averaged into class prototypes at load time.
_LABEL_EXAMPLES: dict[str, list[str]] = {
    "question": [
        "What is X?",
        "How does this work?",
        "Can you explain?",
        "Why did this happen?",
        "When was it made?",
    ],
    "command": [
        "Do this for me.",
        "Please generate a list.",
        "Write a summary.",
        "Create a plan.",
        "Run the analysis.",
    ],
    "statement": [
        "I think this is correct.",
        "Here is some information.",
        "The result was 42.",
        "It happened yesterday.",
        "This is my observation.",
    ],
    "greeting": [
        "Hello!",
        "Hi there.",
        "Good morning.",
        "Hey, how are you?",
        "Nice to meet you.",
    ],
    "clarification": [
        "I meant something different.",
        "Let me rephrase that.",
        "Actually, I was asking about...",
        "To clarify, I want...",
        "That's not quite what I meant.",
    ],
}


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(get_config().encoder_model)
    return _model


def _build_prototypes(model: SentenceTransformer) -> tuple[list[str], np.ndarray]:
    labels = list(_LABEL_EXAMPLES.keys())
    prototypes = []
    for label in labels:
        embeddings = model.encode(_LABEL_EXAMPLES[label], convert_to_numpy=True)
        prototypes.append(embeddings.mean(axis=0))
    return labels, np.stack(prototypes)


_prototypes: tuple[list[str], np.ndarray] | None = None


def _get_prototypes() -> tuple[list[str], np.ndarray]:
    global _prototypes
    if _prototypes is None:
        _prototypes = _build_prototypes(_get_model())
    return _prototypes


def thalamus_node(state: BlackboardState) -> dict:
    model = _get_model()
    labels, prototypes = _get_prototypes()

    input_vec = model.encode([state["raw_input"]], convert_to_numpy=True)[0]

    # Cosine similarity
    norms = np.linalg.norm(prototypes, axis=1) * np.linalg.norm(input_vec)
    scores = prototypes @ input_vec / np.maximum(norms, 1e-9)
    input_type = labels[int(np.argmax(scores))]

    return {"input_type": input_type}
