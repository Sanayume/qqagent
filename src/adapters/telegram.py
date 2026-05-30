"""
Telegram 适配器（个人账号，MTProto via Telethon）

职责：
  - 管理 Telethon 客户端生命周期（连接/断开/重连）
  - 注册消息处理器（装饰器风格，与 OneBotAdapter 一致）
  - 提供统一的发送接口

不含任何业务逻辑，业务逻辑在 telegram_monitor.py 中。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from src.utils.logger import log

# Telethon 是可选依赖，延迟导入，未安装时报友好错误
try:
    from telethon import TelegramClient, events
    from telethon.errors.common import InvalidBufferError
    from telethon.tl.types import Message as TgMessage
    _TELETHON_AVAILABLE = True
except ImportError:
    _TELETHON_AVAILABLE = False
    InvalidBufferError = None


MessageHandler = Callable[[Any], Coroutine[Any, Any, None]]


def _require_telethon() -> None:
    if not _TELETHON_AVAILABLE:
        raise ImportError(
            "Telethon 未安装，请运行：pip install -e \".[telegram]\""
        )


class TelegramAdapter:
    """
    Telethon 客户端的薄封装。

    使用示例:
        adapter = TelegramAdapter(api_id=..., api_hash=..., ...)

        @adapter.on_message
        async def handler(event):
            ...

        await adapter.start()   # 阻塞直到断开
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: str = "data/tg_session",
        phone: str = "",
        proxy: dict | None = None,
    ):
        _require_telethon()
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = str(Path(session_path))
        self.phone = phone
        self.proxy = proxy or self._parse_proxy()

        self._client: "TelegramClient | None" = None
        self._message_handlers: list[MessageHandler] = []
        self._running = False
        self._reconnect_attempt = 0
        self._last_error: str | None = None
        self._last_error_at: str | None = None
        self._last_connected_at: str | None = None

    @staticmethod
    def _is_http_429_error(exc: Exception) -> bool:
        if InvalidBufferError is not None and isinstance(exc, InvalidBufferError):
            return "HTTP code 429" in str(exc)
        return "HTTP code 429" in str(exc) or "429" in str(exc)

    @staticmethod
    def _retry_delay(attempt: int, exc: Exception) -> float:
        if TelegramAdapter._is_http_429_error(exc):
            return min(300.0, 30.0 * max(1, attempt))
        return min(60.0, 5.0 * max(1, attempt))

    async def _reset_client(self) -> None:
        client = self._client
        self._client = None
        if client and client.is_connected():
            try:
                await client.disconnect()
            except Exception as e:
                log.debug(f"TelegramAdapter: 断开旧连接失败（忽略）: {e}")

    def _parse_proxy(self) -> dict | tuple | None:
        """从环境变量或配置中解析代理"""
        import os
        proxy_str = ""
        try:
            from src.utils.config_loader import get_config_loader
            proxy_str = str(get_config_loader().config._raw.get("telegram", {}).get("proxy_url", "") or "")
        except Exception:
            proxy_str = ""
        if not proxy_str:
            proxy_str = os.getenv("TG_PROXY", "")
        if not proxy_str:
            return None

        try:
            from urllib.parse import urlparse
            import python_socks
            parsed = urlparse(proxy_str)
            ptype = python_socks.ProxyType.SOCKS5 if parsed.scheme == "socks5" else python_socks.ProxyType.HTTP
            return {
                "proxy_type": ptype,
                "addr": parsed.hostname,
                "port": int(parsed.port)
            }
        except Exception as e:
            log.warning(f"解析 TG_PROXY 环境变量 ({proxy_str}) 失败: {e}，将不使用代理")
            return None

    # ===================== 处理器注册 =====================

    def on_message(self, handler: MessageHandler) -> MessageHandler:
        """注册消息处理器（装饰器 / 直接调用均可）。"""
        self._message_handlers.append(handler)
        # 如果 client 已经连接，则立即追加到 Telethon 事件系统
        if self._client is not None:
            self._client.add_event_handler(handler, events.NewMessage())
        return handler

    # ===================== 生命周期 =====================

    async def connect(self) -> None:
        """
        连接 TG 并注册事件处理器，但 **不** 阻塞。
        调用方可在 connect() 之后做业务初始化（如解析频道），再调用 run_forever()。
        """
        _require_telethon()
        self._running = True

        self._client = TelegramClient(
            self.session_path,
            self.api_id,
            self.api_hash,
            proxy=self.proxy,
        )

        # 注册 Telethon 事件处理器
        for handler in self._message_handlers:
            self._client.add_event_handler(
                handler,
                events.NewMessage(),
            )

        log.info("TelegramAdapter: 正在连接...")
        await self._client.start(phone=self.phone or None)
        me = await self._client.get_me()
        log.success(f"TelegramAdapter: 已登录 TG 账号 @{me.username or me.id}")

    async def run_forever(self) -> None:
        """阻塞直到 stop() 被调用。必须在 connect() 之后调用。"""
        if self._client is None:
            raise RuntimeError("请先调用 connect()")

        attempt = 0
        while self._running:
            try:
                await self._client.run_until_disconnected()
                if not self._running:
                    break

                attempt += 1
                self._reconnect_attempt = attempt
                self._last_error = "Telegram disconnected"
                self._last_error_at = datetime.now().isoformat(timespec="seconds")
                delay = self._retry_delay(attempt, RuntimeError("Telegram disconnected"))
                log.warning(f"TelegramAdapter: 连接已断开，{delay:.0f}s 后尝试重连")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not self._running:
                    break

                attempt += 1
                self._reconnect_attempt = attempt
                self._last_error = f"{type(e).__name__}: {e}"
                self._last_error_at = datetime.now().isoformat(timespec="seconds")
                delay = self._retry_delay(attempt, e)
                if self._is_http_429_error(e):
                    log.warning(f"TelegramAdapter: 遇到 429 限流，{delay:.0f}s 后重连: {type(e).__name__}: {e}")
                else:
                    log.warning(f"TelegramAdapter: 运行异常，{delay:.0f}s 后重连: {type(e).__name__}: {e}")

            await self._reset_client()
            await asyncio.sleep(delay)

            if not self._running:
                break

            try:
                await self.connect()
                attempt = 0
                self._reconnect_attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as reconnect_error:
                attempt += 1
                reconnect_delay = self._retry_delay(attempt, reconnect_error)
                if self._is_http_429_error(reconnect_error):
                    log.warning(
                        f"TelegramAdapter: 重连时遇到 429 限流，{reconnect_delay:.0f}s 后再试: "
                        f"{type(reconnect_error).__name__}: {reconnect_error}"
                    )
                else:
                    log.warning(
                        f"TelegramAdapter: 重连失败，{reconnect_delay:.0f}s 后再试: "
                        f"{type(reconnect_error).__name__}: {reconnect_error}"
                    )
                await asyncio.sleep(reconnect_delay)

    async def start(self) -> None:
        """兼容旧调用：connect + run_forever。"""
        await self.connect()
        await self.run_forever()

    async def stop(self) -> None:
        """断开连接。"""
        self._running = False
        if self._client and self._client.is_connected():
            await self._client.disconnect()
            log.info("TelegramAdapter: 已断开")

    @property
    def client(self) -> "TelegramClient":
        """获取底层 Telethon 客户端（供监控层直接调用 API）。"""
        if self._client is None:
            raise RuntimeError("TelegramAdapter 尚未启动")
        return self._client

    # ===================== 发送接口 =====================

    async def send_to_saved(self, text: str) -> None:
        """发送到 Saved Messages（自己的收藏夹，相当于给自己私信）。"""
        await self.client.send_message("me", text)

    async def send_to_chat(self, chat_id: int | str, text: str) -> None:
        """发送到指定 TG 群 / 频道 / 用户。"""
        await self.client.send_message(chat_id, text)

    async def resolve_chat(self, chat_id: int | str) -> Any:
        """解析群/频道对象（用于过滤监听目标）。"""
        return await self.client.get_entity(chat_id)
