"""OpenClaw Sub-Agent 工具

将 OpenClaw Gateway 作为 sub-agent 调用，支持：
- SSE 流式读取，实时检测完成状态
- 多轮对话（通过 conversation_id 追问）
- 结构化 JSON 返回，主 Agent 可判断成功/失败/超时

热插拔：可通过 config/builtin_tools.yaml 随时启用/禁用。
前置条件：OpenClaw Gateway 需要在本地运行（默认 127.0.0.1:18789）。
"""

import json
import os
import time
import secrets
import httpx
from langchain_core.tools import tool

from src.utils.config_loader import get_tuning
from src.utils.logger import log

# ---------------------------------------------------------------------------
# 常量与配置
# ---------------------------------------------------------------------------
DEFAULT_OPENCLAW_TIMEOUT = 120
DEFAULT_OPENCLAW_MODEL = "default"
MAX_CONVERSATION_AGE = 1800          # 30 分钟自动清理
MAX_CONTENT_LENGTH = 8000            # 截断过长响应
STREAM_CHUNK_TIMEOUT = 30            # 无数据超过 30 秒视为卡死

OPENCLAW_BASE = os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_GATEWAY_TOKEN", "")

# SubAgent 系统提示词 — 告诉 OpenClaw 它的角色定位
DEFAULT_OPENCLAW_SYSTEM_PROMPT = """\
你是"琪露诺"的后台执行助手。琪露诺是一个 QQ 群聊机器人（猫娘人设，口癖"~喵"）。

## 你的定位
- 你是幕后工作者，负责执行琪露诺无法直接完成的任务（文件操作、Shell 命令、深度网页抓取、多步骤分析等）
- 你的输出不会直接发给用户，而是由琪露诺阅读后用她自己的风格转述
- 因此你不需要模仿琪露诺的语气，专注把事情做好、把结果说清楚即可

## 主动反馈 — 最重要的规则
- 如果任务描述模糊、缺少关键信息、有多种理解方式，你必须在回复中明确提出疑问，列出你需要确认的点
- 格式示例："[需要确认] 1. xxx是指A还是B？2. 范围是xxx还是xxx？"
- 琪露诺看到你的疑问后会补充信息再次调用你，不要自己猜测然后硬做
- 宁可多问一轮也不要交付一个跑偏的结果
- 如果任务清晰无歧义，直接执行，不要为了问而问

## 执行态度 — 不许偷懒
- 完整执行任务，不要省略步骤、不要只做一半就汇报
- 如果任务要求分析10个文件，就分析10个，不要看了3个就说"其余类似"
- 如果需要执行多个命令，逐个执行并汇报每个的结果，不要跳过
- 遇到错误不要立刻放弃，至少尝试2-3种不同方案再报告失败
- 给出的数据要具体（具体数字、具体文件名、具体行号），不要用"大概""可能""一些"

## 输出要求
- 用简洁的中文汇报结果，重点突出关键信息
- 如果任务涉及数据/日志/代码，提取核心结论，不要原样倾倒大段原文
- 如果执行失败，明确说明：失败原因、已尝试的方案、建议的下一步
- 结果分层：先给结论，再给细节，方便琪露诺快速抓重点

## 注意事项
- 琪露诺的用户是 QQ 群友，非技术背景居多，结果要通俗易懂
- 不要输出 Markdown 格式（群聊不渲染）
- 不要自称"我是AI"之类的，你就是琪露诺的工具人，低调干活就好\
"""

# ---------------------------------------------------------------------------
# 会话状态管理
# ---------------------------------------------------------------------------
_conversations: dict[str, dict] = {}


def _get_config(key: str, default):
    """配置读取优先级：环境变量 > get_tuning() > 硬编码默认值"""
    env_val = os.getenv(f"OPENCLAW_{key.upper()}")
    if env_val is not None:
        # 尝试转为与 default 同类型
        try:
            return type(default)(env_val)
        except (ValueError, TypeError):
            return env_val
    tuning_val = get_tuning(f"openclaw_{key}", None)
    if tuning_val is not None:
        return tuning_val
    return default


