"""
TG 资讯监控模块

职责链:
  TG 群消息
    → NewsMonitor._on_raw()        # 过滤 + 聚合窗口
      → NewsMonitor._flush()       # Agent 摘要（可选）
        → BroadcastDispatcher      # 推送到 TG 自己 + QQ 群 / 私聊

配置示例（config.yaml）:
    telegram:
      enabled: true
      session_name: tg_session
      monitor:
        groups: ["some_news_channel", -1001234567890]
        keywords: []
        min_length: 20
        aggregate_seconds: 60
        cooldown_seconds: 300
        summarize: true
      broadcast:
        tg_self: true
        qq_groups: [123456789]
        qq_users: []
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.utils.logger import log

if TYPE_CHECKING:
    from src.adapters.telegram import TelegramAdapter
    from src.adapters.onebot import OneBotAdapter
    from src.agent.graph import QQAgent


# =====================================================================
# 数据结构
# =====================================================================

@dataclass
class _GroupBuffer:
    """单个 TG 群的消息缓冲区"""
    messages: list[str] = field(default_factory=list)
    timer_task: asyncio.Task | None = None
    last_broadcast: float = 0.0   # 上次成功推送的时间戳


# =====================================================================
# BroadcastDispatcher — 纯推送，不含业务判断
# =====================================================================

class BroadcastDispatcher:
    """
    将文本并发推送到所有配置的目标：
      - TG Saved Messages（给自己）
      - 指定 QQ 群
      - 指定 QQ 私聊
    """

    def __init__(
        self,
        tg_adapter: "TelegramAdapter",
        onebot_adapter: "OneBotAdapter | None",
        cfg: dict,
    ):
        self._tg = tg_adapter
        self._ob = onebot_adapter
        self._tg_self: bool = cfg.get("tg_self", True)
        self._qq_groups: list[int] = cfg.get("qq_groups", [])
        self._qq_users: list[int] = cfg.get("qq_users", [])

    async def dispatch(self, text: str) -> None:
        """并发推送到所有目标，单个失败不影响其他目标。"""
        tasks: list[asyncio.Task] = []

        if self._tg_self:
            tasks.append(asyncio.create_task(self._send_tg_self(text)))

        if self._ob:
            for gid in self._qq_groups:
                tasks.append(asyncio.create_task(self._send_qq_group(gid, text)))
            for uid in self._qq_users:
                tasks.append(asyncio.create_task(self._send_qq_user(uid, text)))

        if not tasks:
            log.warning("BroadcastDispatcher: 没有配置任何推送目标，消息丢弃")
            return

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log.warning(f"BroadcastDispatcher: 推送任务 {i} 失败: {r}")

    async def _send_tg_self(self, text: str) -> None:
        await self._tg.send_to_saved(text)
        log.info("📨 已推送到 TG Saved Messages")

    async def _send_qq_group(self, group_id: int, text: str) -> None:
        if self._ob is None:
            return
        await self._ob.send_group_msg(group_id, text)
        log.info(f"📨 已推送到 QQ 群 {group_id}")

    async def _send_qq_user(self, user_id: int, text: str) -> None:
        if self._ob is None:
            return
        await self._ob.send_private_msg(user_id, text)
        log.info(f"📨 已推送到 QQ 私聊 {user_id}")


# =====================================================================
# NewsMonitor — 监听 + 过滤 + 聚合 + 摘要
# =====================================================================

class NewsMonitor:
    """
    监听指定 TG 群/频道的消息，聚合后调用 Agent 生成摘要，再通过
    BroadcastDispatcher 推送到配置的目标。

    不含任何 TG / QQ 发送逻辑，完全委托给 BroadcastDispatcher。
    """

    def __init__(
        self,
        tg_adapter: "TelegramAdapter",
        onebot_adapter: "OneBotAdapter | None",
        agent: "QQAgent | None",
        monitor_cfg: dict,
        broadcast_cfg: dict,
        persona_prompt: str = "",
    ):
        self._tg = tg_adapter
        self._agent = agent
        self._dispatcher = BroadcastDispatcher(tg_adapter, onebot_adapter, broadcast_cfg)

        # 监听配置
        self._watch_groups: list[int | str] = monitor_cfg.get("groups", [])
        self._keywords: list[str] = [k.lower() for k in monitor_cfg.get("keywords", [])]
        self._min_length: int = monitor_cfg.get("min_length", 20)
        self._aggregate_sec: float = float(monitor_cfg.get("aggregate_seconds", 60))
        self._cooldown_sec: float = float(monitor_cfg.get("cooldown_seconds", 300))
        self._summarize: bool = monitor_cfg.get("summarize", True)
        self._max_buffer_messages: int = int(monitor_cfg.get("max_buffer_messages", 50))
        self._dedupe_seconds: float = float(monitor_cfg.get("dedupe_seconds", 300))
        self._store_raw: bool = bool(monitor_cfg.get("store_raw", True))
        self._persona_prompt = persona_prompt or str(monitor_cfg.get("persona_prompt", "") or "")

        # 运行时状态
        self._buffers: dict[int, _GroupBuffer] = {}   # chat_id -> buffer
        self._watch_ids: dict[int, str] = {}          # chat_id -> 频道名
        self._seen_messages: dict[str, float] = {}
        self._running = False
        self._event_count = 0

    # ===================== 生命周期 =====================

    async def start(self) -> None:
        """解析监听目标，注册处理器，启动 TG 适配器。"""
        self._running = True

        log.info(f"NewsMonitor 启动，监听目标={self._watch_groups}")
        await self._resolve_watch_groups()
        log.info(f"NewsMonitor 监听解析完成：{self._watch_ids}")

        # 注册 Telethon 消息处理器
        from telethon import events

        if self._watch_ids:
            chat_list = list(self._watch_ids)
            log.info(f"NewsMonitor: 将监听以下 chat_id: {chat_list}")
            # incoming=True 确保能收到频道消息，outgoing=False 忽略自己发的
            self._tg.client.add_event_handler(
                self._on_raw,
                events.NewMessage(chats=chat_list, incoming=True, outgoing=False)
            )
        else:
            log.warning("NewsMonitor: 未指定监听群，将监听所有消息")
            self._tg.client.add_event_handler(
                self._on_raw,
                events.NewMessage(incoming=True, outgoing=False)
            )

        log.success(
            f"NewsMonitor 已启动，监听 {len(self._watch_ids)} 个群/频道，"
            f"聚合窗口={self._aggregate_sec}s，冷却={self._cooldown_sec}s"
        )

    async def stop(self) -> None:
        """取消所有待处理的聚合定时器。"""
        self._running = False
        for buf in self._buffers.values():
            if buf.timer_task and not buf.timer_task.done():
                buf.timer_task.cancel()
        log.info("NewsMonitor 已停止")

    # ===================== 核心处理流 =====================

    async def _on_raw(self, event) -> None:
        """Telethon 事件回调：过滤 → 入缓冲区 → 重置聚合定时器。"""
        self._event_count += 1
        chat_id: int = event.chat_id

        # Telegram 频道 ID 转换：-1002329614234 → 2329614234
        # 如果是长格式（-100 开头），转换成短格式
        normalized_id = chat_id
        if str(chat_id).startswith("-100"):
            normalized_id = int(str(chat_id)[4:])  # 去掉 -100 前缀

        channel_name = self._watch_ids.get(normalized_id, f"未知频道({chat_id})")
        log.info(f"[TG] 收到第 {self._event_count} 条消息: {channel_name}, text_len={len(getattr(event.message, 'text', '') or '')}")

        # 仅处理配置的群（使用转换后的 ID）
        if self._watch_ids and normalized_id not in self._watch_ids:
            return

        # 后续使用 normalized_id
        chat_id = normalized_id

        # 取消息文本
        text: str = getattr(event.message, "text", "") or ""
        if not text:
            log.debug(f"[TG] chat_id {chat_id} 消息无文本，跳过")
            return

        # 长度过滤
        if len(text) < self._min_length:
            log.debug(f"[TG] chat_id {chat_id} 消息长度 {len(text)} < {self._min_length}，跳过")
            return

        # 关键词过滤（有关键词时，消息必须包含其中之一）
        if self._keywords:
            text_lower = text.lower()
            if not any(kw in text_lower for kw in self._keywords):
                log.debug(f"[TG] chat_id {chat_id} 消息不包含关键词，跳过")
                return

        text_clean = text.strip()
        if self._is_duplicate(chat_id, text_clean):
            log.debug(f"[TG] chat_id {chat_id} 重复消息，跳过")
            return

        # 写入本地结构化存储 (用于后续知识库向量化)
        if self._store_raw:
            self._store_raw_message(chat_id, text_clean)

        # 进入缓冲区 (发送前先清理前后空白符)
        if chat_id not in self._buffers:
            self._buffers[chat_id] = _GroupBuffer()

        buf = self._buffers[chat_id]
        buf.messages.append(text_clean)
        if len(buf.messages) > self._max_buffer_messages:
            overflow = len(buf.messages) - self._max_buffer_messages
            del buf.messages[:overflow]
            log.warning(f"NewsMonitor: chat_id={chat_id} 缓冲超过上限，丢弃最旧 {overflow} 条")

        # 重置聚合定时器
        if buf.timer_task and not buf.timer_task.done():
            buf.timer_task.cancel()

        buf.timer_task = asyncio.create_task(
            self._flush_after(chat_id, self._aggregate_sec)
        )
        channel_name = self._watch_ids.get(chat_id, str(chat_id))
        log.info(f"NewsMonitor: 获取到 TG @{channel_name} 的资讯，已加入缓冲 (缓冲中 {len(buf.messages)} 条)")

    def _is_duplicate(self, chat_id: int, text: str) -> bool:
        now = time.time()
        expire_before = now - self._dedupe_seconds
        self._seen_messages = {
            key: ts for key, ts in self._seen_messages.items()
            if ts >= expire_before
        }
        key = f"{chat_id}:{hash(text[:1000])}"
        if key in self._seen_messages:
            return True
        self._seen_messages[key] = now
        return False

    @staticmethod
    def _store_raw_message(chat_id: int, text: str) -> None:
        import datetime
        from pathlib import Path

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")

        store_dir = Path("data/tg_news")
        store_dir.mkdir(parents=True, exist_ok=True)
        store_file = store_dir / f"{date_str}.txt"

        record = f"[{date_str} {time_str}] [ChatID:{chat_id}]\n{text}\n===\n\n"
        with open(store_file, "a", encoding="utf-8") as f:
            f.write(record)

    async def _flush_after(self, chat_id: int, delay: float) -> None:
        """等待聚合窗口到期后 flush。"""
        try:
            await asyncio.sleep(delay)
            await self._flush(chat_id)
        except asyncio.CancelledError:
            pass  # 被新消息重置，正常情况

    async def _flush(self, chat_id: int) -> None:
        """聚合窗口到期：摘要 → 冷却检查 → 推送。"""
        buf = self._buffers.get(chat_id)
        if not buf or not buf.messages:
            log.warning(f"[TG] flush 被调用但缓冲区为空: chat_id={chat_id}")
            return

        messages = buf.messages.copy()
        buf.messages.clear()

        log.info(f"[TG] 开始 flush: chat_id={chat_id}, 消息数={len(messages)}")

        # 冷却检查
        now = time.time()
        if now - buf.last_broadcast < self._cooldown_sec:
            remaining = self._cooldown_sec - (now - buf.last_broadcast)
            log.info(f"[TG] 冷却中，跳过推送（剩余 {remaining:.0f}s）")
            return

        combined = "\n---\n".join(messages)
        log.info(f"[TG] 聚合 {len(messages)} 条消息，准备推送")

        # 冷却时间更新（无论成功与否都要算作已触发）
        buf.last_broadcast = time.time()

        # 1. 如果没有开启总结，或者没有 Agent，就直接群发原文
        if not self._summarize or not self._agent:
            await self._dispatcher.dispatch(combined)
            return

        # 2. 开启了总结，针对每一个目标（群/人）分别带入他们的上下文进行独立的"分享和锐评"
        tasks = []
        for group_id in self._dispatcher._qq_groups:
            session_id = f"tg_news_to_group_{group_id}"
            tasks.append(self._generate_and_send(chat_id, combined, session_id, target_group=group_id))

        for user_id in self._dispatcher._qq_users:
            session_id = f"tg_news_to_private_{user_id}"
            tasks.append(self._generate_and_send(chat_id, combined, session_id, target_user=user_id))

        if self._dispatcher._tg_self:
            # 对于 TG 私人收藏，不需要带杂乱的上下文，直接做标准总结
            session_id = f"tg_monitor_saved_{chat_id}"
            tasks.append(self._generate_and_send(chat_id, combined, session_id, target_tg_saved=True))

        # 并发执行所有任务
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _generate_and_send(
        self, chat_id: int, text: str, session_id: str,
        target_group: int | None = None,
        target_user: int | None = None,
        target_tg_saved: bool = False
    ):
        """让 AI 用指定的 session_id 进行思考，并推送到特定位置"""
        import asyncio
        import datetime
        from src.agent.tools import set_send_message_callback

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        header = f"📰 [来自TG实时资讯 | {now_str}]\n"

        persona = self._persona_prompt.strip()
        persona_block = f"【当前角色风格】\n{persona}\n\n" if persona else ""
        prompt = (
            f"{persona_block}"
            f"【系统后台提供的数据】刚才在 {now_str}，系统从 Telegram 资讯渠道拉取到了以下几条最新消息：\n\n{text}\n\n"
            f"【你的任务】\n"
            f"像群里正常聊天一样，挑你觉得有信息量、有趣、或和当前群聊气质相关的 1-3 条资讯分享。\n\n"
            f"【具体要求】\n"
            f"- 用自己的话概括核心内容和重要数字，必要时自然提到来源或链接。\n"
            f"- 可以有主观点评，但不要编造原文没有的信息。\n"
            f"- 不要强行逐条回应，不感兴趣或低价值的信息可以忽略。\n"
            f"- 不要写成新闻稿或编号列表，整体保持短、清楚、适合聊天窗口阅读。\n"
        )

        # 构建 send_message 实时回调 —— 和 pipeline.py 同样的模式
        # Agent 调用 send_message 工具时，回调立即触发实际发送
        loop = asyncio.get_running_loop()
        ob = self._dispatcher._ob
        tg = self._dispatcher._tg

        def realtime_callback(cmd: dict):
            send_text = cmd.get("text", "")
            if not send_text:
                return
            full_text = header + send_text

            if target_group and ob:
                asyncio.run_coroutine_threadsafe(ob.send_group_msg(target_group, full_text), loop)
            elif target_user and ob:
                asyncio.run_coroutine_threadsafe(ob.send_private_msg(target_user, full_text), loop)
            elif target_tg_saved and tg:
                asyncio.run_coroutine_threadsafe(tg.send_to_saved(full_text), loop)

        set_send_message_callback(realtime_callback)
        try:
            await self._agent.chat(
                message=prompt,
                session_id=session_id,
                user_name="内部资讯流",
            )
            log.info(f"[TG] 资讯推送完成: session={session_id}")
        except Exception as e:
            log.warning(f"[TG] session={session_id} 生成锐评失败，回退到原文: {e}")
            fallback = header + f"（AI 锐评生成失败，以下为原文）\n\n{text}"
            try:
                if target_group and ob:
                    await ob.send_group_msg(target_group, fallback)
                elif target_user and ob:
                    await ob.send_private_msg(target_user, fallback)
                elif target_tg_saved and tg:
                    await tg.send_to_saved(fallback)
            except Exception as send_err:
                log.error(f"[TG] 回退原文发送也失败: {send_err}")
        finally:
            set_send_message_callback(None)

    # ===================== 辅助 =====================

    async def _resolve_watch_groups(self) -> None:
        """将 config 中的 username/id 解析成 chat_id（int）。"""
        if not self._watch_groups:
            log.warning("NewsMonitor: monitor.groups 为空，将监听所有群消息")
            return

        log.info(f"NewsMonitor: 开始解析 {len(self._watch_groups)} 个监听目标...")
        for g in self._watch_groups:
            try:
                entity = await self._tg.resolve_chat(g)
                self._watch_ids[entity.id] = str(g)
                log.success(f"NewsMonitor: ✓ {g} → chat_id={entity.id}")
            except Exception as e:
                log.error(f"NewsMonitor: ✗ 无法解析 {g}: {e}")
