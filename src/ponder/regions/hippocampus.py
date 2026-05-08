"""Hippocampus — episodic memory retrieval via Qdrant vector store."""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

from ponder.blackboard import BlackboardState
from ponder.config import get_config

_model: SentenceTransformer | None = None
_client: QdrantClient | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(get_config().encoder_model)
    return _model


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        cfg = get_config()
        _client = QdrantClient(url=cfg.qdrant_url)
        _ensure_collection(_client, cfg.memory_collection, _get_model())
    return _client


def _ensure_collection(client: QdrantClient, name: str, model: SentenceTransformer) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        dim = model.get_embedding_dimension()
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def hippocampus_node(state: BlackboardState) -> dict:
    cfg = get_config()
    client = _get_client()
    model = _get_model()

    query_vec = model.encode([state["raw_input"]], convert_to_numpy=True)[0].tolist()

    response = client.query_points(
        collection_name=cfg.memory_collection,
        query=query_vec,
        limit=cfg.memory_top_k,
        with_payload=True,
    )
    results = response.points

    if not results:
        return {"retrieved_memories": ""}

    memory_lines = []
    for hit in results:
        payload = hit.payload or {}
        text = payload.get("text", "")
        score = round(hit.score, 3)
        if text:
            memory_lines.append(f"[relevance {score}] {text}")

    return {"retrieved_memories": "\n".join(memory_lines)}


def store_memory(text: str, metadata: dict | None = None) -> None:
    """Add a memory to the vector store. Called after each completed turn."""
    import uuid

    client = _get_client()
    model = _get_model()
    cfg = get_config()

    vec = model.encode([text], convert_to_numpy=True)[0].tolist()
    payload = {"text": text, **(metadata or {})}
    client.upsert(
        collection_name=cfg.memory_collection,
        points=[PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload)],
    )