def _generate_conversation_id() -> str:
    return f"oc_{secrets.token_hex(6)}"


def _cleanup_stale_conversations():
    """清理超过 MAX_CONVERSATION_AGE 的会话"""
    now = time.time()
    stale = [cid for cid, c in _conversations.items()
             if now - c["last_used"] > MAX_CONVERSATION_AGE]
    for cid in stale:
        del _conversations[cid]
    if stale:
        log.debug(f"OpenClaw | cleaned {len(stale)} stale conversations")


def _build_result(
    status: str,
    content: str,
    conversation_id: str,
    turn: int,
    elapsed: float,
    error: str | None = None,
    error_type: str | None = None,
    retryable: bool = False,
) -> str:
    """构建结构化 JSON 返回"""
    if content and len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n...[内容已截断]"
    return json.dumps({
        "status": status,
        "content": content,
        "conversation_id": conversation_id,
        "turn": turn,
        "elapsed_seconds": round(elapsed, 2),
        "error": error,
        "error_type": error_type,
        "retryable": retryable,
    }, ensure_ascii=False)


def _consume_sse_stream(response: httpx.Response, chunk_timeout: float) -> tuple[str, bool]:
    """消费 SSE 流，返回 (拼接内容, 是否正常完成)

    chunk_timeout 通过 httpx 的 read timeout 实现，不依赖循环内手动计时。
    """
    content_parts: list[str] = []
    completed = False
    buf = ""

    try:
        for raw_bytes in response.stream:
            buf += raw_bytes.decode("utf-8", errors="replace")
            # 按行切分，保留未完成的最后一段
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()

                if not line:
                    continue

                if line == "data: [DONE]":
                    completed = True
                    return "".join(content_parts), completed

                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            content_parts.append(text)
                    except (json.JSONDecodeError, IndexError, KeyError):
                        continue
    except httpx.ReadTimeout:
        log.warning("OpenClaw | SSE chunk read timeout, returning partial content")

    return "".join(content_parts), completed


