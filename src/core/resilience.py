"""
弹性机制 - 重试、熔断、退避

提供:
- retry_with_backoff: 带指数退避的重试装饰器
- CircuitBreaker: 熔断器，防止雪崩
- BackoffStrategy: 退避策略计算
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Callable, TypeVar, Any

from src.core.exceptions import AgentError, RateLimitError, AuthError
from src.utils.logger import log

T = TypeVar("T")


# ==================== 退避策略 ====================

class BackoffStrategy:
    """指数退避策略 (带 jitter)"""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """计算第 N 次重试的等待时间"""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # 添加 ±25% 的随机抖动，避免惊群效应
            delay = delay * (0.75 + random.random() * 0.5)

        return delay


# ==================== 重试装饰器 ====================

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (AgentError,),
    on_retry: Callable[[Exception, int, float], None] | None = None,
):
    """
    带指数退避的异步重试装饰器

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟 (秒)
        max_delay: 最大延迟 (秒)
        retryable_exceptions: 可重试的异常类型
        on_retry: 重试时的回调 (exception, attempt, delay)

    Example:
        @retry_with_backoff(max_retries=3)
        async def fetch_data():
            ...
    """
    backoff = BackoffStrategy(base_delay, max_delay)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except retryable_exceptions as e:
                    last_exception = e

                    # 检查是否可重试
                    if isinstance(e, AgentError) and not e.retryable:
                        log.warning(f"❌ 不可重试的错误: {e}")
                        raise

                    # 最后一次尝试，不再重试
                    if attempt >= max_retries:
                        break

                    # 计算延迟
                    delay = backoff.get_delay(attempt)

                    # 如果异常指定了 retry_after，使用它
                    if isinstance(e, AgentError) and e.retry_after > 0:
                        delay = max(delay, e.retry_after)

                    # 回调
                    if on_retry:
                        on_retry(e, attempt + 1, delay)
                    else:
                        log.warning(
                            f"🔄 重试 {func.__name__} ({attempt + 1}/{max_retries})\n"
                            f"   → 原因: {e}\n"
                            f"   → 等待: {delay:.1f}s"
                        )

                    await asyncio.sleep(delay)

            # 所有重试都失败
            raise last_exception

        return wrapper
    return decorator


# ==================== 熔断器 ====================

class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常，允许请求
    OPEN = "open"          # 熔断，拒绝请求
    HALF_OPEN = "half_open"  # 半开，允许探测


@dataclass
class CircuitBreaker:
    """
    熔断器 - 防止对故障服务的持续调用

    状态转换:
        CLOSED  --失败次数达到阈值--> OPEN
        OPEN    --冷却时间结束-----> HALF_OPEN
        HALF_OPEN --探测成功-------> CLOSED
        HALF_OPEN --探测失败-------> OPEN

    Example:
        breaker = CircuitBreaker(name="llm_api", failure_threshold=5)

        @breaker
        async def call_llm():
            ...
    """

    name: str
    failure_threshold: int = 5      # 触发熔断的失败次数
    recovery_timeout: float = 60.0  # 熔断后的冷却时间 (秒)
    half_open_max_calls: int = 1    # 半开状态允许的探测次数

    # 内部状态
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """获取当前状态 (自动检查是否应该转换到 HALF_OPEN)"""
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                log.info(f"🔓 熔断器 [{self.name}] 进入半开状态，允许探测请求")
        return self._state

    def record_success(self):
        """记录成功调用"""
        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            log.success(f"✅ 熔断器 [{self.name}] 恢复正常")
        elif self._state == CircuitState.CLOSED:
            # 成功时重置失败计数
            self._failure_count = 0

    def record_failure(self, error: Exception):
        """记录失败调用"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            # 半开状态下失败，立即回到 OPEN
            self._state = CircuitState.OPEN
            log.warning(f"⚡ 熔断器 [{self.name}] 探测失败，重新熔断")

        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                log.error(
                    f"⚡ 熔断器 [{self.name}] 触发!\n"
                    f"   → 连续失败 {self._failure_count} 次\n"
                    f"   → 暂停 {self.recovery_timeout}s\n"
                    f"   → 最近错误: {error}"
                )

    def allow_request(self) -> bool:
        """检查是否允许请求"""
        state = self.state  # 触发状态检查

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        # OPEN 状态
        return False

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """作为装饰器使用"""
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            if not self.allow_request():
                remaining = self.recovery_timeout - (time.time() - self._last_failure_time)
                raise CircuitOpenError(
                    name=self.name,
                    message=f"熔断器 [{self.name}] 处于开启状态",
                    retry_after=max(0, remaining),
                )

            try:
                result = await func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:
                self.record_failure(e)
                raise

        return wrapper

    def reset(self):
        """手动重置熔断器"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        log.info(f"🔄 熔断器 [{self.name}] 已手动重置")


@dataclass
class CircuitOpenError(AgentError):
    """熔断器开启时抛出的异常"""
    name: str = ""
    retryable: bool = True
    user_hint: str = "服务暂时不可用，请稍后再试"


# ==================== 预置熔断器实例 ====================

# LLM API 熔断器
llm_circuit = CircuitBreaker(
    name="LLM_API",
    failure_threshold=5,
    recovery_timeout=60.0,
)

# OneBot 连接熔断器
onebot_circuit = CircuitBreaker(
    name="OneBot",
    failure_threshold=10,
    recovery_timeout=30.0,
)

# 媒体下载熔断器
media_circuit = CircuitBreaker(
    name="Media",
    failure_threshold=8,
    recovery_timeout=30.0,
)
