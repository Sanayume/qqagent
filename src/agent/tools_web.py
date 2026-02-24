"""Web 搜索工具 - Brave Search API"""

import os
import httpx
from langchain_core.tools import tool


@tool
def web_search(query: str, count: int = 5) -> str:
    """搜索互联网获取最新信息。当用户询问新闻、实时信息、或你不确定的事实时使用。

    Args:
        query: 搜索关键词
        count: 返回结果数量（1-10）

    Returns:
        格式化的搜索结果
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
    if not api_key:
        return "错误: 未配置 BRAVE_SEARCH_API_KEY"

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
        return f"搜索失败: {e}"

    results = data.get("web", {}).get("results", [])
    if not results:
        return f"没有找到关于「{query}」的结果"

    lines = [f"搜索「{query}」的结果：\n"]
    for i, r in enumerate(results[:count], 1):
        title = r.get("title", "")
        url = r.get("url", "")
        desc = r.get("description", "")
        lines.append(f"{i}. {title}\n   {url}\n   {desc}\n")

    return "\n".join(lines)
