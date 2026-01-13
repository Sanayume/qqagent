"""
LangGraph QQ Agent - 主程序

整合 OneBot 适配器和 LangGraph Agent，实现完整的 QQ 机器人。
支持多模态消息处理（图片、引用、转发）。
"""

import asyncio
import os
import re
from dotenv import load_dotenv

from src.adapters.onebot import OneBotAdapter, OneBotEvent
from src.adapters.mcp import MCPManager
from src.agent.graph import QQAgent
from src.agent.tools import DEFAULT_TOOLS
from src.memory import MemoryStore
from src.presets import PresetManager
from src.utils.config import load_settings
from src.utils.config_loader import get_config_loader
from src.utils.logger import setup_logger, log

# 导入 core 模块
from src.core.onebot import parse_segments, make_text_description, build_text_segment, build_image_segment
from src.core.media import download_and_encode
from src.core.llm_message import build_multimodal_message, build_context_message


# 加载 .env 文件
load_dotenv()


# ==================== 消息处理辅助函数 ====================


async def fetch_reply_context(adapter: OneBotAdapter, reply_id: int) -> str | None:
    """获取引用消息的上下文描述

    Args:
        adapter: OneBot 适配器
        reply_id: 引用消息 ID

    Returns:
        上下文描述字符串，失败返回 None
    """
    try:
        result = await adapter.get_msg(reply_id)
        if result.get("status") != "ok":
            return None

        data = result.get("data", {})
        segments = data.get("message", [])
        parsed = parse_segments(segments)
        sender = data.get("sender", {}).get("nickname", "某人")
        context = f"{sender}: {make_text_description(parsed)}"
        log.debug(f"Reply context: {context}")
        return context
    except Exception as e:
        log.warning(f"Failed to get reply message: {e}")
        return None


async def fetch_forward_summary(adapter: OneBotAdapter, forward_id: str, max_nodes: int = 5) -> str | None:
    """获取合并转发消息的摘要

    Args:
        adapter: OneBot 适配器
        forward_id: 转发消息 ID
        max_nodes: 最多获取的节点数

    Returns:
        摘要字符串，失败返回 None
    """
    try:
        result = await adapter.get_forward_msg(forward_id)
        if result.get("status") != "ok":
            return None

        nodes = result.get("data", {}).get("message", [])
        summaries = []

        for node in nodes[:max_nodes]:
            if node.get("type") == "node":
                node_data = node.get("data", {})
                nickname = node_data.get("nickname", "某人")
                content = node_data.get("content", "")
                if isinstance(content, list):
                    node_parsed = parse_segments(content)
                    content = make_text_description(node_parsed)
                summaries.append(f"{nickname}: {content[:50]}")

        if len(nodes) > max_nodes:
            summaries.append(f"...还有 {len(nodes) - max_nodes} 条消息")

        summary = "\n".join(summaries)
        log.debug(f"Forward summary: {summary[:100]}...")
        return summary
    except Exception as e:
        log.warning(f"Failed to get forward message: {e}")
        return None


async def download_message_images(image_urls: list[str], max_count: int = 3) -> list[tuple[str, str]]:
    """下载消息中的图片

    Args:
        image_urls: 图片 URL 列表
        max_count: 最多下载的图片数

    Returns:
        图片列表 [(base64, mime_type), ...]
    """
    images = []
    for url in image_urls[:max_count]:
        try:
            b64, mime = await download_and_encode(url)
            images.append((b64, mime))
            log.debug(f"Downloaded image: {mime}, {len(b64)} chars")
        except Exception as e:
            log.warning(f"Failed to download image {url}: {e}")
    return images


