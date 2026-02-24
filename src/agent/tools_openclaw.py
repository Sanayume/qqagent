"""OpenClaw Sub-Agent 工具

将 OpenClaw Gateway 作为 sub-agent 调用。
热插拔：可通过 config/builtin_tools.yaml 随时启用/禁用。
前置条件：OpenClaw Gateway 需要在本地运行（默认 127.0.0.1:18789）。
"""

import os
import httpx
from langchain_core.tools import tool

OPENCLAW_BASE = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
OPENCLAW_TIMEOUT = int(os.getenv("OPENCLAW_TIMEOUT", "120"))


@tool
def openclaw_agent(task: str) -> str:
    """委托任务给 OpenClaw 自主代理。它拥有独立的工具链，能自主完成多步骤任务。

    适用场景（必须满足至少一项才调用）：
    - 需要在服务器上读写文件、执行 shell 命令
    - 需要浏览网页并提取结构化信息（不是简单搜索）
    - 需要多步骤推理+执行的复杂任务（如：分析日志→定位问题→生成报告）
    - 用户明确要求使用 OpenClaw 或 sub-agent

    禁止调用的场景：
    - 普通聊天、问答、闲聊
    - 简单的网页搜索（用 web_search）
    - 你自己能直接回答的问题

    task 参数要写清楚具体要做什么，像给一个人下达工作指令一样。

    Args:
        task: 详细的任务指令，包含目标、约束和期望输出格式
    """
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    payload = {
        "model": "default",
        "messages": [{"role": "user", "content": task}],
        "stream": False,
    }

    try:
        client = httpx.Client(proxy=None, trust_env=False)
        resp = client.post(
            f"{OPENCLAW_BASE}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=OPENCLAW_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # OpenAI 兼容格式
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "OpenClaw 无返回内容")
        return "OpenClaw 无返回内容"
    except httpx.ConnectError:
        return "错误: OpenClaw Gateway 未运行，请先启动 openclaw gateway"
    except httpx.HTTPStatusError as e:
        return f"错误: OpenClaw 返回 {e.response.status_code}"
    except Exception as e:
        return f"错误: {e}"
