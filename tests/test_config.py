import os
import pytest
import ponder.config as config_module
from ponder.config import Config, get_config


@pytest.fixture(autouse=True)
def reset_config_singleton():
    config_module._config = None
    yield
    config_module._config = None


def test_defaults():
    cfg = Config()
    assert cfg.redis_url == "redis://localhost:6379"
    assert cfg.qdrant_url == "http://localhost:6333"
    assert cfg.model_url == "http://localhost:8000"
    assert cfg.encoder_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.generative_model == "mistralai/Mistral-7B-Instruct-v0.3"
    assert cfg.memory_collection == "hippocampus"
    assert cfg.memory_top_k == 5
    assert cfg.model_max_tokens == 1024
    assert cfg.model_temperature == 0.7


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("PONDER_REDIS_URL", "redis://prod:6379")
    monkeypatch.setenv("PONDER_QDRANT_URL", "http://qdrant-prod:6333")
    monkeypatch.setenv("PONDER_MODEL_URL", "http://vllm:8000")
    monkeypatch.setenv("PONDER_MEMORY_TOP_K", "10")
    monkeypatch.setenv("PONDER_MODEL_MAX_TOKENS", "2048")
    monkeypatch.setenv("PONDER_MODEL_TEMPERATURE", "0.3")

    cfg = Config.from_env()
    assert cfg.redis_url == "redis://prod:6379"
    assert cfg.qdrant_url == "http://qdrant-prod:6333"
    assert cfg.model_url == "http://vllm:8000"
    assert cfg.memory_top_k == 10
    assert cfg.model_max_tokens == 2048
    assert cfg.model_temperature == 0.3


def test_get_config_returns_singleton():
    a = get_config()
    b = get_config()
    assert a is b


def test_get_config_respects_env(monkeypatch):
    monkeypatch.setenv("PONDER_REDIS_URL", "redis://singleton-test:6379")
    cfg = get_config()
    assert cfg.redis_url == "redis://singleton-test:6379"
