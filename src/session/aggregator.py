"""消息聚合器 - 防抖和聚合引擎

收到首条消息后启动定时器等待，期间有新消息则延长等待，
超时后将所有消息聚合，一次性发给回调处理。
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Any

from src.session.message import PendingMessage
from src.utils.logger import log

# ==================== 常量 ====================
MIN_REMAINING_WAIT = 0.5


@dataclass
class _Bucket:
    """单个会话的消息聚合桶（内部使用）"""
    messages: list[PendingMessage] = field(default_factory=list)
    first_time: float = 0
    timer: asyncio.Task | None = None
    first_event: Any = None


class MessageAggregator:
    """消息聚合器

    用法::

        agg = MessageAggregator(
            initial_wait=5.0,
            extended_wait=10.0,
            on_aggregate=callback,
        )
        await agg.add_message(group_id, msg, event)
    """

    def __init__(
        self,
        initial_wait: float = 5.0,
        extended_wait: float = 10.0,
        on_aggregate: Callable[[int, list[PendingMessage], Any], Coroutine[Any, Any, None]] | None = None,
        label: str = "群",
        density_enabled: bool = False,
        density_threshold: int = 10,
        density_window: float = 60.0,
        density_cooldown: float = 60.0,
    ):
        self.initial_wait = initial_wait
        self.extended_wait = extended_wait
        self.on_aggregate = on_aggregate
        self.label = label

        self.density_enabled = density_enabled
        self.density_threshold = density_threshold
        self.density_window = density_window
        self.density_cooldown = density_cooldown

        self._buckets: dict[int, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._density_tracker: dict[int, list[float]] = {}

    async def add_message(
        self,
        key: int,
        message: PendingMessage,
        event: Any = None,
        immediate: bool = False,
    ) -> bool:
        """添加消息到聚合桶

        Returns:
            True 如果是新的聚合（首条消息）
        """
        async with self._lock:
            now = time.time()
            is_first = key not in self._buckets

            if is_first:
                self._buckets[key] = _Bucket(first_time=now, first_event=event)
                log.info(f"[{self.label} {key}] 开始聚合，等待 {self.initial_wait}s")

            bucket = self._buckets[key]
            bucket.messages.append(message)

            # 立即模式：跳过等待
            if immediate:
                self._cancel_timer(bucket)
                log.info(f"[{self.label} {key}] @bot 立即响应")
                asyncio.create_task(self._flush(key))
                return is_first

            # 计算等待时间
            wait = self._calc_wait(bucket, now, is_first, key)
            self._restart_timer(bucket, key, wait)

            return is_first

    def _calc_wait(self, bucket: _Bucket, now: float, is_first: bool, key: int) -> float:
        """计算本次应等待的时间"""
        if is_first:
            wait = self.initial_wait
        else:
            remaining = self.extended_wait - (now - bucket.first_time)
            wait = max(MIN_REMAINING_WAIT, remaining)
            log.debug(f"[{self.label} {key}] 追加消息，剩余等待 {wait:.1f}s")

        if self.density_enabled:
            density = self._update_density(key, now)
            if density >= self.density_threshold:
                wait = max(wait, self.density_cooldown)
                log.info(f"[{self.label} {key}] 密度过高 ({density}/{self.density_window:.0f}s)，冷却等待 {wait:.0f}s")

        return wait

    def _update_density(self, key: int, now: float) -> int:
        """更新密度追踪，返回当前窗口内的消息数"""
        tracker = self._density_tracker.setdefault(key, [])
        tracker.append(now)
        self._density_tracker[key] = [t for t in tracker if now - t < self.density_window]
        return len(self._density_tracker[key])

    @staticmethod
    def _cancel_timer(bucket: _Bucket):
        if bucket.timer and not bucket.timer.done():
            bucket.timer.cancel()

    def _restart_timer(self, bucket: _Bucket, key: int, wait: float):
        self._cancel_timer(bucket)
        bucket.timer = asyncio.create_task(self._wait_and_flush(key, wait))

    async def _wait_and_flush(self, key: int, wait: float):
        try:
            await asyncio.sleep(wait)
            await self._flush(key)
        except asyncio.CancelledError:
            pass

    async def _flush(self, key: int):
        async with self._lock:
            bucket = self._buckets.pop(key, None)

        if not bucket or not bucket.messages:
            return

        log.info(f"[{self.label} {key}] 聚合完成，共 {len(bucket.messages)} 条消息")

        if self.on_aggregate:
            try:
                await self.on_aggregate(key, bucket.messages, bucket.first_event)
            except Exception as e:
                log.error(f"聚合回调失败: {e}")

    async def flush_all(self):
        """强制刷新所有桶（用于关闭时）"""
        async with self._lock:
            keys = list(self._buckets.keys())
        for key in keys:
            await self._flush(key)

    def get_pending_count(self, key: int) -> int:
        bucket = self._buckets.get(key)
        return len(bucket.messages) if bucket else 0

    def is_aggregating(self, key: int) -> bool:
        return key in self._buckets


# 重导出：保持 from src.session.aggregator import ... 的兼容性
from src.session.message import PendingMessage  # noqa: F811
from src.session.formatter import (  # noqa: F401
    format_aggregated_messages,
    format_private_aggregated_messages,
    collect_images_from_messages,
)
