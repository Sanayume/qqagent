"""
Crawl4AI MCP Server
企业级网页爬取工具，为 qqagent 提供以下能力：

工具列表：
  crawl_page         - 单页爬取 → 干净 Markdown
  deep_crawl         - 深度多页爬取（BFS/DFS）
  extract_structured - CSS Schema 结构化数据提取
  screenshot_page    - 网页截图（保存到本地）
  batch_crawl        - 批量并发爬取多个 URL

环境变量（config/mcp_servers.json 中配置）：
  CRAWL4AI_HEADLESS           - 是否无头模式 (true/false, 默认 true)
  CRAWL4AI_PROXY              - 代理地址（可选）
  CRAWL4AI_PAGE_TIMEOUT       - 单页超时秒数（默认 30）
  CRAWL4AI_MAX_CONCURRENT     - 批量爬取最大并发（默认 5）
  CRAWL4AI_DEEP_MAX_PAGES     - 深度爬取最大页面数（默认 20）
  CRAWL4AI_PRUNE_THRESHOLD    - 内容过滤阈值 0~1（默认 0.48）
  CRAWL4AI_SCREENSHOT_DIR     - 截图保存目录（默认 workspace/screenshots）
  CRAWL4AI_CACHE_MODE         - 缓存模式 enabled/bypass/disabled（默认 bypass）
  CRAWL4AI_STEALTH            - 启用反爬模式（默认 true）
"""

import asyncio
import json
import os
import sys
from typing import Any

# ── Windows UTF-8 fix ──────────────────────────────────────────────────────
# MCP stdio transport 期望 UTF-8，但 Windows 默认使用 GBK/CP936
# 必须在所有其他 import 之前强制重定向
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
# ────────────────────────────────────────────────────────────────────────────

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 确保同目录模块可以被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crawler as crawl_engine  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# MCP Server 实例
# ─────────────────────────────────────────────────────────────────────────────

server = Server("crawl4ai")

