"""
AppContext - 应用程序上下文单例

提供全局组件注册表，让 Admin Console 能直接访问运行中的 Agent 组件。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.adapters.mcp import MCPManager
    from src.adapters.onebot import OneBotAdapter
    from src.agent.graph import QQAgent
    from src.memory.store import MemoryStore
    from src.presets.loader import PresetManager
    from src.session.aggregator import MessageAggregator


@dataclass
class AgentStats:
    """Agent 运行时统计"""

    start_time: datetime = field(default_factory=datetime.now)
    messages_processed: int = 0
    errors_count: int = 0
    last_message_time: Optional[datetime] = None

    @property
    def uptime_seconds(self) -> float:
        """运行时间（秒）"""
        return (datetime.now() - self.start_time).total_seconds()

    @property
    def uptime_formatted(self) -> str:
        """格式化的运行时间"""
        seconds = int(self.uptime_seconds)
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, secs = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if secs > 0 or not parts:
            parts.append(f"{secs}秒")

        return "".join(parts)

    def record_message(self):
        """记录一条处理的消息"""
        self.messages_processed += 1
        self.last_message_time = datetime.now()

    def record_error(self):
        """记录一次错误"""
        self.errors_count += 1

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "start_time": self.start_time.isoformat(),
            "uptime": self.uptime_formatted,
            "uptime_seconds": self.uptime_seconds,
            "messages_processed": self.messages_processed,
            "errors_count": self.errors_count,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
        }


class AppContext:
    """应用程序上下文单例

    持有所有核心组件的引用，供 Admin Console 和其他模块访问。
    使用线程安全的单例模式。
    """

    _instance: Optional[AppContext] = None
    _lock = threading.Lock()

    def __new__(cls) -> AppContext:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._agent: Optional[QQAgent] = None
        self._mcp_manager: Optional[MCPManager] = None
        self._adapter: Optional[OneBotAdapter] = None
        self._memory_store: Optional[MemoryStore] = None
        self._aggregator: Optional[MessageAggregator] = None
        self._preset_manager: Optional[PresetManager] = None
        self._stats = AgentStats()
        self._extra: dict[str, Any] = {}

        self._initialized = True

    # ==================== 注册方法 ====================

    def register_agent(self, agent: QQAgent) -> None:
        """注册 QQAgent"""
        self._agent = agent

    def register_mcp_manager(self, manager: MCPManager) -> None:
        """注册 MCP Manager"""
        self._mcp_manager = manager

    def register_adapter(self, adapter: OneBotAdapter) -> None:
        """注册 OneBot 适配器"""
        self._adapter = adapter

    def register_memory_store(self, store: MemoryStore) -> None:
        """注册会话存储"""
        self._memory_store = store

    def register_aggregator(self, aggregator: MessageAggregator) -> None:
        """注册消息聚合器"""
        self._aggregator = aggregator

    def register_preset_manager(self, manager: PresetManager) -> None:
        """注册预设管理器"""
        self._preset_manager = manager

    def register(self, name: str, component: Any) -> None:
        """注册自定义组件"""
        self._extra[name] = component

    # ==================== 获取方法 ====================

    @property
    def agent(self) -> Optional[QQAgent]:
        """获取 QQAgent"""
        return self._agent

    @property
    def mcp_manager(self) -> Optional[MCPManager]:
        """获取 MCP Manager"""
        return self._mcp_manager

    @property
    def adapter(self) -> Optional[OneBotAdapter]:
        """获取 OneBot 适配器"""
        return self._adapter

    @property
    def memory_store(self) -> Optional[MemoryStore]:
        """获取会话存储"""
        return self._memory_store

    @property
    def aggregator(self) -> Optional[MessageAggregator]:
        """获取消息聚合器"""
        return self._aggregator

    @property
    def preset_manager(self) -> Optional[PresetManager]:
        """获取预设管理器"""
        return self._preset_manager

    @property
    def stats(self) -> AgentStats:
        """获取运行时统计"""
        return self._stats

    def get(self, name: str) -> Optional[Any]:
        """获取自定义组件"""
        return self._extra.get(name)

    # ==================== 状态检查 ====================

    @property
    def is_agent_running(self) -> bool:
        """Agent 是否已注册并运行"""
        return self._agent is not None

    @property
    def is_mcp_running(self) -> bool:
        """MCP Manager 是否已注册"""
        return self._mcp_manager is not None

    @property
    def is_adapter_connected(self) -> bool:
        """OneBot 适配器是否已连接"""
        if self._adapter is None:
            return False
        return getattr(self._adapter, 'connected', False)

    def get_status_summary(self) -> dict:
        """获取状态摘要"""
        return {
            "agent_running": self.is_agent_running,
            "mcp_running": self.is_mcp_running,
            "adapter_connected": self.is_adapter_connected,
            "memory_store": self._memory_store is not None,
            "aggregator": self._aggregator is not None,
            "preset_manager": self._preset_manager is not None,
            "stats": self._stats.to_dict(),
        }

    def reset(self) -> None:
        """重置上下文（主要用于测试）"""
        self._agent = None
        self._mcp_manager = None
        self._adapter = None
        self._memory_store = None
        self._aggregator = None
        self._preset_manager = None
        self._stats = AgentStats()
        self._extra.clear()


def get_app_context() -> AppContext:
    """获取 AppContext 单例的便捷函数"""
    return AppContext()
