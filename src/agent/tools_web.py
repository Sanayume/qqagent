"""Web search tool backed by Brave Search API."""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from src.utils.config import load_settings


@tool
def web_search(query: str, count: int = 5) -> str:
    """Search the web for fresh information."""
    settings = load_settings()
    api_key = settings.integrations.brave_search_api_key
    if not api_key:
        return "??: ??? Brave Search API Key"

    count = max(1, min(10, count))

    try:
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"????: {e}"

    results = data.get("web", {}).get("results", [])
    if not results:
        return f"???????{query}????"

    lines = [f"???{query}?????\n"]
    for i, result in enumerate(results[:count], 1):
        title = result.get("title", "")
        url = result.get("url", "")
        desc = result.get("description", "")
        lines.append(f"{i}. {title}\n   {url}\n   {desc}\n")

    return "\n".join(lines)
