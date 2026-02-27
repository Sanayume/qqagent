"""
Philosophy RAG MCP Server
哲学知识库检索服务，使用 Rewrite → Hybrid → Rerank 完整 RAG 流程
"""
import json
import asyncio
import sys
import os
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# 确保能找到同目录的模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_engine import RAGEngine

# 创建 MCP Server
server = Server("philosophy-rag")

# RAG 引擎实例
rag_engine: RAGEngine = None


def get_engine() -> RAGEngine:
    global rag_engine
    if rag_engine is None:
        rag_engine = RAGEngine()
    return rag_engine


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="rag_search",
            description="检索哲学知识库。自动进行查询改写、混合检索和重排序，返回最相关的知识片段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "查询内容"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回结果数量",
                        "default": 5
                    },
                    "skip_rewrite": {
                        "type": "boolean",
                        "description": "是否跳过 Query Rewrite 步骤以降低延迟",
                        "default": False
                    },
                    "skip_rerank": {
                        "type": "boolean",
                        "description": "是否跳过 Rerank 步骤以降低延迟",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name != "rag_search":
        return [TextContent(type="text", text=f"未知工具: {name}")]

    engine = get_engine()

    try:
        result = await engine.search_full(
            query=arguments["query"],
            top_k=arguments.get("top_k", 5),
            skip_rewrite=arguments.get("skip_rewrite", None),
            skip_rerank=arguments.get("skip_rerank", None)
        )

        # 简化输出：只保留关键信息
        output = {
            "query": result.get("original_query", arguments["query"]),
            "rewritten_query": result.get("rewritten_query"),
            "results": [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "score": round(r.get("score", 0), 4)
                }
                for r in result.get("results", [])
            ]
        }

        return [TextContent(type="text", text=json.dumps(output, ensure_ascii=False, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=f"检索失败: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
