"""
OneBot 11 Adapter - 支持正向和反向 WebSocket

正向 WebSocket (Forward):
    - Agent 作为客户端，主动连接到 NapCat
    - 适合 NapCat 已经在运行的情况

反向 WebSocket (Reverse):
    - Agent 作为服务端，等待 NapCat 连接
    - 更稳定，NapCat 会自动重连
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import websockets
from websockets.server import serve as ws_serve
from websockets.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

from src.utils.logger import log


@dataclass
class OneBotEvent:
    """OneBot 事件数据结构"""
    
    post_type: str  # message, notice, request, meta_event
    
    # Message event fields
    message_type: str | None = None  # private, group
    sub_type: str | None = None
    message_id: int | None = None
    user_id: int | None = None
    group_id: int | None = None
    raw_message: str = ""
    message: list[dict] | str = field(default_factory=list)
    sender: dict = field(default_factory=dict)
    
    # Notice/Request fields
    notice_type: str | None = None
    request_type: str | None = None
    
    # Meta fields
    meta_event_type: str | None = None
    
    # Self info
    self_id: int | None = None
    time: int | None = None
    
    # Raw data
    raw: dict = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> "OneBotEvent":
        """从字典创建事件对象"""
        return cls(
            post_type=data.get("post_type", ""),
            message_type=data.get("message_type"),
            sub_type=data.get("sub_type"),
            message_id=data.get("message_id"),
            user_id=data.get("user_id"),
            group_id=data.get("group_id"),
            raw_message=data.get("raw_message", ""),
            message=data.get("message", []),
            sender=data.get("sender", {}),
            notice_type=data.get("notice_type"),
            request_type=data.get("request_type"),
            meta_event_type=data.get("meta_event_type"),
            self_id=data.get("self_id"),
            time=data.get("time"),
            raw=data,
        )
    
    @property
    def is_message(self) -> bool:
        return self.post_type == "message"
    
    @property
    def is_private(self) -> bool:
        return self.message_type == "private"
    
    @property
    def is_group(self) -> bool:
        return self.message_type == "group"
    
    @property
    def sender_nickname(self) -> str:
        return self.sender.get("nickname", str(self.user_id))
    
    def get_plain_text(self) -> str:
        """提取纯文本内容"""
        if isinstance(self.message, str):
            return self.message
        
        text_parts = []
        for seg in self.message:
            if seg.get("type") == "text":
                text_parts.append(seg.get("data", {}).get("text", ""))
        return "".join(text_parts)
    
    def is_at_me(self, self_id: int) -> bool:
        """检查是否@了机器人"""
        if isinstance(self.message, str):
            return f"[CQ:at,qq={self_id}]" in self.message
        
        for seg in self.message:
            if seg.get("type") == "at":
                qq = seg.get("data", {}).get("qq")
                if qq and (str(qq) == str(self_id) or qq == "all"):
                    return True
        return False


MessageHandler = Callable[[OneBotEvent], Coroutine[Any, Any, None]]


class OneBotAdapter:
    """
    OneBot 11 适配器
    
    支持两种连接模式:
    - forward: 正向WS，Agent主动连接NapCat
    - reverse: 反向WS，Agent作为服务端等待NapCat连接
    """
    
    def __init__(
        self,
        # Forward WS config
        ws_url: str = "ws://127.0.0.1:3001",
        # Reverse WS config
        reverse_host: str = "127.0.0.1",
        reverse_port: int = 5140,
        reverse_path: str = "/onebot",
        # Auth
        token: str = "",
        # Mode
        mode: str = "reverse",  # forward, reverse, both
    ):
        self.ws_url = ws_url
        self.reverse_host = reverse_host
        self.reverse_port = reverse_port
        self.reverse_path = reverse_path
        self.token = token
        self.mode = mode
        
        # Connection state
        self._ws_forward: websockets.WebSocketClientProtocol | None = None
        self._ws_reverse: websockets.WebSocketServerProtocol | None = None
        self._server: websockets.Server | None = None
        
        # Event handlers
        self._message_handlers: list[MessageHandler] = []
        self._event_handlers: list[Callable[[OneBotEvent], Coroutine]] = []
        
        # API response tracking
        self._pending_requests: dict[str, asyncio.Future] = {}
        
        # Bot info
        self.self_id: int | None = None
        
        # Running flag
        self._running = False
    
    def on_message(self, handler: MessageHandler) -> MessageHandler:
        """注册消息处理器 (装饰器)"""
        self._message_handlers.append(handler)
        return handler
    
    def on_event(self, handler: Callable[[OneBotEvent], Coroutine]) -> Callable:
        """注册事件处理器 (装饰器)"""
        self._event_handlers.append(handler)
        return handler
    
    # ==================== Connection Management ====================
    
    async def start(self):
        """启动适配器"""
        self._running = True
        log.info(f"Starting OneBot adapter in {self.mode} mode...")
        
        tasks = []
        
        if self.mode in ("forward", "both"):
            tasks.append(asyncio.create_task(self._run_forward_client()))
        
        if self.mode in ("reverse", "both"):
            tasks.append(asyncio.create_task(self._run_reverse_server()))
        
        if not tasks:
            log.error(f"Invalid mode: {self.mode}")
            return
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Adapter shutting down...")
        finally:
            await self.stop()
    
    async def stop(self):
        """停止适配器"""
        self._running = False
        
        if self._ws_forward:
            await self._ws_forward.close()
        
        if self._ws_reverse:
            await self._ws_reverse.close()
        
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        
        log.info("OneBot adapter stopped")
    
    async def _run_forward_client(self):
        """运行正向 WebSocket 客户端"""
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        while self._running:
            try:
                log.info(f"Connecting to NapCat at {self.ws_url}...")
                async with ws_connect(self.ws_url, extra_headers=headers) as ws:
                    self._ws_forward = ws
                    log.success(f"Connected to NapCat (Forward WS)")
                    await self._handle_connection(ws, "forward")
                    
            except ConnectionRefusedError:
                log.warning(f"Connection refused, retrying in 5s...")
            except ConnectionClosed as e:
                log.warning(f"Connection closed: {e}, reconnecting in 5s...")
            except Exception as e:
                log.error(f"Forward WS error: {e}, retrying in 5s...")
            
            if self._running:
                await asyncio.sleep(5)
    
    async def _run_reverse_server(self):
        """运行反向 WebSocket 服务端"""
        
        async def handle_client(websocket):
            # 获取连接信息用于日志
            remote = getattr(websocket, 'remote_address', 'unknown')
            path = getattr(websocket, 'path', '/')

            # 忽略 NapCat WebUI 的状态轮询请求
            if path == '/status':
                await websocket.close(1000, "Not OneBot endpoint")
                return

            log.info(f"New connection from {remote}, path: {path}")
            
            # 获取请求头
            headers = {}
            if hasattr(websocket, 'request_headers'):
                headers = dict(websocket.request_headers)
            elif hasattr(websocket, 'request') and hasattr(websocket.request, 'headers'):
                headers = dict(websocket.request.headers)
            
            log.debug(f"Request headers: {headers}")

            # Token 验证 (如果配置了 token)
            if self.token:
                # HTTP headers 大小写不敏感，转为小写查找
                headers_lower = {k.lower(): v for k, v in headers.items()}
                auth = headers_lower.get("authorization", "")
                # NapCat 可能发送 "Bearer token" 或 "Token token" 或直接发送 token
                token_valid = (
                    auth == f"Bearer {self.token}" or
                    auth == f"Token {self.token}" or
                    auth == self.token or
                    headers_lower.get("access_token") == self.token
                )
                if not token_valid:
                    log.warning(f"Token validation failed from {remote}. Got Authorization: '{auth}'")
                    await websocket.close(1008, "Unauthorized")
                    return
            
            self._ws_reverse = websocket
            log.success(f"NapCat connected (Reverse WS) from {remote}")
            
            try:
                await self._handle_connection(websocket, "reverse")
            except ConnectionClosed as e:
                log.info(f"Reverse WS client disconnected: {e}")
            except Exception as e:
                log.exception(f"Error in connection handler: {e}")
            finally:
                self._ws_reverse = None
                log.info("Connection closed")
        
        log.info(f"Starting reverse WS server at ws://{self.reverse_host}:{self.reverse_port}{self.reverse_path}")
        
        self._server = await ws_serve(
            handle_client,
            self.reverse_host,
            self.reverse_port,
        )
        
        log.success(f"Reverse WS server listening on {self.reverse_host}:{self.reverse_port}")
        
        # Keep server running
        await self._server.wait_closed()
    
    async def _handle_connection(self, ws, conn_type: str):
        """处理 WebSocket 连接"""
        async for raw_message in ws:
            try:
                data = json.loads(raw_message)
                
                # API response
                if "echo" in data and data.get("echo") in self._pending_requests:
                    echo = data["echo"]
                    future = self._pending_requests.pop(echo)
                    if not future.done():
                        future.set_result(data)
                    continue
                
                # Event
                event = OneBotEvent.from_dict(data)
                
                # Update self_id from lifecycle event
                if event.post_type == "meta_event" and event.self_id:
                    self.self_id = event.self_id
                    log.info(f"Bot QQ: {self.self_id}")
                
                # Dispatch event
                await self._dispatch_event(event)
                
            except json.JSONDecodeError:
                log.warning(f"Invalid JSON: {raw_message[:100]}...")
            except Exception as e:
                log.exception(f"Error handling message: {e}")
    
    async def _dispatch_event(self, event: OneBotEvent):
        """分发事件到处理器"""
        # Message event -> message handlers
        if event.is_message:
            for handler in self._message_handlers:
                try:
                    asyncio.create_task(handler(event))
                except Exception as e:
                    log.exception(f"Message handler error: {e}")
        
        # All events -> event handlers
        for handler in self._event_handlers:
            try:
                asyncio.create_task(handler(event))
            except Exception as e:
                log.exception(f"Event handler error: {e}")
    
    # ==================== API Methods ====================
    
    def _get_active_ws(self):
        """获取活跃的 WebSocket 连接"""
        return self._ws_reverse or self._ws_forward
    
    async def call_api(self, action: str, params: dict | None = None, timeout: float = 30) -> dict:
        """调用 OneBot API"""
        ws = self._get_active_ws()
        if not ws:
            raise ConnectionError("No active WebSocket connection")
        
        echo = str(uuid.uuid4())
        payload = {
            "action": action,
            "params": params or {},
            "echo": echo,
        }
        
        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[echo] = future
        
        try:
            await ws.send(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            
            if result.get("status") == "failed":
                log.warning(f"API call failed: {action}, {result.get('msg')}")
            
            return result
            
        except asyncio.TimeoutError:
            self._pending_requests.pop(echo, None)
            raise TimeoutError(f"API call timed out: {action}")
    
    async def send_private_msg(self, user_id: int, message: str | list) -> dict:
        """发送私聊消息"""
        return await self.call_api("send_private_msg", {
            "user_id": user_id,
            "message": message,
        })
    
    async def send_group_msg(self, group_id: int, message: str | list) -> dict:
        """发送群消息"""
        return await self.call_api("send_group_msg", {
            "group_id": group_id,
            "message": message,
        })
    
    async def send_msg(self, event: OneBotEvent, message: str | list) -> dict:
        """根据事件类型发送消息"""
        if event.is_group:
            return await self.send_group_msg(event.group_id, message)
        else:
            return await self.send_private_msg(event.user_id, message)
    
    async def get_login_info(self) -> dict:
        """获取登录信息"""
        result = await self.call_api("get_login_info")
        if result.get("status") == "ok":
            data = result.get("data", {})
            self.self_id = data.get("user_id")
        return result
    
    async def get_stranger_info(self, user_id: int, no_cache: bool = False) -> dict:
        """获取陌生人信息"""
        return await self.call_api("get_stranger_info", {
            "user_id": user_id,
            "no_cache": no_cache,
        })
    
    async def get_group_info(self, group_id: int, no_cache: bool = False) -> dict:
        """获取群信息"""
        return await self.call_api("get_group_info", {
            "group_id": group_id,
            "no_cache": no_cache,
        })
    
    async def get_group_member_info(self, group_id: int, user_id: int, no_cache: bool = False) -> dict:
        """获取群成员信息"""
        return await self.call_api("get_group_member_info", {
            "group_id": group_id,
            "user_id": user_id,
            "no_cache": no_cache,
        })

    async def get_msg(self, message_id: int) -> dict:
        """获取消息详情

        用于获取引用消息的完整内容。

        Args:
            message_id: 消息 ID

        Returns:
            API 响应，成功时 data 包含:
            - message_id: 消息 ID
            - real_id: 真实消息 ID
            - sender: 发送者信息 {user_id, nickname}
            - time: 发送时间戳
            - message: 消息段数组

        Example:
            >>> result = await adapter.get_msg(12345)
            >>> if result.get("status") == "ok":
            ...     msg = result["data"]["message"]
        """
        return await self.call_api("get_msg", {"message_id": message_id})

    async def get_forward_msg(self, forward_id: str) -> dict:
        """获取合并转发消息内容

        Args:
            forward_id: 合并转发 ID (从 forward 消息段的 data.id 获取)

        Returns:
            API 响应，成功时 data 包含:
            - message: 转发节点数组，每个节点包含:
                - type: "node"
                - data: {user_id, nickname, content}

        Note:
            content 可能是消息段数组，也可能是字符串。

        Example:
            >>> result = await adapter.get_forward_msg("abc123")
            >>> if result.get("status") == "ok":
            ...     nodes = result["data"]["message"]
        """
        return await self.call_api("get_forward_msg", {"id": forward_id})


# ==================== Helper Functions ====================

def build_message(*segments) -> list[dict]:
    """构建消息段数组
    
    Example:
        msg = build_message(
            text("Hello "),
            at(123456),
            text("!"),
            image("file:///path/to/image.png")
        )
    """
    return list(segments)


def text(content: str) -> dict:
    """文本消息段"""
    return {"type": "text", "data": {"text": content}}


def at(qq: int | str) -> dict:
    """@消息段"""
    return {"type": "at", "data": {"qq": str(qq)}}


def image(file: str, type_: str = "", url: str = "") -> dict:
    """图片消息段
    
    Args:
        file: 图片文件路径 (file:///, base64://, http://)
        type_: 图片类型 (flash 闪照, show 秀图)
        url: 图片URL
    """
    data = {"file": file}
    if type_:
        data["type"] = type_
    if url:
        data["url"] = url
    return {"type": "image", "data": data}


def face(id_: int) -> dict:
    """QQ表情"""
    return {"type": "face", "data": {"id": str(id_)}}


def reply(message_id: int) -> dict:
    """回复消息段"""
    return {"type": "reply", "data": {"id": str(message_id)}}
