"""Shared HTTP client for OpenAI-compatible model server (vLLM / Ollama)."""

from __future__ import annotations

import json

import httpx
from ponder.config import get_config


def generate(system_prompt: str, user_prompt: str) -> str:
    cfg = get_config()
    payload = {
        "model": cfg.generative_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": cfg.model_max_tokens,
        "temperature": cfg.model_temperature,
    }
    response = httpx.post(
        f"{cfg.model_url}/v1/chat/completions",
        json=payload,
        timeout=300.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


async def generate_streaming(system_prompt: str, user_prompt: str):
    """Async generator yielding text chunks from a streaming completion.

    Follows the OpenAI SSE wire format (data: {...} lines, terminated by
    data: [DONE]). Compatible with Ollama and vLLM.

    The caller can break out of the async for loop at any time; Python will
    call aclose() on this generator, which closes the httpx connection and
    stops server-side generation.
    """
    cfg = get_config()
    payload = {
        "model": cfg.generative_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": cfg.model_max_tokens,
        "temperature": cfg.model_temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream(
            "POST",
            f"{cfg.model_url}/v1/chat/completions",
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    return
                try:
                    obj = json.loads(data)
                    content = obj["choices"][0]["delta"].get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