# ─────────────────────────────────────────────────────────────────────────────
# 工具定义
# ─────────────────────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ── 1. 单页爬取 ────────────────────────────────────────────────────
        Tool(
            name="crawl_page",
            description=(
                "爬取单个网页，返回干净的 Markdown 内容。"
                "自动过滤导航栏、广告等噪音，适合获取文章、文档、新闻等内容。"
                "支持 JavaScript 注入和等待条件，可抓取动态渲染页面。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要爬取的网页 URL（需包含协议，如 https://）"
                    },
                    "js_code": {
                        "type": "string",
                        "description": "（可选）爬取前在页面执行的 JavaScript 代码，用于展开折叠内容、点击按钮等",
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "（可选）等待条件，CSS 选择器或 JavaScript 表达式，页面出现该元素后再获取内容",
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "是否返回页面中的链接（内链/外链），默认 false",
                        "default": False,
                    },
                    "include_images": {
                        "type": "boolean",
                        "description": "是否返回页面中的图片列表，默认 false",
                        "default": False,
                    },
                    "use_prune_filter": {
                        "type": "boolean",
                        "description": "是否启用内容过滤（去除噪音），默认 true。设为 false 获取完整原始 Markdown",
                        "default": True,
                    },
                },
                "required": ["url"],
            },
        ),

        # ── 2. 深度爬取 ────────────────────────────────────────────────────
        Tool(
            name="deep_crawl",
            description=(
                "从起始 URL 深度爬取整个网站（同域名），"
                "自动发现并跟随页面内链接。适合爬取文档站、博客等多页内容。"
                "支持 BFS（广度优先）和 DFS（深度优先）两种策略。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "起始 URL"
                    },
                    "strategy": {
                        "type": "string",
                        "enum": ["bfs", "dfs"],
                        "description": "爬取策略：bfs（广度优先，适合全面覆盖）或 dfs（深度优先，适合深挖某个分支），默认 bfs",
                        "default": "bfs",
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "最多爬取页面数，最大 20（由服务器配置限制），默认 10",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 20,
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大爬取深度（从起始页算起），默认 3",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "keyword_filter": {
                        "type": "string",
                        "description": "（可选）关键词过滤：只保留内容中包含该关键词的页面",
                    },
                },
                "required": ["url"],
            },
        ),

        # ── 3. 结构化提取 ──────────────────────────────────────────────────
        Tool(
            name="extract_structured",
            description=(
                "使用 CSS 选择器从网页提取结构化数据（JSON），无需 LLM。"
                "适合爬取商品列表、表格、文章列表等有规律的重复性数据。"
                "需要提供 JSON Schema 描述目标数据结构。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "目标网页 URL"
                    },
                    "schema": {
                        "type": "object",
                        "description": (
                            "CSS 提取 Schema，格式：\n"
                            "{\n"
                            "  \"name\": \"数据集名称\",\n"
                            "  \"baseSelector\": \".item\",  // 每条数据的根元素\n"
                            "  \"fields\": [\n"
                            "    {\"name\": \"title\", \"selector\": \"h2\", \"type\": \"text\"},\n"
                            "    {\"name\": \"link\", \"selector\": \"a\", \"type\": \"attribute\", \"attribute\": \"href\"}\n"
                            "  ]\n"
                            "}"
                        ),
                    },
                    "js_code": {
                        "type": "string",
                        "description": "（可选）提取前执行的 JavaScript，用于触发动态加载",
                    },
                },
                "required": ["url", "schema"],
            },
        ),

        # ── 4. 网页截图 ────────────────────────────────────────────────────
        Tool(
            name="screenshot_page",
            description=(
                "对网页进行截图，保存为 PNG 文件并返回本地文件路径。"
                "适合查看页面视觉效果、调试爬取问题、或存档网页快照。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要截图的网页 URL"
                    },
                    "wait_for": {
                        "type": "string",
                        "description": "（可选）截图前等待的 CSS 选择器，确保目标元素加载完成",
                    },
                    "js_code": {
                        "type": "string",
                        "description": "（可选）截图前执行的 JavaScript 代码",
                    },
                },
                "required": ["url"],
            },
        ),

        # ── 5. 批量爬取 ────────────────────────────────────────────────────
        Tool(
            name="batch_crawl",
            description=(
                "并发批量爬取多个 URL，自动控制并发数量（最大 5）。"
                "适合同时获取多个页面内容，比逐个爬取效率高数倍。"
                "返回每个 URL 的爬取结果，包含成功/失败状态。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要爬取的 URL 列表（建议不超过 20 个）",
                        "minItems": 1,
                        "maxItems": 30,
                    },
                    "use_prune_filter": {
                        "type": "boolean",
                        "description": "是否启用内容过滤，默认 true",
                        "default": True,
                    },
                },
                "required": ["urls"],
            },
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 工具调用分发
# ─────────────────────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        if name == "crawl_page":
            result = await crawl_engine.crawl_page(
                url=arguments["url"],
                js_code=arguments.get("js_code"),
                wait_for=arguments.get("wait_for"),
                use_prune_filter=arguments.get("use_prune_filter", True),
                include_links=arguments.get("include_links", False),
                include_images=arguments.get("include_images", False),
            )

        elif name == "deep_crawl":
            result = await crawl_engine.deep_crawl(
                url=arguments["url"],
                strategy=arguments.get("strategy", "bfs"),
                max_pages=arguments.get("max_pages", 10),
                max_depth=arguments.get("max_depth", 3),
                keyword_filter=arguments.get("keyword_filter"),
            )

        elif name == "extract_structured":
            result = await crawl_engine.extract_structured(
                url=arguments["url"],
                schema=arguments["schema"],
                js_code=arguments.get("js_code"),
            )

        elif name == "screenshot_page":
            result = await crawl_engine.screenshot_page(
                url=arguments["url"],
                wait_for=arguments.get("wait_for"),
                js_code=arguments.get("js_code"),
            )

        elif name == "batch_crawl":
            result = await crawl_engine.batch_crawl(
                urls=arguments["urls"],
                use_prune_filter=arguments.get("use_prune_filter", True),
            )

        else:
            result = {"error": f"未知工具: {name}"}

        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    except Exception as e:
        error = {"error": str(e), "tool": name}
        return [TextContent(type="text", text=json.dumps(error, ensure_ascii=False))]


# ─────────────────────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