# ---------------------------------------------------------------------------
# 主工具函数
# ---------------------------------------------------------------------------
@tool
def openclaw_agent(task: str, conversation_id: str = "") -> str:
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

    多轮对话机制（重要）：
    - 返回的 JSON 中 content 可能包含 "[需要确认]" 开头的反问，说明 SubAgent 需要更多信息才能正确执行
    - 此时你应该根据用户原始需求和上下文，组织补充信息，用同一个 conversation_id 再次调用本工具回答它的问题
    - 不要把 SubAgent 的反问直接转发给用户，你自己能回答的就直接回答
    - 只有当你也无法判断时，才通过 send_message 向用户确认，拿到答案后再传给 SubAgent
    - 收到最终结果后，用你自己的风格转述给用户，不要原样复读 SubAgent 的输出

    task 参数要写清楚具体要做什么，像给一个人下达工作指令一样。
    返回结构化 JSON，包含 status/content/conversation_id 等字段。
    首次调用不传 conversation_id；追问时传入上次返回的 conversation_id 即可继续对话。

    Args:
        task: 详细的任务指令，包含目标、约束和期望输出格式
        conversation_id: 可选，传入之前返回的 conversation_id 可继续多轮对话
    """
    start = time.time()
    _cleanup_stale_conversations()

    # 读取配置
    total_timeout = _get_config("timeout", DEFAULT_OPENCLAW_TIMEOUT)
    model = _get_config("model", DEFAULT_OPENCLAW_MODEL)
    chunk_timeout = _get_config("stream_chunk_timeout", STREAM_CHUNK_TIMEOUT)

    # 会话管理：复用或新建
    cid = conversation_id.strip() if conversation_id else ""
    if cid and cid in _conversations:
        conv = _conversations[cid]
        conv["messages"].append({"role": "user", "content": task})
        conv["last_used"] = time.time()
    else:
        cid = _generate_conversation_id()
        conv = {
            "messages": [{"role": "user", "content": task}],
            "created_at": time.time(),
            "last_used": time.time(),
        }
        _conversations[cid] = conv

    turn = len([m for m in conv["messages"] if m["role"] == "user"])

    # 构建请求
    headers = {"Content-Type": "application/json"}
    if OPENCLAW_TOKEN:
        headers["Authorization"] = f"Bearer {OPENCLAW_TOKEN}"

    # 注入 system prompt（放在 messages 最前面，OpenClaw Gateway 会提取为 extraSystemPrompt）
    system_prompt = _get_config("system_prompt", DEFAULT_OPENCLAW_SYSTEM_PROMPT)
    if not system_prompt:
        system_prompt = DEFAULT_OPENCLAW_SYSTEM_PROMPT
    api_messages = [{"role": "system", "content": system_prompt}] + conv["messages"]

    payload = {
        "model": model,
        "messages": api_messages,
        "stream": True,
        "user": cid,
    }

    log.info(f"OpenClaw | cid={cid} turn={turn} task={task[:80]}")

    try:
        with httpx.Client(proxy=None, trust_env=False) as client:
            with client.stream(
                "POST",
                f"{OPENCLAW_BASE}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(total_timeout, connect=10.0, read=chunk_timeout),
            ) as resp:
                resp.raise_for_status()
                content, completed = _consume_sse_stream(resp, chunk_timeout)

        elapsed = time.time() - start

        # 保存 assistant 回复到会话历史
        if content:
            conv["messages"].append({"role": "assistant", "content": content})

        if not content:
            status = "empty"
            log.warning(f"OpenClaw | cid={cid} empty response in {elapsed:.1f}s")
        elif completed:
            status = "success"
            log.info(f"OpenClaw | cid={cid} status=success in {elapsed:.1f}s")
        else:
            status = "timeout"
            log.warning(f"OpenClaw | cid={cid} status=timeout (partial) in {elapsed:.1f}s")

        return _build_result(
            status=status,
            content=content,
            conversation_id=cid,
            turn=turn,
            elapsed=elapsed,
        )

    except httpx.ConnectError:
        elapsed = time.time() - start
        log.error(f"OpenClaw | cid={cid} connection failed")
        return _build_result(
            status="error",
            content="",
            conversation_id=cid,
            turn=turn,
            elapsed=elapsed,
            error="OpenClaw Gateway 未运行，请先启动 openclaw gateway",
            error_type="connection",
            retryable=False,
        )

    except httpx.TimeoutException:
        elapsed = time.time() - start
        log.error(f"OpenClaw | cid={cid} timeout after {elapsed:.1f}s")
        return _build_result(
            status="timeout",
            content="",
            conversation_id=cid,
            turn=turn,
            elapsed=elapsed,
            error=f"请求超时（{total_timeout}秒）",
            error_type="timeout",
            retryable=True,
        )

    except httpx.HTTPStatusError as e:
        elapsed = time.time() - start
        code = e.response.status_code
        if code == 401:
            etype, retry = "auth", False
        elif code == 429:
            etype, retry = "rate_limit", True
        elif code >= 500:
            etype, retry = "server", True
        else:
            etype, retry = "unknown", False
        log.error(f"OpenClaw | cid={cid} HTTP {code}")
        return _build_result(
            status="error",
            content="",
            conversation_id=cid,
            turn=turn,
            elapsed=elapsed,
            error=f"OpenClaw 返回 HTTP {code}",
            error_type=etype,
            retryable=retry,
        )

    except Exception as e:
        elapsed = time.time() - start
        log.error(f"OpenClaw | cid={cid} unexpected error: {e}")
        return _build_result(
            status="error",
            content="",
            conversation_id=cid,
            turn=turn,
            elapsed=elapsed,
            error=str(e),
            error_type="unknown",
            retryable=False,
        )