async def build_response_segments(
    response_text: str,
    tool_images: list[tuple[str, str]],
) -> list[dict]:
    """构建回复消息段

    处理文本中的 markdown 图片链接，并附加工具返回的图片。

    Args:
        response_text: AI 回复文本
        tool_images: 工具返回的图片列表 [(base64, mime_type), ...]

    Returns:
        OneBot 消息段列表
    """
    segments = []

    # 处理文本中的 markdown 图片链接 ![...](url)
    img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    parts = re.split(img_pattern, response_text)

    i = 0
    while i < len(parts):
        if i + 2 < len(parts):
            # 图片匹配: (text_before, alt, url, ...)
            text_before = parts[i]
            if text_before.strip():
                segments.append(build_text_segment(text_before))

            # 跳过 alt text，获取 URL
            img_url = parts[i + 2]

            # 下载图片并转为 base64
            try:
                log.debug(f"Downloading response image: {img_url}")
                img_b64, img_mime = await download_and_encode(img_url)
                segments.append(build_image_segment(f"base64://{img_b64}"))
                log.debug(f"Converted image to base64: {len(img_b64)} chars")
            except Exception as e:
                log.warning(f"Failed to download response image {img_url}: {e}")
                segments.append(build_text_segment(f"[图片: {img_url}]"))

            i += 3
        else:
            # 剩余文本
            if parts[i].strip():
                segments.append(build_text_segment(parts[i]))
            i += 1

    # 添加工具返回的图片
    for img_b64, img_mime in tool_images:
        segments.append(build_image_segment(f"base64://{img_b64}"))
        log.debug(f"Added tool image: {img_mime}, {len(img_b64)} chars")

    return segments


# ==================== 主程序 ====================


