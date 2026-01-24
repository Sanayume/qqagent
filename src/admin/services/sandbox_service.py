"""
沙盒服务

管理沙盒环境的用户、群组、消息。
支持两种模式:
- 模拟模式: 简单的模拟回复，不连接真实 Agent
- 真实 Agent 模式: 使用运行中的 Agent 处理消息
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Callable, Awaitable

from src.utils.logger import log
from src.core.context import get_app_context

# ==================== Models ====================

@dataclass
class User:
    """QQ 用户"""
    qq: int
    nickname: str
    avatar: str = ""
    is_bot: bool = False

    def to_dict(self) -> dict:
        return {
            "qq": self.qq,
            "nickname": self.nickname,
            "avatar": self.avatar or f"https://q1.qlogo.cn/g?b=qq&nk={self.qq}&s=100",
            "is_bot": self.is_bot,
        }


@dataclass
class Group:
    """QQ 群"""
    group_id: int
    name: str
    members: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "members": self.members,
        }


@dataclass
class Message:
    """消息"""
    message_id: int
    sender_qq: int
    content: str
    image: str = ""
    at_users: list[int] = field(default_factory=list)
    reply_to: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    chat_type: Literal["private", "group"] = "group"
    group_id: int | None = None
    target_qq: int | None = None

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "sender_qq": self.sender_qq,
            "content": self.content,
            "image": self.image,
            "at_users": self.at_users,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp.isoformat(),
            "chat_type": self.chat_type,
            "group_id": self.group_id,
            "target_qq": self.target_qq,
        }


# ==================== Service ====================

class SandboxService:
    """沙盒服务 - 支持模拟模式和真实 Agent 模式"""

    def __init__(self, bot_qq: int = 10000):
        self.bot_qq = bot_qq
        self.users: dict[int, User] = {}
        self.groups: dict[int, Group] = {}
        self.messages: list[Message] = []
        self._message_id_counter = 1000
        self._listeners: set = set()
        self.use_real_agent = False  # 是否使用真实 Agent

        # 初始化默认数据
        self.add_user(User(qq=bot_qq, nickname="Bot", is_bot=True))
        self.create_default_data()

    async def broadcast(self, data: dict):
        """广播消息给所有连接的 WebSocket 客户端"""
        dead = set()
        for ws in self._listeners:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._listeners.discard(ws)

    def add_user(self, user: User) -> User:
        self.users[user.qq] = user
        return user
        
    def get_user(self, qq: int) -> User | None:
        return self.users.get(qq)
        
    def add_group(self, group: Group) -> Group:
        if self.bot_qq not in group.members:
            group.members.append(self.bot_qq)
        self.groups[group.group_id] = group
        return group
        
    def next_message_id(self) -> int:
        self._message_id_counter += 1
        return self._message_id_counter

    def add_message(self, msg: Message) -> Message:
        self.messages.append(msg)
        return msg

    def get_chat_messages(self, chat_type: str, group_id: int | None = None, user_qq: int | None = None, limit: int = 50) -> list[dict]:
        """获取并序列化消息"""
        result = []
        for msg in reversed(self.messages):
            if msg.chat_type == chat_type:
                if chat_type == "group" and msg.group_id == group_id:
                    result.append(msg)
                elif chat_type == "private":
                    if (msg.sender_qq == user_qq or msg.target_qq == user_qq):
                        result.append(msg)
            if len(result) >= limit:
                break
        
        return [self._enrich_message(m) for m in reversed(result)]

    def _enrich_message(self, msg: Message) -> dict:
        data = msg.to_dict()
        sender = self.users.get(msg.sender_qq)
        if sender:
            data["sender"] = sender.to_dict()
        return data

    def create_default_data(self):
        """创建默认测试数据"""
        if 10001 not in self.users:
            self.add_user(User(qq=10001, nickname="张三", avatar="https://q1.qlogo.cn/g?b=qq&nk=10001&s=100"))
            self.add_user(User(qq=10002, nickname="李四", avatar="https://q1.qlogo.cn/g?b=qq&nk=10002&s=100"))
            self.add_user(User(qq=10003, nickname="王五", avatar="https://q1.qlogo.cn/g?b=qq&nk=10003&s=100"))
            self.create_group(100001, "测试群1", [self.bot_qq, 10001, 10002, 10003])
            
            # 添加一些示例消息
            self.add_message(Message(
                message_id=self.next_message_id(),
                sender_qq=10001,
                content="大家好！",
                chat_type="group",
                group_id=100001
            ))
            self.add_message(Message(
                message_id=self.next_message_id(),
                sender_qq=self.bot_qq,
                content="你好呀～欢迎来到沙盒测试环境！",
                chat_type="group",
                group_id=100001
            ))

    def create_group(self, group_id: int, name: str, members: list[int]) -> Group:
        group = Group(group_id=group_id, name=name, members=members)
        return self.add_group(group)

    async def simulate_bot_reply(self, original_msg: Message):
        """模拟 Bot 回复

        根据 use_real_agent 设置决定使用模拟回复还是真实 Agent。
        """
        if self.use_real_agent:
            await self._real_agent_reply(original_msg)
        else:
            await self._mock_reply(original_msg)

    async def _mock_reply(self, original_msg: Message):
        """模拟回复（简单的回显，不连接真实 Agent）"""
        replies = [
            f"收到了「{original_msg.content}」！",
            f"嗯嗯，{self.users.get(original_msg.sender_qq, User(qq=0, nickname='你')).nickname}说得对！",
            "觉得这个问题很有趣呢～",
            "让我想想...",
        ]

        import random
        reply_text = random.choice(replies)

        reply_msg = Message(
            message_id=self.next_message_id(),
            sender_qq=self.bot_qq,
            content=reply_text,
            chat_type=original_msg.chat_type,
            group_id=original_msg.group_id,
            target_qq=original_msg.sender_qq if original_msg.chat_type == "private" else None,
        )

        self.add_message(reply_msg)

        await self.broadcast({
            "type": "new_message",
            "data": self._enrich_message(reply_msg)
        })

    async def _real_agent_reply(self, original_msg: Message):
        """使用真实 Agent 回复"""
        ctx = get_app_context()

        if not ctx.agent:
            # 如果 Agent 未运行，回退到模拟模式
            log.warning("Real agent not available, falling back to mock reply")
            await self._mock_reply(original_msg)
            return

        try:
            # 构建 session_id
            if original_msg.chat_type == "group":
                session_id = f"sandbox-group-{original_msg.group_id}"
            else:
                session_id = f"sandbox-private-{original_msg.sender_qq}"

            sender = self.users.get(original_msg.sender_qq)
            user_name = sender.nickname if sender else "用户"

            # 调用真实 Agent
            response = await ctx.agent.chat(
                message=original_msg.content,
                session_id=session_id,
                user_id=original_msg.sender_qq,
                group_id=original_msg.group_id,
                user_name=user_name,
            )

            # 记录统计
            ctx.stats.record_message()

            # 发送回复
            reply_msg = Message(
                message_id=self.next_message_id(),
                sender_qq=self.bot_qq,
                content=response.text or "[无回复]",
                image=response.images[0] if response.images else "",
                chat_type=original_msg.chat_type,
                group_id=original_msg.group_id,
                target_qq=original_msg.sender_qq if original_msg.chat_type == "private" else None,
            )

            self.add_message(reply_msg)

            await self.broadcast({
                "type": "new_message",
                "data": self._enrich_message(reply_msg)
            })

        except Exception as e:
            log.error(f"Real agent reply failed: {e}")
            ctx.stats.record_error()

            # 发送错误消息
            error_msg = Message(
                message_id=self.next_message_id(),
                sender_qq=self.bot_qq,
                content=f"处理消息时出错: {str(e)[:100]}",
                chat_type=original_msg.chat_type,
                group_id=original_msg.group_id,
                target_qq=original_msg.sender_qq if original_msg.chat_type == "private" else None,
            )

            self.add_message(error_msg)

            await self.broadcast({
                "type": "new_message",
                "data": self._enrich_message(error_msg)
            })

    def set_real_agent_mode(self, enabled: bool) -> bool:
        """设置是否使用真实 Agent 模式"""
        ctx = get_app_context()

        if enabled and not ctx.agent:
            log.warning("Cannot enable real agent mode: Agent not running")
            return False

        self.use_real_agent = enabled
        log.info(f"Sandbox real agent mode: {'enabled' if enabled else 'disabled'}")
        return True

    def is_real_agent_available(self) -> bool:
        """检查真实 Agent 是否可用"""
        ctx = get_app_context()
        return ctx.agent is not None


# 全局单例
_sandbox_service: SandboxService | None = None

def get_sandbox_service() -> SandboxService:
    global _sandbox_service
    if _sandbox_service is None:
        _sandbox_service = SandboxService()
    return _sandbox_service
