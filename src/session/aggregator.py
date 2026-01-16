"""
消息聚合器 - 群聊消息防抖和聚合

功能：
- 群聊中第一条消息到达时，启动 5 秒等待
- 如果 5 秒内有新消息，延长等待到 10 秒
- 超时后将所有消息聚合，一次性发给 Agent

这样做的好处：
- 避免用户连续发消息时机器人频繁响应
- 让 Agent 看到完整的对话上下文
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any

from src.utils.logger import log


@dataclass
class PendingMessage:
    """待聚合的单条消息"""
    sender_name: str
    sender_qq: int
    message_id: int
    text: str
    image_urls: list[str] = field(default_factory=list)
    reply_context: str | None = None  # 引用消息的内容
    reply_to_id: int | None = None    # 引用的消息 ID
    at_targets: list[str] = field(default_factory=list)
    forward_summary: str | None = None
    timestamp: float = field(default_factory=time.time)

    def format(self) -> str:
        """格式化为可读文本"""
        parts = []

        # 发送者信息
        header = f"【{self.sender_name} (QQ:{self.sender_qq})】"

        # 引用信息
        if self.reply_context:
            if self.reply_to_id:
                parts.append(f"↩️ 引用消息ID {self.reply_to_id}: 「{self.reply_context}」")
            else:
                parts.append(f"↩️ 引用: 「{self.reply_context}」")

        # 消息正文
        if self.text:
            parts.append(self.text)
        elif self.image_urls:
            parts.append(f"[发送了 {len(self.image_urls)} 张图片]")

        # @ 目标
        if self.at_targets:
            parts.append(f"(@了: {', '.join(self.at_targets)})")

        # 转发摘要
        if self.forward_summary:
            # 转发内容较长，单独一段
            parts.append(f"[转发消息]\n{self.forward_summary}")

        content = "\n".join(parts) if parts else "(空消息)"
        return f"{header}\n{content}"


@dataclass
class AggregationBucket:
    """单个群的消息聚合桶"""
    group_id: int
    messages: list[PendingMessage] = field(default_factory=list)
    first_message_time: float = 0
    last_message_time: float = 0
    timer_task: asyncio.Task | None = None
    # 保存原始事件，用于回复
    first_event: Any = None


class MessageAggregator:
    """
    消息聚合器

    使用方式：
        aggregator = MessageAggregator(
            initial_wait=5.0,
            extended_wait=10.0,
            on_aggregate=handle_aggregated_messages,
        )

        # 在消息处理器中
        await aggregator.add_message(group_id, pending_msg, event)

    参数：
        initial_wait: 首次消息后的等待时间 (秒)
        extended_wait: 有后续消息时的最大等待时间 (秒)
        on_aggregate: 聚合完成后的回调函数
    """

    def __init__(
        self,
        initial_wait: float = 5.0,
        extended_wait: float = 10.0,
        on_aggregate: Callable[[int, list[PendingMessage], Any], Coroutine[Any, Any, None]] | None = None,
    ):
        self.initial_wait = initial_wait
        self.extended_wait = extended_wait
        self.on_aggregate = on_aggregate

        # group_id -> AggregationBucket
        self._buckets: dict[int, AggregationBucket] = {}
        self._lock = asyncio.Lock()

    async def add_message(
        self,
        group_id: int,
        message: PendingMessage,
        event: Any = None,
    ) -> bool:
        """
        添加消息到聚合桶

        Args:
            group_id: 群号
            message: 待聚合的消息
            event: 原始事件对象（用于后续回复）

        Returns:
            True 如果是新的聚合（首条消息）
            False 如果是追加到现有聚合
        """
        async with self._lock:
            now = time.time()
            is_first = False

            if group_id not in self._buckets:
                # 新的聚合桶
                bucket = AggregationBucket(
                    group_id=group_id,
                    first_message_time=now,
                    first_event=event,
                )
                self._buckets[group_id] = bucket
                is_first = True
                log.info(f"📥 群 {group_id}: 开始消息聚合，等待 {self.initial_wait}s")
            else:
                bucket = self._buckets[group_id]

            # 添加消息
            bucket.messages.append(message)
            bucket.last_message_time = now

            # 计算等待时间
            elapsed = now - bucket.first_message_time
            if is_first:
                # 首条消息：等待 initial_wait
                wait_time = self.initial_wait
            else:
                # 后续消息：延长到 extended_wait，但不超过剩余时间
                remaining = self.extended_wait - elapsed
                wait_time = max(0.5, remaining)  # 至少等 0.5s
                log.debug(f"📥 群 {group_id}: 追加消息，剩余等待 {wait_time:.1f}s")

            # 取消旧定时器
            if bucket.timer_task and not bucket.timer_task.done():
                bucket.timer_task.cancel()

            # 启动新定时器
            bucket.timer_task = asyncio.create_task(
                self._wait_and_flush(group_id, wait_time)
            )

            return is_first

    async def _wait_and_flush(self, group_id: int, wait_time: float):
        """等待后触发聚合"""
        try:
            await asyncio.sleep(wait_time)
            await self._flush(group_id)
        except asyncio.CancelledError:
            # 定时器被取消（有新消息到达）
            pass

    async def _flush(self, group_id: int):
        """触发聚合回调"""
        async with self._lock:
            bucket = self._buckets.pop(group_id, None)

        if not bucket or not bucket.messages:
            return

        log.info(f"📤 群 {group_id}: 聚合完成，共 {len(bucket.messages)} 条消息")

        if self.on_aggregate:
            try:
                await self.on_aggregate(group_id, bucket.messages, bucket.first_event)
            except Exception as e:
                log.error(f"聚合回调失败: {e}")

    async def flush_all(self):
        """强制刷新所有桶（用于关闭时）"""
        async with self._lock:
            group_ids = list(self._buckets.keys())

        for group_id in group_ids:
            await self._flush(group_id)

    def get_pending_count(self, group_id: int) -> int:
        """获取群的待处理消息数"""
        bucket = self._buckets.get(group_id)
        return len(bucket.messages) if bucket else 0

    def is_aggregating(self, group_id: int) -> bool:
        """检查群是否正在聚合中"""
        return group_id in self._buckets


def format_aggregated_messages(
    messages: list[PendingMessage],
    group_id: int,
) -> str:
    """
    格式化聚合后的消息为 LLM 可读的文本

    Args:
        messages: 聚合的消息列表
        group_id: 群号

    Returns:
        格式化的文本

    Example output:
        [群聊消息汇总]
        群号: 123456
        消息数: 3
        时间跨度: 8.2 秒

        ---
        【张三 (QQ:111111)】
        你好啊

        ---
        【李四 (QQ:222222)】
        ↩️ 引用: 「你好啊」
        在吗？

        ---
        【张三 (QQ:111111)】
        [发送了 1 张图片]
    """
    if not messages:
        return "[无消息]"

    # 计算时间跨度
    first_time = messages[0].timestamp
    last_time = messages[-1].timestamp
    time_span = last_time - first_time

    parts = []

    # 头部信息
    header_lines = [
        "[群聊消息汇总]",
        f"群号: {group_id}",
        f"消息数: {len(messages)}",
    ]
    if time_span > 0.1:
        header_lines.append(f"时间跨度: {time_span:.1f} 秒")

    parts.append("\n".join(header_lines))

    # 每条消息
    for msg in messages:
        parts.append("---")
        parts.append(msg.format())

    return "\n\n".join(parts)


def collect_images_from_messages(messages: list[PendingMessage]) -> list[str]:
    """从聚合消息中收集所有图片 URL"""
    urls = []
    for msg in messages:
        urls.extend(msg.image_urls)
    return urls
