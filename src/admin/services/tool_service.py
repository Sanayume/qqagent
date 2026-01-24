"""
工具管理服务

提供内置工具和 MCP 工具的查看、启用/禁用等管理功能。
"""

from typing import Any

from src.agent.tool_registry import (
    get_tool_registry,
    ToolRegistry,
    ToolCategory,
    ToolSource,
)
from src.core.context import get_app_context
from src.utils.logger import log


class ToolService:
    """工具管理服务"""

    def __init__(self):
        self._registry: ToolRegistry = get_tool_registry()

    def list_tools(self) -> list[dict]:
        """列出所有内置工具"""
        return [meta.to_dict() for meta in self._registry.list_tools()]

    def list_by_category(self, category: str) -> list[dict]:
        """按分类列出工具"""
        try:
            cat = ToolCategory(category)
            return [meta.to_dict() for meta in self._registry.list_by_category(cat)]
        except ValueError:
            return []

    def get_tool(self, name: str) -> dict | None:
        """获取工具详情"""
        meta = self._registry.get_tool(name)
        if meta:
            return meta.to_dict()
        return None

    def enable_tool(self, name: str) -> dict[str, Any]:
        """启用工具"""
        success = self._registry.enable_tool(name)
        if success:
            self._notify_agent_reload()
            return {"success": True, "message": f"工具 {name} 已启用"}
        return {"success": False, "error": f"工具 {name} 不存在"}

    def disable_tool(self, name: str) -> dict[str, Any]:
        """禁用工具"""
        meta = self._registry.get_tool(name)
        if not meta:
            return {"success": False, "error": f"工具 {name} 不存在"}

        if meta.is_core:
            return {"success": False, "error": f"核心工具 {name} 不可禁用"}

        success = self._registry.disable_tool(name)
        if success:
            self._notify_agent_reload()
            return {"success": True, "message": f"工具 {name} 已禁用"}
        return {"success": False, "error": "禁用失败"}

    def set_enabled(self, name: str, enabled: bool) -> dict[str, Any]:
        """设置工具启用状态"""
        if enabled:
            return self.enable_tool(name)
        else:
            return self.disable_tool(name)

    def get_status(self) -> dict:
        """获取工具状态摘要"""
        return self._registry.get_status()

    def get_categories(self) -> list[dict]:
        """获取所有分类"""
        return [
            {"value": cat.value, "label": cat.name}
            for cat in ToolCategory
        ]

    def reload_config(self) -> dict[str, Any]:
        """重新加载配置"""
        self._registry.reload_config()
        self._notify_agent_reload()
        return {"success": True, "message": "配置已重新加载"}

    def _notify_agent_reload(self):
        """通知 Agent 重新加载工具"""
        ctx = get_app_context()
        if ctx.agent:
            try:
                # 重新创建 graph 以应用新的工具配置
                ctx.agent._tools = self._get_all_tools()
                ctx.agent.graph = ctx.agent._create_graph()
                log.info("Agent tools reloaded")
            except Exception as e:
                log.error(f"Failed to reload agent tools: {e}")

    def _get_all_tools(self) -> list:
        """获取所有启用的工具（内置 + MCP 都在 Registry 中）"""
        return self._registry.get_enabled_tools()

    # ==================== MCP 工具管理 ====================

    def list_by_source(self, source: str, source_name: str = "") -> list[dict]:
        """按来源列出工具"""
        try:
            src = ToolSource(source)
            return [
                meta.to_dict()
                for meta in self._registry.list_by_source(src, source_name)
            ]
        except ValueError:
            return []

    def get_mcp_servers(self) -> dict[str, dict]:
        """获取所有 MCP 服务器及其工具统计"""
        return self._registry.get_mcp_servers()


# 全局单例
_tool_service: ToolService | None = None


def get_tool_service() -> ToolService:
    """获取 ToolService 单例"""
    global _tool_service
    if _tool_service is None:
        _tool_service = ToolService()
    return _tool_service
