"""
Agent 状态定义

定义 LangGraph Agent 的状态结构，用于在节点之间传递数据。
"""

from dataclasses import dataclass, field
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


@dataclass
class ChatResponse:
    """Agent 聊天响应

    Attributes:
        text: 文本回复内容（Agent 内部输出，不直接发送）
        images: 图片列表 [(base64_data, mime_type), ...]
        pending_sends: 待执行的发送指令列表
    """
    text: str = ""
    images: list[tuple[str, str]] = field(default_factory=list)
    pending_sends: list[dict] = field(default_factory=list)

    def has_images(self) -> bool:
        """是否包含图片"""
        return bool(self.images)

    def has_pending_sends(self) -> bool:
        """是否有待发送的消息"""
        return bool(self.pending_sends)


class AgentState(TypedDict):
    """Agent 运行时状态
    
    Attributes:
        messages: 消息历史，由 LangGraph 自动管理追加
        session_id: 会话唯一标识 (用于隔离不同用户/群的对话)
        user_id: 发送消息的用户 QQ 号
        group_id: 群号 (私聊时为 None)
        user_name: 用户昵称
        preset_name: 当前使用的预设名称
        system_prompt: 系统提示词
        should_respond: 是否应该回复
    """
    
    # 消息历史 - 使用 add_messages reducer 自动追加
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # 会话信息
    session_id: str
    user_id: int
    group_id: int | None
    user_name: str
    
    # 预设配置
    preset_name: str
    system_prompt: str
    
    # 控制标志
    should_respond: bool


class SessionContext(TypedDict):
    """会话上下文 (用于初始化状态)"""
    session_id: str
    user_id: int
    group_id: int | None
    user_name: str
    preset_name: str
    system_prompt: str
