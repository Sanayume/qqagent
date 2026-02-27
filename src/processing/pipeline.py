"""消息处理管线

从 bot.py 提取的消息处理方法：单条消息、聚合消息、文件上传、Agent 调用。
"""

import asyncio
import time

from src.adapters.onebot import OneBotAdapter, OneBotEvent
from src.agent.graph import QQAgent
from src.agent.tools import set_send_message_callback, set_download_file_callback
from src.core.onebot import parse_segments, make_text_description, get_file_descriptions, format_file_size
from src.core.llm_message import build_multimodal_message, build_rich_context_message
from src.core.message_fetch import download_message_images
from src.core.exceptions import (
    NetworkError, APIError, RateLimitError, AuthError, OneBotError,
)
from src.core.resilience import CircuitOpenError
from src.core.context import AppContext
from src.session.aggregator import (
    PendingMessage,
    format_aggregated_messages, format_private_aggregated_messages,
    collect_images_from_messages,
)
from src.utils.logger import log, log_error


class MessagePipeline:
    def __init__(self, adapter: OneBotAdapter, agent: QQAgent, ctx: AppContext, settings, audio):
        self.adapter = adapter
        self.agent = agent
        self.ctx = ctx
        self.settings = settings
        self.audio = audio  # AudioProcessor
        self._group_aggregator = None
        self._private_aggregator = None

    async def process_single_message(
        self,
        event: OneBotEvent,
        parsed,
        plain_text: str,
        sender: str,
        reply_context: str | None,
        forward_summary: str | None,
        all_image_urls: list[str],
        audio_path: str | None = None,
    ):
        """处理单条消息（私聊或未聚合的群消息）"""
        session_id = self.adapter.session_manager.get_session_id(
            user_id=event.user_id,
            group_id=event.group_id if event.is_group else None,
            is_private=event.is_private,
        )

        images, image_paths = await download_message_images(all_image_urls, max_count=5) if all_image_urls else ([], [])
        file_descriptions = get_file_descriptions(parsed) if parsed.has_files() else None

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
            file_descriptions=file_descriptions,
            image_paths=image_paths if image_paths else None,
            timestamp=event.time,
        )

        audio_clips = None
        if audio_path and self.audio.should_use_native_audio():
            from pathlib import Path
            p = Path(audio_path)
            if p.exists():
                data = p.read_bytes()
                fmt = p.suffix.lstrip(".").lower()
                converted = self.audio.try_convert_audio(data, fmt)
                if converted:
                    audio_clips = [converted]

        llm_message = build_multimodal_message(text=context_text, images=images, audio=audio_clips)
        await self._invoke_agent(event, session_id, llm_message)

    async def process_aggregated_messages(
        self,
        group_id: int,
        messages: list[PendingMessage],
        first_event,
    ):
        """处理聚合后的群消息"""
        if not messages or not first_event:
            return

        log.info(f"处理聚合消息: 群 {group_id}, {len(messages)} 条")

        session_id = self.adapter.session_manager.get_session_id(
            user_id=first_event.user_id,
            group_id=group_id,
            is_private=False,
        )

        all_image_urls = collect_images_from_messages(messages)
        images, image_paths = await download_message_images(all_image_urls, max_count=5) if all_image_urls else ([], [])

        context_text = format_aggregated_messages(messages, group_id, image_paths)
        audio_clips = await self.audio.collect_audio_from_messages(messages) if self.audio.should_use_native_audio() else []
        llm_message = build_multimodal_message(text=context_text, images=images, audio=audio_clips or None)

        await self._invoke_agent(first_event, session_id, llm_message)

    async def process_private_aggregated_messages(
        self,
        user_id: int,
        messages: list[PendingMessage],
        first_event,
    ):
        """处理聚合后的私聊消息"""
        if not messages or not first_event:
            return

        log.info(f"处理私聊聚合消息: 用户 {user_id}, {len(messages)} 条")

        session_id = self.adapter.session_manager.get_session_id(
            user_id=user_id,
            group_id=None,
            is_private=True,
        )

        all_image_urls = collect_images_from_messages(messages)
        images, image_paths = await download_message_images(all_image_urls, max_count=5) if all_image_urls else ([], [])

        context_text = format_private_aggregated_messages(messages, image_paths)
        audio_clips = await self.audio.collect_audio_from_messages(messages) if self.audio.should_use_native_audio() else []
        llm_message = build_multimodal_message(text=context_text, images=images, audio=audio_clips or None)

        await self._invoke_agent(first_event, session_id, llm_message)

    def set_aggregators(self, group_agg, private_agg):
        """设置聚合器引用（避免循环依赖）"""
        self._group_aggregator = group_agg
        self._private_aggregator = private_agg

    async def handle_file_upload(self, event: OneBotEvent):
        """处理文件上传事件（群文件/私聊文件）"""
        file_info = event.file
        if not file_info:
            return

        file_name = file_info.get("name", "未知文件")
        file_size = file_info.get("size", 0)
        file_url = file_info.get("url", "")

        is_group = event.notice_type == "group_upload"
        chat_type = "群聊" if is_group else "私聊"

        sender = str(event.user_id)
        if is_group and event.group_id:
            try:
                info = await self.adapter.get_group_member_info(event.group_id, event.user_id)
                if info.get("status") == "ok":
                    sender = info.get("data", {}).get("nickname", sender)
            except Exception as e:
                log.debug(f"Failed to get group member info: {e}")
        else:
            try:
                info = await self.adapter.get_stranger_info(event.user_id)
                if info.get("status") == "ok":
                    sender = info.get("data", {}).get("nickname", sender)
            except Exception as e:
                log.debug(f"Failed to get stranger info: {e}")

        log.info(f"[{chat_type} {event.group_id or event.user_id}] {sender} 上传文件: {file_name}")
        size_str = format_file_size(file_size)

        if file_url:
            file_desc = f"[文件: {file_name}, 大小: {size_str}, URL: {file_url}]"
        else:
            file_desc = f"[文件: {file_name}, 大小: {size_str}]"

        pending = PendingMessage(
            sender_name=sender,
            sender_qq=event.user_id,
            message_id=0,
            text="",
            file_descriptions=[file_desc],
            timestamp=float(event.time) if event.time else time.time(),
        )

        if is_group and event.group_id:
            await self._group_aggregator.add_message(event.group_id, pending, event)
            return

        if self._private_aggregator:
            await self._private_aggregator.add_message(event.user_id, pending, event)
        else:
            context_text = build_rich_context_message(
                main_text="",
                sender_name=sender,
                sender_qq=event.user_id,
                group_id=None,
                file_descriptions=[file_desc],
                timestamp=event.time,
            )
            llm_message = build_multimodal_message(text=context_text, images=[])
            session_id = self.adapter.session_manager.get_session_id(
                user_id=event.user_id, group_id=None, is_private=True,
            )
            await self._invoke_agent(event, session_id, llm_message)

    def _setup_callbacks(self, event: OneBotEvent, loop):
        """创建并注册实时发送和文件下载回调"""

        def realtime_callback(cmd: dict):
            delay_minutes = cmd.get("delay_minutes", 0)

            if delay_minutes > 0:
                async def _delayed_send():
                    delay_seconds = delay_minutes * 60
                    log.info(f"定时发送已安排: {delay_minutes}分钟后发送")
                    await asyncio.sleep(delay_seconds)
                    try:
                        await self.adapter.send_rich_msg(
                            event=event,
                            text=cmd.get("text", ""),
                            image=cmd.get("image", ""),
                            record=cmd.get("record", ""),
                            at_users=cmd.get("at_users"),
                            reply_to=cmd.get("reply_to", 0),
                        )
                        log.info("定时消息发送成功")
                    except Exception as e:
                        log.warning(f"定时消息发送失败: {e}")

                asyncio.run_coroutine_threadsafe(_delayed_send(), loop)
            else:
                asyncio.run_coroutine_threadsafe(
                    self.adapter.send_rich_msg(
                        event=event,
                        text=cmd.get("text", ""),
                        image=cmd.get("image", ""),
                        record=cmd.get("record", ""),
                        at_users=cmd.get("at_users"),
                        reply_to=cmd.get("reply_to", 0),
                    ),
                    loop,
                )

        def download_file_callback(file_id: str) -> dict | None:
            future = asyncio.run_coroutine_threadsafe(
                self.adapter.get_file(file_id), loop,
            )
            try:
                return future.result(timeout=60)
            except Exception as e:
                log.warning(f"下载文件失败: {e}")
                return None

        set_send_message_callback(realtime_callback)
        set_download_file_callback(download_file_callback)

    async def _handle_agent_error(self, event: OneBotEvent, error: Exception):
        """统一处理 Agent 调用中的异常"""
        if isinstance(error, RateLimitError):
            log_error(error, context="调用 LLM")
            await self.adapter.send_rich_msg(event, text="请求太频繁了，请稍后再试~")
        elif isinstance(error, AuthError):
            log_error(error, context="调用 LLM")
            await self.adapter.send_rich_msg(event, text="AI 服务认证失败，请联系管理员检查配置")
        elif isinstance(error, CircuitOpenError):
            log.warning(f"熔断器开启: {error.name}")
            await self.adapter.send_rich_msg(event, text="服务暂时不可用，请稍后再试~")
        elif isinstance(error, NetworkError):
            log_error(error, context="处理消息")
            await self.adapter.send_rich_msg(event, text="网络连接异常，请稍后重试~")
        elif isinstance(error, APIError):
            log_error(error, context="调用 API")
            await self.adapter.send_rich_msg(event, text=f"服务异常: {error.user_hint or '请稍后重试'}")
        elif isinstance(error, OneBotError):
            log_error(error, context="发送消息")
        else:
            log_error(error, context="处理消息", show_traceback=True)
            self.ctx.stats.record_error()
            if not self.settings.agent.silent_errors:
                try:
                    await self.adapter.send_rich_msg(event, text="处理消息时出错了，请稍后重试")
                except Exception as e:
                    log.debug(f"Failed to send error message to user: {e}")

    async def _invoke_agent(self, event: OneBotEvent, session_id: str, llm_message):
        """调用 Agent 并处理响应"""
        loop = asyncio.get_running_loop()
        self._setup_callbacks(event, loop)

        try:
            await self.agent.chat(
                message=llm_message,
                session_id=session_id,
                user_id=event.user_id,
                group_id=event.group_id,
                user_name=event.sender_nickname,
            )
            log.info("Agent 处理完成")
            self.ctx.stats.record_message()

        except asyncio.CancelledError:
            log.info("消息处理被取消")
            raise

        except Exception as e:
            await self._handle_agent_error(event, e)

        finally:
            set_send_message_callback(None)
            set_download_file_callback(None)