async def main():
    # 加载配置
    settings = load_settings()
    config_loader = get_config_loader()

    # 设置日志 (使用配置的日志级别)
    setup_logger(level=settings.log_level)

    log.info("=" * 60)
    log.info("LangGraph QQ Agent Starting...")
    log.info("=" * 60)
    log.info(f"Log Level: {settings.log_level}")
    log.info(f"OneBot Mode: {settings.onebot.mode}")
    log.info(f"LLM Model: {settings.llm.default_model}")
    log.info(f"LangSmith: {'Enabled' if settings.langchain_tracing_v2 else 'Disabled'}")

    # 设置 LangSmith 环境变量
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
        log.info(f"LangSmith Project: {settings.langchain_project}")

    # 创建 MemoryStore (SQLite 持久化)
    memory_store = MemoryStore(db_path="data/sessions.db", max_messages=20)
    log.success(f"MemoryStore initialized: {memory_store.get_session_count()} existing sessions")

    # 创建 PresetManager
    preset_manager = PresetManager(
        config_loader=config_loader,
        preset_dir="config/presets",
    )

    # 获取默认预设 (根据配置)
    preset_name = settings.agent.default_preset
    default_preset = preset_manager.get(preset_name) or preset_manager.get_default()
    log.info(f"Default preset: {default_preset.name}")

    # 启动 MCP 服务器并获取工具 (超时 120 秒，重试 2 次)
    mcp_manager = MCPManager("config/mcp_servers.json", timeout=120.0, retry_count=2)
    await mcp_manager.start()
    mcp_tools = mcp_manager.get_tools()

    # 合并内置工具和 MCP 工具
    all_tools = DEFAULT_TOOLS + mcp_tools
    log.info(f"Total tools: {len(all_tools)} (builtin: {len(DEFAULT_TOOLS)}, MCP: {len(mcp_tools)})")

    # 创建 Agent
    agent = QQAgent(
        model=settings.llm.default_model,
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_api_base,
        default_system_prompt=default_preset.system_prompt,
        memory_store=memory_store,
        tools=all_tools,
    )

    log.success("Agent created successfully")
    
    # 创建 OneBot 适配器
    adapter = OneBotAdapter(
        ws_url=settings.onebot.ws_url,
        reverse_host=settings.onebot.reverse_ws_host,
        reverse_port=settings.onebot.reverse_ws_port,
        reverse_path=settings.onebot.reverse_ws_path,
        token=settings.onebot.token,
        mode=settings.onebot.mode,
    )
    
    # 初始化会话管理器
    from src.session.manager import SessionManager
    adapter.session_manager = SessionManager(use_loader=True)
    
    # 触发配置
    bot_names = settings.agent.bot_names
    allow_at = settings.agent.allow_at_reply
    allow_private = settings.agent.allow_private
    
    log.info(f"Bot names: {bot_names}")
    log.info(f"Allow @: {allow_at}, Allow private: {allow_private}")
    
    # 消息处理器
    @adapter.on_message
    async def handle_message(event: OneBotEvent):
        """处理收到的消息（支持多模态）"""
        # 解析消息段
        segments = event.message if isinstance(event.message, list) else []
        parsed = parse_segments(segments)

        # 生成文本描述（用于日志和触发检测）
        text_desc = make_text_description(parsed)
        plain_text = parsed.text.strip()
        sender = event.sender_nickname

        # 日志
        if event.is_group:
            log.info(f"[群 {event.group_id}] {sender}({event.user_id}): {text_desc}")
        else:
            log.info(f"[私聊 {event.user_id}] {sender}: {text_desc}")

        # 检查是否应该响应
        should_respond = False

        if event.is_private and allow_private:
            should_respond = True
        if event.is_group and allow_at and adapter.self_id:
            if event.is_at_me(adapter.self_id):
                should_respond = True
        for name in bot_names:
            if name.lower() in plain_text.lower():
                should_respond = True
                break

        if not should_respond:
            return

        log.info(f"Responding to: {text_desc}")
        log.debug(f"Raw segments: {segments}")
        log.debug(f"Parsed image_urls: {parsed.image_urls}")

        try:
            # 生成会话 ID
            session_id = adapter.session_manager.get_session_id(
                user_id=event.user_id,
                group_id=event.group_id if event.is_group else None,
                is_private=event.is_private,
            )

            # 获取上下文（引用消息、合并转发）
            reply_context = None
            forward_summary = None

            if parsed.has_reply() and parsed.reply_id:
                reply_context = await fetch_reply_context(adapter, parsed.reply_id)

            if parsed.has_forward() and parsed.forward_id:
                forward_summary = await fetch_forward_summary(adapter, parsed.forward_id)

            # 下载图片
            images = await download_message_images(parsed.image_urls) if parsed.has_images() else []

            # 构建 LLM 消息
            context_text = build_context_message(
                main_text=plain_text,
                reply_context=reply_context,
                forward_summary=forward_summary,
            )
            llm_message = build_multimodal_message(text=context_text, images=images)

            # 调用 Agent
            chat_response = await agent.chat(
                message=llm_message,
                session_id=session_id,
                user_id=event.user_id,
                group_id=event.group_id,
                user_name=sender,
            )

            response_text = chat_response.text
            tool_images = chat_response.images

            log.info(f"Response: {response_text[:100]}..." if len(response_text) > 100 else f"Response: {response_text}")
            if tool_images:
                log.info(f"Tool returned {len(tool_images)} image(s)")

            # 构建回复消息段
            response_segments = await build_response_segments(response_text, tool_images)

            # 发送回复
            if not response_segments:
                await adapter.send_msg(event, response_text)
            elif len(response_segments) == 1 and response_segments[0]["type"] == "text":
                await adapter.send_msg(event, response_text)
            else:
                await adapter.send_msg(event, response_segments)

        except Exception as e:
            log.exception(f"Error processing message: {e}")
            await adapter.send_msg(event, f"抱歉，处理消息时出错了: {str(e)[:50]}")
    
    # 事件处理器
    @adapter.on_event
    async def handle_event(event: OneBotEvent):
        """处理全部事件"""
        if event.post_type == "meta_event":
            if event.meta_event_type == "lifecycle":
                log.success(f"Bot connected! QQ: {event.self_id}")
            elif event.meta_event_type == "heartbeat":
                log.debug("Heartbeat")
    
    # 启动
    log.info("=" * 60)
    log.info("Bot is running! Waiting for messages...")
    log.info(f"Triggers: @bot, or mention: {bot_names}")
    log.info("Press Ctrl+C to stop")
    log.info("=" * 60)
    
    try:
        await adapter.start()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        await adapter.stop()
        await mcp_manager.stop()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
