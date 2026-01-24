"""
内置工具注册表

提供可配置的工具管理系统，支持：
- 工具注册与元数据管理
- 通过配置文件启用/禁用工具
- 运行时动态加载工具
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import yaml

from langchain_core.tools import BaseTool

from src.utils.logger import log


class ToolCategory(str, Enum):
    """工具分类"""
    CORE = "core"           # 核心工具（如 send_message）
    UTILITY = "utility"     # 实用工具（时间、计算等）
    MESSAGING = "messaging" # 消息相关（转发、合并等）
    SEARCH = "search"       # 搜索相关
    MEDIA = "media"         # 媒体处理
    CUSTOM = "custom"       # 自定义工具
    MCP = "mcp"             # MCP 工具


class ToolSource(str, Enum):
    """工具来源"""
    BUILTIN = "builtin"     # 内置工具
    MCP = "mcp"             # MCP 服务器工具


@dataclass
class ToolMeta:
    """工具元数据"""
    name: str                          # 工具名称（唯一标识）
    description: str                   # 简短描述
    category: ToolCategory             # 分类
    tool: BaseTool                     # LangChain 工具实例
    source: ToolSource = ToolSource.BUILTIN  # 工具来源
    source_name: str = ""              # 来源名称（MCP 服务器名）
    is_core: bool = False              # 是否为核心工具（核心工具不可禁用）
    enabled: bool = True               # 是否启用
    version: str = "1.0.0"             # 版本号
    author: str = "system"             # 作者
    tags: list[str] = field(default_factory=list)  # 标签

    def to_dict(self) -> dict:
        """转换为字典（用于 API 返回）"""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "source": self.source.value,
            "source_name": self.source_name,
            "is_core": self.is_core,
            "enabled": self.enabled,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "tool_description": self.tool.description[:300] if self.tool.description else "",
        }


class ToolRegistry:
    """工具注册表

    管理所有内置工具的注册、配置和获取。
    """

    CONFIG_FILE = Path("config/builtin_tools.yaml")

    def __init__(self):
        self._tools: dict[str, ToolMeta] = {}
        self._config: dict[str, bool] = {}
        self._load_config()

    def _load_config(self):
        """加载工具配置"""
        if not self.CONFIG_FILE.exists():
            self._config = {}
            return

        try:
            with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self._config = data.get("tools", {})
        except Exception as e:
            log.warning(f"Failed to load tool config: {e}")
            self._config = {}

    def _save_config(self):
        """保存工具配置"""
        self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # 构建配置数据
        data = {
            "tools": {
                name: meta.enabled
                for name, meta in self._tools.items()
                if not meta.is_core  # 核心工具不保存（始终启用）
            }
        }

        try:
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            log.error(f"Failed to save tool config: {e}")

    def register(
        self,
        tool: BaseTool,
        category: ToolCategory = ToolCategory.UTILITY,
        is_core: bool = False,
        description: str = "",
        version: str = "1.0.0",
        author: str = "system",
        tags: list[str] | None = None,
        source: ToolSource = ToolSource.BUILTIN,
        source_name: str = "",
    ) -> "ToolRegistry":
        """注册工具

        Args:
            tool: LangChain 工具实例
            category: 工具分类
            is_core: 是否为核心工具
            description: 简短描述（默认使用工具的 description）
            version: 版本号
            author: 作者
            tags: 标签列表
            source: 工具来源
            source_name: 来源名称（MCP 服务器名）

        Returns:
            self（支持链式调用）
        """
        name = tool.name

        # 确定启用状态
        if is_core:
            enabled = True  # 核心工具始终启用
        elif name in self._config:
            enabled = self._config[name]
        else:
            enabled = True  # 默认启用

        meta = ToolMeta(
            name=name,
            description=description or (tool.description[:100] if tool.description else name),
            category=category,
            tool=tool,
            source=source,
            source_name=source_name,
            is_core=is_core,
            enabled=enabled,
            version=version,
            author=author,
            tags=tags or [],
        )

        self._tools[name] = meta
        log.debug(f"Registered tool: {name} (source={source.value}, enabled={enabled})")

        return self

    def get_enabled_tools(self) -> list[BaseTool]:
        """获取所有启用的工具"""
        return [
            meta.tool
            for meta in self._tools.values()
            if meta.enabled
        ]

    def get_tool(self, name: str) -> ToolMeta | None:
        """获取工具元数据"""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMeta]:
        """列出所有工具"""
        return list(self._tools.values())

    def list_by_category(self, category: ToolCategory) -> list[ToolMeta]:
        """按分类列出工具"""
        return [
            meta for meta in self._tools.values()
            if meta.category == category
        ]

    def enable_tool(self, name: str) -> bool:
        """启用工具"""
        if name not in self._tools:
            return False

        self._tools[name].enabled = True
        self._save_config()
        log.info(f"Tool enabled: {name}")
        return True

    def disable_tool(self, name: str) -> bool:
        """禁用工具"""
        if name not in self._tools:
            return False

        meta = self._tools[name]
        if meta.is_core:
            log.warning(f"Cannot disable core tool: {name}")
            return False

        meta.enabled = False
        self._save_config()
        log.info(f"Tool disabled: {name}")
        return True

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """设置工具启用状态"""
        if enabled:
            return self.enable_tool(name)
        else:
            return self.disable_tool(name)

    def reload_config(self):
        """重新加载配置"""
        self._load_config()

        # 更新工具状态
        for name, meta in self._tools.items():
            if meta.is_core:
                continue
            if name in self._config:
                meta.enabled = self._config[name]

        log.info("Tool config reloaded")

    def get_status(self) -> dict:
        """获取工具状态摘要"""
        total = len(self._tools)
        enabled = sum(1 for m in self._tools.values() if m.enabled)
        core = sum(1 for m in self._tools.values() if m.is_core)

        by_category = {}
        for meta in self._tools.values():
            cat = meta.category.value
            if cat not in by_category:
                by_category[cat] = {"total": 0, "enabled": 0}
            by_category[cat]["total"] += 1
            if meta.enabled:
                by_category[cat]["enabled"] += 1

        # 按来源统计
        by_source = {}
        for meta in self._tools.values():
            src = meta.source.value
            src_name = meta.source_name or src
            key = f"{src}:{src_name}" if meta.source == ToolSource.MCP else src
            if key not in by_source:
                by_source[key] = {"total": 0, "enabled": 0}
            by_source[key]["total"] += 1
            if meta.enabled:
                by_source[key]["enabled"] += 1

        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "core": core,
            "by_category": by_category,
            "by_source": by_source,
        }

    # ==================== MCP 工具管理 ====================

    def register_mcp_tools(self, server_name: str, tools: list[BaseTool]) -> int:
        """注册 MCP 服务器的工具

        Args:
            server_name: MCP 服务器名称
            tools: 工具列表

        Returns:
            注册的工具数量
        """
        count = 0
        for tool in tools:
            self.register(
                tool,
                category=ToolCategory.MCP,
                source=ToolSource.MCP,
                source_name=server_name,
                author=f"mcp:{server_name}",
                tags=[server_name, "mcp"],
            )
            count += 1

        log.info(f"Registered {count} tools from MCP server: {server_name}")
        return count

    def unregister_mcp_tools(self, server_name: str | None = None) -> int:
        """注销 MCP 工具

        Args:
            server_name: 服务器名称，None 表示注销所有 MCP 工具

        Returns:
            注销的工具数量
        """
        to_remove = []
        for name, meta in self._tools.items():
            if meta.source == ToolSource.MCP:
                if server_name is None or meta.source_name == server_name:
                    to_remove.append(name)

        for name in to_remove:
            del self._tools[name]

        if to_remove:
            log.info(f"Unregistered {len(to_remove)} MCP tools" +
                     (f" from {server_name}" if server_name else ""))

        return len(to_remove)

    def list_by_source(self, source: ToolSource, source_name: str = "") -> list[ToolMeta]:
        """按来源列出工具"""
        return [
            meta for meta in self._tools.values()
            if meta.source == source and (not source_name or meta.source_name == source_name)
        ]

    def get_mcp_servers(self) -> dict[str, dict]:
        """获取所有 MCP 服务器及其工具统计"""
        servers: dict[str, dict] = {}
        for meta in self._tools.values():
            if meta.source == ToolSource.MCP:
                name = meta.source_name
                if name not in servers:
                    servers[name] = {"total": 0, "enabled": 0, "tools": []}
                servers[name]["total"] += 1
                servers[name]["tools"].append(meta.name)
                if meta.enabled:
                    servers[name]["enabled"] += 1
        return servers


# 全局注册表实例
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def init_builtin_tools() -> ToolRegistry:
    """初始化内置工具

    注册所有内置工具到注册表。
    """
    from src.agent.tools import (
        send_message,
        get_current_time,
        get_current_date,
        calculate,
    )

    registry = get_tool_registry()

    # 核心工具 - 不可禁用
    registry.register(
        send_message,
        category=ToolCategory.CORE,
        is_core=True,
        description="发送消息到当前对话",
        tags=["messaging", "output"],
    )

    # 实用工具 - 可禁用
    registry.register(
        get_current_time,
        category=ToolCategory.UTILITY,
        description="获取当前时间",
        tags=["time", "datetime"],
    )

    registry.register(
        get_current_date,
        category=ToolCategory.UTILITY,
        description="获取当前日期和星期",
        tags=["date", "datetime"],
    )

    registry.register(
        calculate,
        category=ToolCategory.UTILITY,
        description="计算数学表达式",
        tags=["math", "calculator"],
    )

    log.info(f"Builtin tools initialized: {registry.get_status()}")

    return registry
