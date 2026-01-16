"""
LangGraph QQ Agent - 主程序

整合 OneBot 适配器和 LangGraph Agent，实现完整的 QQ 机器人。
支持多模态消息处理（图片、引用、转发）。
"""

import asyncio
import os

from src.adapters.onebot import OneBotAdapter, OneBotEvent
from src.adapters.mcp import MCPManager
from src.agent.graph import QQAgent
from src.agent.tools import DEFAULT_TOOLS, set_send_message_callback
from src.memory import MemoryStore
from src.presets import PresetManager
from src.utils.config import load_settings
from src.utils.config_loader import get_config_loader
from src.utils.env_loader import get_env_loader
from src.utils.logger import setup_logger, log, log_error

# 导入 core 模块
from src.core.onebot import parse_segments, make_text_description
from src.core.media import download_and_encode
from src.core.llm_message import build_multimodal_message, build_rich_context_message
from src.core.exceptions import (
    NetworkError, APIError, RateLimitError, AuthError,
    MediaError, DownloadError, OneBotError,
)
from src.core.resilience import CircuitOpenError
from src.session.aggregator import (
    MessageAggregator, PendingMessage,
    format_aggregated_messages, collect_images_from_messages,
)


# 加载 .env 文件 (使用 EnvLoader 支持热重载)
env_loader = get_env_loader()


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
            log.debug(f"获取引用消息失败: {result.get('msg', 'unknown')}")
            return None

        data = result.get("data", {})
        segments = data.get("message", [])
        parsed = parse_segments(segments)
        sender = data.get("sender", {}).get("nickname", "某人")
        context = f"{sender}: {make_text_description(parsed)}"
        log.debug(f"Reply context: {context}")
        return context

    except asyncio.TimeoutError:
        log.warning("⏱️ 获取引用消息超时")
        return None
    except OneBotError as e:
        log.warning(f"🤖 获取引用消息失败: {e}")
        return None
    except Exception as e:
        log.warning(f"获取引用消息异常: {type(e).__name__}: {e}")
        return None


async def fetch_forward_content(adapter: OneBotAdapter, forward_id: str, max_nodes: int = 50) -> tuple[str | None, list[str]]:
    """获取合并转发消息的内容和图片

    Args:
        adapter: OneBot 适配器
        forward_id: 转发消息 ID
        max_nodes: 最多获取的节点数

    Returns:
        (摘要字符串, 图片URL列表)，失败返回 (None, [])
    """
    log.debug(f"Fetching forward message, id={forward_id}")
    try:
        result = await adapter.get_forward_msg(forward_id)
        log.debug(f"Forward API result status: {result.get('status')}, retcode: {result.get('retcode')}")

        if result.get("status") != "ok":
            log.warning(f"📦 获取转发消息失败: {result.get('msg', result.get('message', 'Unknown'))}")
            return None, []

        data = result.get("data", {})
        # NapCat 可能返回 "messages" 而不是 "message"
        nodes = data.get("message", data.get("messages", []))
        log.debug(f"Forward message has {len(nodes)} nodes")

        if not nodes:
            log.warning("📦 转发消息为空")
            return None, []

        summaries = []
        all_image_urls = []

        for i, node in enumerate(nodes[:max_nodes]):
            node_type = node.get("type", "unknown")

            # 尝试多种数据结构
            if node_type == "node":
                node_data = node.get("data", {})
            else:
                node_data = node

            nickname = node_data.get("nickname", node_data.get("sender", {}).get("nickname", "某人"))
            content = node_data.get("content", node_data.get("message", ""))

            if isinstance(content, list):
                node_parsed = parse_segments(content)
                if node_parsed.image_urls:
                    all_image_urls.extend(node_parsed.image_urls)
                content = make_text_description(node_parsed)
            elif isinstance(content, str):
                content = content.strip()
            else:
                content = str(content)[:200] if content else ""

            if nickname or content:
                summaries.append(f"{nickname}: {content[:200]}")

        if len(nodes) > max_nodes:
            summaries.append(f"...还有 {len(nodes) - max_nodes} 条消息")

        summary = "\n".join(summaries)
        log.info(f"📦 转发消息: {len(nodes)} 条, {len(all_image_urls)} 张图片")
        return summary, all_image_urls

    except asyncio.TimeoutError:
        log.warning("⏱️ 获取转发消息超时")
        return None, []
    except OneBotError as e:
        log.warning(f"🤖 获取转发消息失败: {e}")
        return None, []
    except Exception as e:
        log.warning(f"获取转发消息异常: {type(e).__name__}: {e}")
        return None, []


