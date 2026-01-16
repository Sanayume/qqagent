"""
数据模型 - 用户、群组、消息
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import random


@dataclass
class User:
    """QQ 用户"""
    qq: int
    nickname: str
    avatar: str = ""  # 头像 URL（可选）
    is_bot: bool = False  # 是否是机器人

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
    members: list[int] = field(default_factory=list)  # QQ 号列表

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
    content: str  # 文本内容
    image: str = ""  # 图片 URL
    at_users: list[int] = field(default_factory=list)
    reply_to: int = 0  # 回复的消息 ID
    timestamp: datetime = field(default_factory=datetime.now)

    # 会话信息
    chat_type: Literal["private", "group"] = "group"
    group_id: int | None = None
    target_qq: int | None = None  # 私聊对象

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


class Simulator:
    """QQ 模拟器状态管理"""

    def __init__(self, bot_qq: int = 10000):
        self.bot_qq = bot_qq
        self.users: dict[int, User] = {}
        self.groups: dict[int, Group] = {}
        self.messages: list[Message] = []
        self._message_id_counter = 1000

        # 初始化机器人用户
        self.add_user(User(qq=bot_qq, nickname="Bot", is_bot=True))

    def add_user(self, user: User) -> User:
        """添加用户"""
        self.users[user.qq] = user
        return user

    def get_user(self, qq: int) -> User | None:
        """获取用户"""
        return self.users.get(qq)

    def remove_user(self, qq: int) -> bool:
        """删除用户"""
        if qq in self.users and qq != self.bot_qq:
            del self.users[qq]
            # 从所有群移除
            for group in self.groups.values():
                if qq in group.members:
                    group.members.remove(qq)
            return True
        return False

    def list_users(self) -> list[User]:
        """列出所有用户"""
        return list(self.users.values())

    def add_group(self, group: Group) -> Group:
        """添加群"""
        # 确保机器人在群里
        if self.bot_qq not in group.members:
            group.members.append(self.bot_qq)
        self.groups[group.group_id] = group
        return group

    def get_group(self, group_id: int) -> Group | None:
        """获取群"""
        return self.groups.get(group_id)

    def remove_group(self, group_id: int) -> bool:
        """删除群"""
        if group_id in self.groups:
            del self.groups[group_id]
            return True
        return False

    def list_groups(self) -> list[Group]:
        """列出所有群"""
        return list(self.groups.values())

    def add_member_to_group(self, group_id: int, qq: int) -> bool:
        """添加成员到群"""
        group = self.groups.get(group_id)
        if group and qq in self.users and qq not in group.members:
            group.members.append(qq)
            return True
        return False

    def remove_member_from_group(self, group_id: int, qq: int) -> bool:
        """从群移除成员"""
        group = self.groups.get(group_id)
        if group and qq in group.members and qq != self.bot_qq:
            group.members.remove(qq)
            return True
        return False

    def next_message_id(self) -> int:
        """生成下一个消息 ID"""
        self._message_id_counter += 1
        return self._message_id_counter

    def add_message(self, msg: Message) -> Message:
        """添加消息"""
        self.messages.append(msg)
        return msg

    def get_message(self, message_id: int) -> Message | None:
        """获取消息"""
        for msg in self.messages:
            if msg.message_id == message_id:
                return msg
        return None

    def get_chat_messages(
        self,
        chat_type: str,
        group_id: int | None = None,
        user_qq: int | None = None,
        limit: int = 50,
    ) -> list[Message]:
        """获取聊天消息"""
        result = []
        for msg in reversed(self.messages):
            if msg.chat_type == chat_type:
                if chat_type == "group" and msg.group_id == group_id:
                    result.append(msg)
                elif chat_type == "private":
                    # 私聊：两个用户之间的消息
                    if (msg.sender_qq == user_qq or msg.target_qq == user_qq):
                        result.append(msg)
            if len(result) >= limit:
                break
        return list(reversed(result))

    def create_default_data(self):
        """创建默认测试数据"""
        # 添加一些用户
        self.add_user(User(qq=10001, nickname="张三"))
        self.add_user(User(qq=10002, nickname="李四"))
        self.add_user(User(qq=10003, nickname="王五"))

        # 创建一个群
        group = Group(
            group_id=100001,
            name="测试群",
            members=[self.bot_qq, 10001, 10002, 10003],
        )
        self.add_group(group)

    def to_dict(self) -> dict:
        """导出状态"""
        return {
            "bot_qq": self.bot_qq,
            "users": [u.to_dict() for u in self.users.values()],
            "groups": [g.to_dict() for g in self.groups.values()],
        }
