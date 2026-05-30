"""Embedding vector generation via OpenAI-compatible API."""

from __future__ import annotations

import httpx

from src.utils.config import load_settings


def get_embedding(text: str) -> list[float]:
    settings = load_settings()
    api_key = settings.embeddings.api_key or settings.llm.openai_api_key
    base_url = (settings.embeddings.api_base or settings.llm.openai_api_base or "https://api.openai.com/v1").rstrip("/")
    model = settings.embeddings.model

    resp = httpx.post(
        f"{base_url}/embeddings",
        json={"input": text[:8000], "model": model},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]
