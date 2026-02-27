"""
Crawl4AI 核心封装层
封装 crawl4ai 的各类爬取能力，提供干净的异步接口供 MCP Server 调用。
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
from contextlib import contextmanager
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from config import config


# ─────────────────────────────────────────────────────────────────────────────
# stdout 静音
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def _muted_stdout():
    """
    在爬取期间把 sys.stdout 重定向到 sys.stderr。
    crawl4ai 的进度日志（[FETCH] / [SCRAPE] / ⏱）会写到 stdout，
    而 MCP stdio transport 也监听同一个 stdout，混入非 JSON 内容会导致解析错误。
    MCP 的 write_stream 在 stdio_server() 建立时就已持有真实的 stdout fd，
    之后即使我们替换 sys.stdout 也不影响 JSON-RPC 响应的发送。
    """
    old = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _cache_mode() -> CacheMode:
    mapping = {
        "enabled": CacheMode.ENABLED,
        "bypass": CacheMode.BYPASS,
        "disabled": CacheMode.DISABLED,
    }
    return mapping.get(config.cache_mode.lower(), CacheMode.BYPASS)


def _build_browser_config() -> BrowserConfig:
    kwargs: dict[str, Any] = {
        "headless": config.headless,
        "verbose": False,
        "enable_stealth": config.stealth_mode,
    }
    if config.proxy:
        kwargs["proxy"] = config.proxy
    return BrowserConfig(**kwargs)


def _build_run_config(
    *,
    cache_mode: CacheMode | None = None,
    js_code: list[str] | None = None,
    wait_for: str | None = None,
    screenshot: bool = False,
    word_count_threshold: int = 10,
    use_prune_filter: bool = True,
    extraction_strategy=None,
) -> CrawlerRunConfig:
    """构建统一的爬取运行配置"""
    kwargs: dict[str, Any] = {
        "cache_mode": cache_mode or _cache_mode(),
        "word_count_threshold": word_count_threshold,
        "page_timeout": config.page_timeout * 1000,  # crawl4ai 用毫秒
        "navigate_timeout": config.page_timeout * 1000,
        "screenshot": screenshot,
    }

    if use_prune_filter:
        kwargs["markdown_generator"] = DefaultMarkdownGenerator(
            content_filter=PruningContentFilter(
                threshold=config.prune_threshold,
                threshold_type="fixed",
                min_word_threshold=config.min_word_threshold,
            )
        )

    if js_code:
        kwargs["js_code"] = js_code
    if wait_for:
        kwargs["wait_for"] = wait_for
    if extraction_strategy:
        kwargs["extraction_strategy"] = extraction_strategy

    return CrawlerRunConfig(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# 核心爬取方法
# ─────────────────────────────────────────────────────────────────────────────

async def crawl_page(
    url: str,
    *,
    js_code: str | None = None,
    wait_for: str | None = None,
    use_prune_filter: bool = True,
    include_links: bool = False,
    include_images: bool = False,
) -> dict[str, Any]:
    """
    单页爬取，返回干净的 Markdown + 元数据。
    内置 Cloudflare 挑战页检测：若首次抓取命中 CF "Just a moment" 页，
    自动等待并重试一次。

    Returns:
        {
            "url": ...,
            "title": ...,
            "markdown": ...,       # fit_markdown（精简后）
            "raw_markdown": ...,   # 原始 Markdown（可选）
            "links": [...],        # 页面链接（include_links=True 时）
            "images": [...],       # 图片列表（include_images=True 时）
            "success": bool,
            "error": str | None,
        }
    """
    browser_config = _build_browser_config()
    run_config = _build_run_config(
        js_code=[js_code] if js_code else None,
        wait_for=wait_for,
        use_prune_filter=use_prune_filter,
    )

    with _muted_stdout():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

            # ── Cloudflare 挑战页检测与重试 ──────────────────────
            title = (result.metadata or {}).get("title", "") if getattr(result, "metadata", None) else ""
            md_text = ""
            if result.success and result.markdown:
                md_text = result.markdown.fit_markdown or result.markdown.raw_markdown or ""

            cf_detected = (
                "just a moment" in title.lower()
                or (result.success and len(md_text.strip()) == 0)
            )

            if cf_detected:
                # 等待 Cloudflare 挑战完成后重试（在同一个浏览器会话中）
                cf_wait_js = """
                await new Promise(r => {
                    const check = () => {
                        if (!document.title.toLowerCase().includes('just a moment')) {
                            r();
                        } else {
                            setTimeout(check, 1000);
                        }
                    };
                    setTimeout(check, 3000);
                });
                """
                retry_config = _build_run_config(
                    js_code=[cf_wait_js],
                    wait_for="js:() => !document.title.toLowerCase().includes('just a moment')",
                    use_prune_filter=use_prune_filter,
                )
                result = await crawler.arun(url=url, config=retry_config)

    output: dict[str, Any] = {
        "url": url,
        "title": getattr(result, "metadata", {}).get("title", "") if result.metadata else "",
        "success": result.success,
        "error": result.error_message if not result.success else None,
    }

    if result.success:
        md = result.markdown
        if md:
            output["markdown"] = md.fit_markdown or md.raw_markdown or ""
        else:
            output["markdown"] = ""

        if include_links and result.links:
            internal = result.links.get("internal", [])
            external = result.links.get("external", [])
            output["links"] = {
                "internal": [lk.get("href", "") for lk in internal[:30]],
                "external": [lk.get("href", "") for lk in external[:20]],
            }

        if include_images and result.media:
            images = result.media.get("images", [])
            output["images"] = [
                {"src": img.get("src", ""), "alt": img.get("alt", "")}
                for img in images[:20]
            ]

    return output


async def deep_crawl(
    url: str,
    *,
    strategy: str = "bfs",
    max_pages: int = 10,
    max_depth: int = 3,
    keyword_filter: str | None = None,
) -> dict[str, Any]:
    """
    深度爬取（BFS / DFS），从起始 URL 递归爬取同域名页面。

    Returns:
        {
            "start_url": ...,
            "strategy": ...,
            "pages_crawled": int,
            "pages": [{"url":..., "title":..., "markdown":...}, ...],
            "success": bool,
        }
    """
    from crawl4ai.deep_crawling import BFSDeepCrawlStrategy, DFSDeepCrawlStrategy

    max_pages = min(max_pages, config.deep_max_pages)

    crawler_strategy = (
        BFSDeepCrawlStrategy(max_depth=max_depth, max_pages=max_pages)
        if strategy.lower() == "bfs"
        else DFSDeepCrawlStrategy(max_depth=max_depth, max_pages=max_pages)
    )

    browser_config = _build_browser_config()
    run_config = _build_run_config()
    run_config.deep_crawl_strategy = crawler_strategy

    pages: list[dict] = []

    with _muted_stdout():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            raw_results = await crawler.arun(url=url, config=run_config)

    # crawl4ai 0.8.x: arun with deep_crawl_strategy returns a list
    if not isinstance(raw_results, list):
        raw_results = [raw_results]

    for result in raw_results:
        if not result.success:
            continue
        md = result.markdown
        content = md.fit_markdown or md.raw_markdown or "" if md else ""
        # 关键词过滤
        if keyword_filter and keyword_filter.lower() not in content.lower():
            continue
        pages.append({
            "url": result.url,
            "title": (result.metadata or {}).get("title", ""),
            "markdown": content[:3000],  # 每页最多 3000 字符，防止超长
        })

    return {
        "start_url": url,
        "strategy": strategy,
        "pages_crawled": len(pages),
        "pages": pages,
        "success": True,
    }


async def extract_structured(
    url: str,
    *,
    schema: dict[str, Any],
    js_code: str | None = None,
) -> dict[str, Any]:
    """
    CSS Schema 结构化提取，无需 LLM。

    schema 格式：
    {
        "name": "产品列表",
        "baseSelector": ".product-item",
        "fields": [
            {"name": "title", "selector": "h2", "type": "text"},
            {"name": "price", "selector": ".price", "type": "text"},
            {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
        ]
    }
    """
    import json as _json
    from crawl4ai import JsonCssExtractionStrategy

    strategy = JsonCssExtractionStrategy(schema, verbose=False)
    browser_config = _build_browser_config()
    run_config = _build_run_config(
        extraction_strategy=strategy,
        js_code=[js_code] if js_code else None,
        use_prune_filter=False,
        cache_mode=CacheMode.BYPASS,
    )

    with _muted_stdout():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        return {"url": url, "success": False, "error": result.error_message, "data": []}

    try:
        data = _json.loads(result.extracted_content) if result.extracted_content else []
    except Exception as e:
        data = []

    return {
        "url": url,
        "success": True,
        "count": len(data),
        "data": data,
    }


async def screenshot_page(
    url: str,
    *,
    wait_for: str | None = None,
    js_code: str | None = None,
) -> dict[str, Any]:
    """
    截取网页截图，保存到本地并返回文件路径。

    Returns:
        {"url":..., "path":..., "success":bool, "error":str|None}
    """
    import time

    os.makedirs(config.screenshot_dir, exist_ok=True)

    browser_config = _build_browser_config()
    run_config = _build_run_config(
        screenshot=True,
        js_code=[js_code] if js_code else None,
        wait_for=wait_for,
        use_prune_filter=False,
        cache_mode=CacheMode.BYPASS,
    )

    with _muted_stdout():
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        return {"url": url, "success": False, "error": result.error_message, "path": None}

    screenshot_data = getattr(result, "screenshot", None)
    if not screenshot_data:
        return {"url": url, "success": False, "error": "截图数据为空", "path": None}

    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.abspath(os.path.join(config.screenshot_dir, filename))

    # screenshot 可能是 base64 字符串或 bytes
    if isinstance(screenshot_data, str):
        raw = base64.b64decode(screenshot_data)
    else:
        raw = screenshot_data

    with open(filepath, "wb") as f:
        f.write(raw)

    return {"url": url, "success": True, "path": filepath, "error": None}


async def batch_crawl(
    urls: list[str],
    *,
    use_prune_filter: bool = True,
) -> dict[str, Any]:
    """
    批量并发爬取多个 URL，自动控制并发数量。

    Returns:
        {
            "total": int,
            "success": int,
            "failed": int,
            "results": [{"url":..., "markdown":..., "success":bool, "error":...}, ...],
        }
    """
    semaphore = asyncio.Semaphore(config.max_concurrent)

    async def _crawl_one(url: str) -> dict:
        async with semaphore:
            return await crawl_page(url, use_prune_filter=use_prune_filter)

    tasks = [_crawl_one(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output_results = []
    success_count = 0
    failed_count = 0

    for url, res in zip(urls, results):
        if isinstance(res, Exception):
            output_results.append({
                "url": url,
                "success": False,
                "markdown": "",
                "error": str(res),
            })
            failed_count += 1
        else:
            output_results.append(res)
            if res.get("success"):
                success_count += 1
            else:
                failed_count += 1

    return {
        "total": len(urls),
        "success": success_count,
        "failed": failed_count,
        "results": output_results,
    }
