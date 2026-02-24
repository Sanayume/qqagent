"""Embedding 向量生成 - 调用 OpenAI 兼容 API"""

import os
import httpx


def get_embedding(text: str) -> list[float]:
    """获取文本的 embedding 向量"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    resp = httpx.post(
        f"{base_url}/embeddings",
        json={"input": text[:8000], "model": model},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]
