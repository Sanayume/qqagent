"""Logging configuration using loguru + 人性化错误格式化"""

import sys
import traceback
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.core.exceptions import AgentError


def setup_logger(level: str = "INFO", log_file: str | None = None):
    """Configure loguru logger

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional file path for log output
    """
    # Remove default handler
    logger.remove()

    # Console handler with colors - 简化格式，更易读
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> <level>{level: <7}</level> <level>{message}</level>",
        colorize=True,
    )

    # File handler if specified
    if log_file:
        logger.add(
            log_file,
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
        )

    return logger


# Default logger instance
log = logger


# ==================== 人性化错误格式化 ====================

# 错误图标映射
ERROR_ICONS = {
    "NetworkError": "🌐",
    "ConnectionError": "🔌",
    "TimeoutError": "⏱️",
    "APIError": "📡",
    "RateLimitError": "🚦",
    "AuthError": "🔑",
    "TokenExhaustedError": "💰",
    "MediaError": "🖼️",
    "DownloadError": "⬇️",
    "OneBotError": "🤖",
    "CircuitOpenError": "⚡",
}


def format_error(
    error: Exception,
    context: str = "",
    show_traceback: bool = False,
) -> str:
    """
    格式化错误为人性化的日志消息

    Args:
        error: 异常对象
        context: 错误发生的上下文描述
        show_traceback: 是否显示完整堆栈

    Returns:
        格式化的错误消息

    Example:
        >>> log.error(format_error(e, context="处理消息"))
        ❌ 处理消息失败 [RateLimitError]
           → 原因: 请求过于频繁
           → 建议: 等待 30 秒后重试
    """
    error_type = type(error).__name__
    icon = ERROR_ICONS.get(error_type, "❌")

    lines = []

    # 标题行
    title = f"{icon} {context}失败" if context else f"{icon} 错误"
    lines.append(f"{title} [{error_type}]")

    # 原因
    lines.append(f"   → 原因: {error}")

    # 如果是自定义异常，显示更多信息
    try:
        from src.core.exceptions import AgentError
        if isinstance(error, AgentError):
            if error.user_hint:
                lines.append(f"   → 建议: {error.user_hint}")
            if error.retry_after > 0:
                lines.append(f"   → 重试: {error.retry_after:.0f}s 后")
            if error.cause:
                lines.append(f"   → 底层: {type(error.cause).__name__}: {error.cause}")
    except ImportError:
        pass

    # 堆栈 (可选)
    if show_traceback:
        tb = traceback.format_exc()
        # 只取最后几行
        tb_lines = tb.strip().split("\n")
        if len(tb_lines) > 6:
            tb_lines = ["   ..."] + tb_lines[-5:]
        lines.append("   → 堆栈:")
        for tb_line in tb_lines:
            lines.append(f"      {tb_line}")

    return "\n".join(lines)


def log_error(
    error: Exception,
    context: str = "",
    show_traceback: bool = False,
):
    """记录格式化的错误日志"""
    log.error(format_error(error, context, show_traceback))


def log_retry(
    error: Exception,
    attempt: int,
    max_attempts: int,
    delay: float,
    context: str = "",
):
    """记录重试日志"""
    error_type = type(error).__name__
    icon = "🔄"

    log.warning(
        f"{icon} 重试 {context} ({attempt}/{max_attempts})\n"
        f"   → 原因: [{error_type}] {error}\n"
        f"   → 等待: {delay:.1f}s"
    )


def log_circuit_open(name: str, remaining: float, last_error: Exception):
    """记录熔断器开启日志"""
    log.warning(
        f"⚡ 熔断器 [{name}] 已开启\n"
        f"   → 剩余冷却: {remaining:.0f}s\n"
        f"   → 最近错误: {last_error}"
    )


def log_connection_status(
    status: str,
    target: str,
    attempt: int = 0,
    max_attempts: int = 0,
    delay: float = 0,
    error: Exception | None = None,
):
    """
    记录连接状态日志

    Args:
        status: connecting, connected, disconnected, reconnecting, failed
        target: 连接目标描述
        attempt: 当前尝试次数
        max_attempts: 最大尝试次数
        delay: 下次重试延迟
        error: 错误信息
    """
    icons = {
        "connecting": "🔗",
        "connected": "✅",
        "disconnected": "🔌",
        "reconnecting": "🔄",
        "failed": "❌",
    }
    icon = icons.get(status, "•")

    if status == "connected":
        log.success(f"{icon} 已连接: {target}")
    elif status == "connecting":
        log.info(f"{icon} 正在连接: {target}")
    elif status == "disconnected":
        msg = f"{icon} 连接断开: {target}"
        if error:
            msg += f"\n   → 原因: {error}"
        log.warning(msg)
    elif status == "reconnecting":
        msg = f"{icon} 正在重连: {target}"
        if attempt and max_attempts:
            msg += f" ({attempt}/{max_attempts})"
        if delay:
            msg += f"\n   → 等待: {delay:.1f}s (指数退避)"
        if error:
            msg += f"\n   → 上次错误: {error}"
        log.warning(msg)
    elif status == "failed":
        log.error(f"{icon} 连接失败: {target}\n   → 错误: {error}")
