"""
自定义异常层次 - 细化错误类型，便于精确处理

异常层次:
    AgentError (基类)
    ├── NetworkError        - 网络相关错误
    │   ├── ConnectionError - 连接失败
    │   └── TimeoutError    - 超时
    ├── APIError            - API 调用错误
    │   ├── RateLimitError  - 限流
    │   ├── AuthError       - 认证失败 (Token 过期等)
    │   └── BadRequestError - 请求参数错误
    ├── MediaError          - 媒体处理错误
    │   ├── DownloadError   - 下载失败
    │   └── EncodeError     - 编码失败
    └── OneBotError         - OneBot 协议错误
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentError(Exception):
    """Agent 基础异常"""
    message: str
    cause: Exception | None = None
    details: dict = field(default_factory=dict)

    # 用户友好的提示
    user_hint: str = ""
    # 是否可重试
    retryable: bool = False
    # 建议等待时间 (秒)
    retry_after: float = 0

    def __str__(self):
        return self.message

    def __repr__(self):
        return f"{self.__class__.__name__}({self.message!r})"


# ==================== 网络错误 ====================

@dataclass
class NetworkError(AgentError):
    """网络相关错误"""
    retryable: bool = True
    user_hint: str = "网络连接异常，请检查网络状态"


@dataclass
class ConnectionError(NetworkError):
    """连接失败"""
    host: str = ""
    port: int = 0
    user_hint: str = "无法建立连接"


@dataclass
class TimeoutError(NetworkError):
    """超时错误"""
    timeout: float = 0
    operation: str = ""
    user_hint: str = "操作超时，请稍后重试"


# ==================== API 错误 ====================

@dataclass
class APIError(AgentError):
    """API 调用错误"""
    status_code: int = 0
    api_name: str = ""


@dataclass
class RateLimitError(APIError):
    """限流错误"""
    retryable: bool = True
    retry_after: float = 30
    user_hint: str = "请求过于频繁，请稍后再试"


@dataclass
class AuthError(APIError):
    """认证错误 (Token 过期、无效等)"""
    retryable: bool = False
    user_hint: str = "认证失败，请检查 API Key 配置"


@dataclass
class BadRequestError(APIError):
    """请求参数错误"""
    retryable: bool = False
    user_hint: str = "请求参数有误"


@dataclass
class TokenExhaustedError(APIError):
    """Token/配额耗尽"""
    retryable: bool = False
    user_hint: str = "API 配额已耗尽，请检查账户余额"


# ==================== 媒体错误 ====================

@dataclass
class MediaError(AgentError):
    """媒体处理错误"""
    url: str = ""


@dataclass
class DownloadError(MediaError):
    """下载失败"""
    retryable: bool = True
    user_hint: str = "媒体下载失败"


@dataclass
class EncodeError(MediaError):
    """编码失败"""
    retryable: bool = False
    user_hint: str = "媒体编码失败"


# ==================== OneBot 错误 ====================

@dataclass
class OneBotError(AgentError):
    """OneBot 协议错误"""
    action: str = ""
    retcode: int = 0


@dataclass
class OneBotAPIError(OneBotError):
    """OneBot API 调用失败"""
    retryable: bool = True


@dataclass
class OneBotConnectionError(OneBotError):
    """OneBot 连接错误"""
    retryable: bool = True
    user_hint: str = "与 QQ 客户端的连接中断"


# ==================== 异常转换工具 ====================

def classify_http_error(status_code: int, response_text: str = "", api_name: str = "") -> APIError:
    """根据 HTTP 状态码分类异常"""
    if status_code == 401:
        return AuthError(
            message=f"认证失败: {response_text or 'Unauthorized'}",
            status_code=status_code,
            api_name=api_name,
        )
    elif status_code == 429:
        return RateLimitError(
            message=f"请求限流: {response_text or 'Too Many Requests'}",
            status_code=status_code,
            api_name=api_name,
        )
    elif status_code == 400:
        return BadRequestError(
            message=f"请求错误: {response_text or 'Bad Request'}",
            status_code=status_code,
            api_name=api_name,
        )
    elif status_code == 402 or "insufficient" in response_text.lower():
        return TokenExhaustedError(
            message=f"配额耗尽: {response_text or 'Payment Required'}",
            status_code=status_code,
            api_name=api_name,
        )
    else:
        return APIError(
            message=f"API 错误 ({status_code}): {response_text}",
            status_code=status_code,
            api_name=api_name,
            retryable=status_code >= 500,  # 5xx 错误可重试
        )


def classify_network_error(error: Exception, host: str = "", operation: str = "") -> NetworkError:
    """将底层网络异常转换为自定义异常"""
    import asyncio
    import aiohttp

    error_str = str(error).lower()
    error_type = type(error).__name__

    # 超时
    if isinstance(error, asyncio.TimeoutError) or "timeout" in error_str:
        return TimeoutError(
            message=f"操作超时: {operation or error_type}",
            operation=operation,
            cause=error,
        )

    # 连接拒绝
    if "refused" in error_str or "connect" in error_str:
        return ConnectionError(
            message=f"连接失败: {host or error_str}",
            host=host,
            cause=error,
        )

    # 通用网络错误
    return NetworkError(
        message=f"网络错误: {error}",
        cause=error,
    )
