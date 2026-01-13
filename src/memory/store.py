"""
会话历史存储 (SQLite 持久化)

提供统一的会话历史管理，支持：
- 内存缓存 (快速读取)
- SQLite 持久化 (重启不丢失)
- 自动限制历史长度
- 多模态消息自动转为纯文本存储
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Sequence

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)

from src.utils.logger import log
from src.core.llm_message import message_to_storage_text


def message_to_dict(message: BaseMessage) -> dict:
    """将 LangChain 消息转为可序列化的字典

    多模态消息会被转为纯文本存储，避免存储 base64 数据。
    """
    # 获取内容 - 如果是多模态，转为纯文本描述
    content = message.content
    if isinstance(content, list):
        # 多模态内容，转为纯文本存储
        content = message_to_storage_text(message)

    data = {
        "type": message.__class__.__name__,
        "content": content,
    }
    # 保存额外字段
    if hasattr(message, "tool_calls") and message.tool_calls:
        data["tool_calls"] = message.tool_calls
    if hasattr(message, "tool_call_id") and message.tool_call_id:
        data["tool_call_id"] = message.tool_call_id
    if hasattr(message, "name") and message.name:
        data["name"] = message.name
    return data


def dict_to_message(data: dict) -> BaseMessage:
    """从字典恢复 LangChain 消息"""
    msg_type = data.get("type", "HumanMessage")
    content = data.get("content", "")

    if msg_type == "HumanMessage":
        return HumanMessage(content=content)
    elif msg_type == "AIMessage":
        msg = AIMessage(content=content)
        if "tool_calls" in data:
            msg.tool_calls = data["tool_calls"]
        return msg
    elif msg_type == "SystemMessage":
        return SystemMessage(content=content)
    elif msg_type == "ToolMessage":
        return ToolMessage(
            content=content,
            tool_call_id=data.get("tool_call_id", ""),
            name=data.get("name", ""),
        )
    else:
        # 默认当作 HumanMessage
        return HumanMessage(content=content)


class MemoryStore:
    """统一的会话历史存储

    特性：
    - 内存缓存：频繁访问的会话保存在内存中
    - SQLite 持久化：所有变更自动写入数据库
    - 自动截断：超过 max_messages 时自动删除旧消息
    """

    def __init__(
        self,
        db_path: str = "data/sessions.db",
        max_messages: int = 20,
    ):
        """初始化存储

        Args:
            db_path: SQLite 数据库路径
            max_messages: 每个会话保留的最大消息数
        """
        self.db_path = Path(db_path)
        self.max_messages = max_messages
        self._cache: dict[str, list[BaseMessage]] = {}

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_db()
        log.info(f"MemoryStore initialized: {self.db_path}")

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    messages TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def _serialize(self, messages: list[BaseMessage]) -> str:
        """消息列表 -> JSON 字符串"""
        return json.dumps(
            [message_to_dict(m) for m in messages],
            ensure_ascii=False,
        )

    def _deserialize(self, data: str) -> list[BaseMessage]:
        """JSON 字符串 -> 消息列表"""
        items = json.loads(data)
        return [dict_to_message(item) for item in items]

    def _save_to_db(self, session_id: str, messages: list[BaseMessage]):
        """保存到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions (session_id, messages, updated_at)
                VALUES (?, ?, ?)
                """,
                (session_id, self._serialize(messages), datetime.now()),
            )
            conn.commit()

    def _load_from_db(self, session_id: str) -> list[BaseMessage] | None:
        """从数据库加载"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT messages FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._deserialize(row[0])
        return None

    def get_history(self, session_id: str) -> list[BaseMessage]:
        """获取会话历史

        Args:
            session_id: 会话 ID

        Returns:
            消息列表 (如果不存在返回空列表)
        """
        # 先查缓存
        if session_id in self._cache:
            return self._cache[session_id].copy()

        # 从数据库加载
        messages = self._load_from_db(session_id)
        if messages is not None:
            self._cache[session_id] = messages
            return messages.copy()

        return []

    def add_message(self, session_id: str, message: BaseMessage):
        """添加一条消息

        Args:
            session_id: 会话 ID
            message: 要添加的消息
        """
        # 获取当前历史
        if session_id not in self._cache:
            self._cache[session_id] = self._load_from_db(session_id) or []

        # 添加消息
        self._cache[session_id].append(message)

        # 截断
        if len(self._cache[session_id]) > self.max_messages:
            self._cache[session_id] = self._cache[session_id][-self.max_messages:]

        # 保存到数据库
        self._save_to_db(session_id, self._cache[session_id])

    def set_history(self, session_id: str, messages: Sequence[BaseMessage]):
        """设置会话历史 (覆盖)

        Args:
            session_id: 会话 ID
            messages: 新的消息列表
        """
        # 截断
        msg_list = list(messages)
        if len(msg_list) > self.max_messages:
            msg_list = msg_list[-self.max_messages:]

        # 更新缓存和数据库
        self._cache[session_id] = msg_list
        self._save_to_db(session_id, msg_list)

    def clear(self, session_id: str):
        """清除会话历史

        Args:
            session_id: 会话 ID
        """
        # 清除缓存
        if session_id in self._cache:
            del self._cache[session_id]

        # 清除数据库
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()

        log.info(f"Session cleared: {session_id}")

    def get_all_session_ids(self) -> list[str]:
        """获取所有会话 ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT session_id FROM sessions")
            return [row[0] for row in cursor.fetchall()]

    def get_session_count(self) -> int:
        """获取会话总数"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]
