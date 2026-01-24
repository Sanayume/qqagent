"""
MCP 服务

管理 MCP 服务器配置、状态检测和进程控制。
配置存储在 config/mcp_servers.json 中。

通过 AppContext 可以访问运行中的 MCPManager，获取真实状态。
"""

import json
import asyncio
from pathlib import Path
from typing import Any, Optional

from src.utils.logger import log
from src.adapters.mcp import MCPManager
from src.core.context import get_app_context


MCP_CONFIG_FILE = Path("config/mcp_servers.json")

class MCPService:
    """MCP 管理服务"""

    def __init__(self, config_file: Path = MCP_CONFIG_FILE):
        self.config_file = config_file

    def list_servers(self) -> dict[str, Any]:
        """读取所有服务器配置"""
        if not self.config_file.exists():
            return {}
            
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.error(f"读取 MCP 配置失败: {e}")
            return {}

    def get_server(self, name: str) -> Optional[dict]:
        """获取单个服务器配置"""
        servers = self.list_servers()
        return servers.get(name)

    def add_server(self, name: str, config: dict) -> bool:
        """添加或更新服务器"""
        servers = self.list_servers()
        servers[name] = config
        return self._save_servers(servers)
    
    def delete_server(self, name: str) -> bool:
        """删除服务器"""
        servers = self.list_servers()
        if name in servers:
            del servers[name]
            return self._save_servers(servers)
        return False
        
    def _save_servers(self, servers: dict) -> bool:
        """保存配置"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(servers, f, ensure_ascii=False, indent=2)
            log.info("MCP 配置已更新")
            return True
        except Exception as e:
            log.error(f"保存 MCP 配置失败: {e}")
            return False

    async def check_status(self) -> dict[str, str]:
        """检查服务器状态（优先使用运行时状态）"""
        ctx = get_app_context()

        # 如果有运行中的 MCPManager，返回真实状态
        if ctx.mcp_manager:
            return await self.get_runtime_status()

        # 否则只返回配置状态
        servers = self.list_servers()
        return {name: "configured" for name in servers}

    async def get_runtime_status(self) -> dict[str, Any]:
        """获取 MCP 服务器真实运行状态

        通过 AppContext 访问运行中的 MCPManager。
        """
        ctx = get_app_context()

        if not ctx.mcp_manager:
            return {"error": "MCPManager 未运行", "servers": {}}

        manager = ctx.mcp_manager

        # 获取服务器状态
        servers_status = {}
        for name in manager.servers:
            status = manager.get_server_status(name)
            tools = manager.get_tools_by_server(name)
            servers_status[name] = {
                "status": status,
                "tools_count": len(tools),
                "tools": [t.name for t in tools],
            }

        return {
            "running": True,
            "servers": servers_status,
            "total_tools": len(manager.get_tools()),
        }

    async def reload_all(self) -> dict[str, Any]:
        """重载所有 MCP 服务器

        重新读取配置文件并重启所有服务器。
        """
        ctx = get_app_context()

        if not ctx.mcp_manager:
            return {"success": False, "error": "MCPManager 未运行"}

        manager = ctx.mcp_manager

        try:
            # 停止所有服务器
            await manager.stop()

            # 重新加载配置并启动
            manager.config_file = self.config_file
            await manager.start()

            log.success("MCP servers reloaded")

            return {
                "success": True,
                "message": "MCP 服务器已重载",
                "servers": list(manager.servers.keys()),
            }
        except Exception as e:
            log.error(f"MCP reload failed: {e}")
            return {"success": False, "error": str(e)}

    async def restart_server(self, name: str) -> dict[str, Any]:
        """重启单个 MCP 服务器"""
        ctx = get_app_context()

        if not ctx.mcp_manager:
            return {"success": False, "error": "MCPManager 未运行"}

        manager = ctx.mcp_manager

        if name not in manager.servers:
            return {"success": False, "error": f"服务器 {name} 不存在"}

        try:
            await manager.restart_server(name)
            log.info(f"MCP server {name} restarted")
            return {"success": True, "message": f"服务器 {name} 已重启"}
        except Exception as e:
            log.error(f"MCP server {name} restart failed: {e}")
            return {"success": False, "error": str(e)}


# 全局单例
_mcp_service: MCPService | None = None

def get_mcp_service() -> MCPService:
    global _mcp_service
    if _mcp_service is None:
        _mcp_service = MCPService()
    return _mcp_service