async def download_message_images(image_urls: list[str], max_count: int = 3) -> list[tuple[str, str]]:
    """下载消息中的图片

    Args:
        image_urls: 图片 URL 列表
        max_count: 最多下载的图片数

    Returns:
        图片列表 [(base64, mime_type), ...]
    """
    images = []
    failed_count = 0

    for url in image_urls[:max_count]:
        try:
            b64, mime = await download_and_encode(url)
            images.append((b64, mime))
            log.debug(f"🖼️ 下载图片成功: {mime}, {len(b64)} chars")
        except asyncio.TimeoutError:
            failed_count += 1
            log.warning(f"⏱️ 下载图片超时: {url[:50]}...")
        except DownloadError as e:
            failed_count += 1
            log.warning(f"⬇️ 下载图片失败: {e}")
        except MediaError as e:
            failed_count += 1
            log.warning(f"🖼️ 图片处理失败: {e}")
        except Exception as e:
            failed_count += 1
            log.warning(f"下载图片异常: {type(e).__name__}: {e}")

    if failed_count > 0:
        log.info(f"🖼️ 图片下载: {len(images)} 成功, {failed_count} 失败")

    return images


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
    memory_store = MemoryStore(db_path="data/sessions.db", max_messages=settings.agent.max_history_messages)
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
    
    # 注册 .env 热重载回调 (更新 LLM 配置)
    def on_env_reload():
        """当 .env 发生变化时，重新创建 LLM 实例"""
        new_api_key = os.getenv("OPENAI_API_KEY", "")
        new_base_url = os.getenv("OPENAI_API_BASE", "")
        new_model = os.getenv("DEFAULT_MODEL", settings.llm.default_model)
        
        if new_api_key != agent.api_key or new_base_url != agent.base_url or new_model != agent.model:
            log.info(f"Updating agent LLM config: model={new_model}, base_url={new_base_url[:30]}...")
            agent.api_key = new_api_key
            agent.base_url = new_base_url
            agent.model = new_model
            # 重新创建 graph 以应用新配置
            agent.graph = agent._create_graph()
            log.success("Agent LLM config updated!")
    
    env_loader.add_callback(on_env_reload)
    
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
    allow_all_group = settings.agent.allow_all_group_msg

    log.info(f"Bot names: {bot_names}")
    log.info(f"Allow @: {allow_at}, Allow private: {allow_private}, Allow all group: {allow_all_group}")

    # ==================== 核心处理函数 ====================

    async def process_single_message(
        event: OneBotEvent,
        parsed,
        plain_text: str,
        sender: str,
        reply_context: str | None,
        forward_summary: str | None,
        all_image_urls: list[str],
    ):
        """处理单条消息（私聊或未聚合的群消息）"""
        session_id = adapter.session_manager.get_session_id(
            user_id=event.user_id,
            group_id=event.group_id if event.is_group else None,
            is_private=event.is_private,
        )

        # 下载图片
        images = await download_message_images(all_image_urls, max_count=5) if all_image_urls else []

        # 构建 LLM 消息
        context_text = build_rich_context_message(
            main_text=plain_text,
            sender_name=sender,
            sender_qq=event.user_id,
            message_id=event.message_id or 0,
            group_id=event.group_id if event.is_group else None,
            reply_to_id=parsed.reply_id,
            reply_context=reply_context,
            at_targets=parsed.at_targets if parsed.at_targets else None,
            forward_summary=forward_summary,
        )
        llm_message = build_multimodal_message(text=context_text, images=images)

        await invoke_agent(event, session_id, llm_message)

    async def process_aggregated_messages(
        group_id: int,
        messages: list[PendingMessage],
        first_event,
    ):
        """处理聚合后的群消息"""
        if not messages or not first_event:
            return

        log.info(f"🔄 处理聚合消息: 群 {group_id}, {len(messages)} 条")

        session_id = adapter.session_manager.get_session_id(
            user_id=first_event.user_id,
            group_id=group_id,
            is_private=False,
        )

        # 收集所有图片
        all_image_urls = collect_images_from_messages(messages)
        images = await download_message_images(all_image_urls, max_count=5) if all_image_urls else []

        # 格式化聚合消息
        context_text = format_aggregated_messages(messages, group_id)
        llm_message = build_multimodal_message(text=context_text, images=images)

        await invoke_agent(first_event, session_id, llm_message)

    async def invoke_agent(event: OneBotEvent, session_id: str, llm_message):
        """调用 Agent 并处理响应"""
        loop = asyncio.get_running_loop()

        # 实时发送回调 - 工具调用时触发，提交到适配器发送
        def realtime_callback(cmd: dict):
            asyncio.run_coroutine_threadsafe(
                adapter.send_rich_msg(
                    event=event,
                    text=cmd.get("text", ""),
                    image=cmd.get("image", ""),
                    at_users=cmd.get("at_users"),
                    reply_to=cmd.get("reply_to", 0),
                ),
                loop,
            )

        set_send_message_callback(realtime_callback)

        try:
            await agent.chat(
                message=llm_message,
                session_id=session_id,
                user_id=event.user_id,
                group_id=event.group_id,
                user_name=event.sender_nickname,
            )
            log.info("💭 Agent 处理完成")

        except RateLimitError as e:
            log_error(e, context="调用 LLM")
            await adapter.send_rich_msg(event, text="🚦 请求太频繁了，请稍后再试~")

        except AuthError as e:
            log_error(e, context="调用 LLM")
            await adapter.send_rich_msg(event, text="🔑 AI 服务认证失败，请联系管理员检查配置")

        except CircuitOpenError as e:
            log.warning(f"⚡ 熔断器开启: {e.name}")
            await adapter.send_rich_msg(event, text="⚡ 服务暂时不可用，请稍后再试~")

        except NetworkError as e:
            log_error(e, context="处理消息")
            await adapter.send_rich_msg(event, text="🌐 网络连接异常，请稍后重试~")

        except APIError as e:
            log_error(e, context="调用 API")
            await adapter.send_rich_msg(event, text=f"📡 服务异常: {e.user_hint or '请稍后重试'}")

        except OneBotError as e:
            log_error(e, context="发送消息")

        except asyncio.CancelledError:
            log.info("消息处理被取消")
            raise

        except Exception as e:
            log_error(e, context="处理消息", show_traceback=True)
            # 根据 silent_errors 配置决定是否发送错误提示
            if not settings.agent.silent_errors:
                try:
                    await adapter.send_rich_msg(event, text="❌ 处理消息时出错了，请稍后重试")
                except Exception:
                    pass

        finally:
            set_send_message_callback(None)

    # 创建群消息聚合器
    group_aggregator = MessageAggregator(
        initial_wait=10.0,   # 首条消息后等待 10 秒
        extended_wait=15.0,  # 有后续消息时最多等待 15 秒
        on_aggregate=process_aggregated_messages,
    )

    # ==================== 消息处理器 ====================

    @adapter.on_message
    async def handle_message(event: OneBotEvent):
        """处理收到的消息（支持多模态 + 群消息聚合）"""
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
        if event.is_group:
            if allow_all_group:
                should_respond = True
            elif allow_at and adapter.self_id and event.is_at_me(adapter.self_id):
                should_respond = True
        for name in bot_names:
            if name.lower() in plain_text.lower():
                should_respond = True
                break

        if not should_respond:
            return

        log.debug(f"📩 触发响应: {text_desc[:50]}")

        try:
            # 获取上下文（引用消息、合并转发）
            reply_context = None
            forward_summary = None
            forward_image_urls = []

            if parsed.has_reply() and parsed.reply_id:
                reply_context = await fetch_reply_context(adapter, parsed.reply_id)

            if parsed.has_forward() and parsed.forward_id:
                forward_summary, forward_image_urls = await fetch_forward_content(adapter, parsed.forward_id)

            # 防止空消息
            all_image_urls = parsed.image_urls + forward_image_urls
            if not plain_text and not reply_context and not forward_summary and not parsed.has_images() and not forward_image_urls:
                log.warning("空消息，跳过处理")
                if parsed.has_forward():
                    await adapter.send_msg(event, "抱歉，暂时无法读取这条合并转发消息的内容~")
                return

            # ===== 分流：私聊直接处理，群聊走聚合器 =====
            if event.is_private:
                # 私聊：立即处理
                await process_single_message(
                    event=event,
                    parsed=parsed,
                    plain_text=plain_text,
                    sender=sender,
                    reply_context=reply_context,
                    forward_summary=forward_summary,
                    all_image_urls=all_image_urls,
                )
            else:
                # 群聊：添加到聚合器
                pending = PendingMessage(
                    sender_name=sender,
                    sender_qq=event.user_id,
                    message_id=event.message_id or 0,
                    text=plain_text,
                    image_urls=all_image_urls,
                    reply_context=reply_context,
                    reply_to_id=parsed.reply_id,
                    at_targets=parsed.at_targets or [],
                    forward_summary=forward_summary,
                )
                await group_aggregator.add_message(event.group_id, pending, event)

        except Exception as e:
            log_error(e, context="消息预处理", show_traceback=True)

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
        # 刷新聚合器中的待处理消息
        await group_aggregator.flush_all()
        await adapter.stop()
        await mcp_manager.stop()
        log.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
