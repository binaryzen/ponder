import os
from pydantic import BaseModel


class Config(BaseModel):
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    model_url: str = "http://localhost:8000"  # vLLM OpenAI-compatible endpoint
    encoder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    generative_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    memory_collection: str = "hippocampus"
    memory_top_k: int = 5
    model_max_tokens: int = 1024
    model_temperature: float = 0.7
    prompts_dir: str = os.path.join(os.path.dirname(__file__), "..", "prompts")

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            redis_url=os.getenv("PONDER_REDIS_URL", "redis://localhost:6379"),
            qdrant_url=os.getenv("PONDER_QDRANT_URL", "http://localhost:6333"),
            model_url=os.getenv("PONDER_MODEL_URL", "http://localhost:8000"),
            encoder_model=os.getenv("PONDER_ENCODER_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            generative_model=os.getenv("PONDER_GENERATIVE_MODEL", "mistralai/Mistral-7B-Instruct-v0.3"),
            memory_collection=os.getenv("PONDER_MEMORY_COLLECTION", "hippocampus"),
            memory_top_k=int(os.getenv("PONDER_MEMORY_TOP_K", "5")),
            model_max_tokens=int(os.getenv("PONDER_MODEL_MAX_TOKENS", "1024")),
            model_temperature=float(os.getenv("PONDER_MODEL_TEMPERATURE", "0.7")),
            prompts_dir=os.getenv(
                "PONDER_PROMPTS_DIR",
                os.path.join(os.path.dirname(__file__), "..", "prompts"),
            ),
        )


_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
