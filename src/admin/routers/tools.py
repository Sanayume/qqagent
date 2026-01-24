"""
工具管理 API 路由

提供内置工具的查看、启用/禁用等 REST API。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.admin.services.tool_service import get_tool_service

router = APIRouter(prefix="/api/tools", tags=["Tools"])


class ToolToggleRequest(BaseModel):
    """工具启用/禁用请求"""
    enabled: bool


@router.get("")
async def list_tools():
    """列出所有内置工具"""
    svc = get_tool_service()
    return {
        "tools": svc.list_tools(),
        "status": svc.get_status(),
    }


@router.get("/status")
async def get_status():
    """获取工具状态摘要"""
    svc = get_tool_service()
    return svc.get_status()


@router.get("/categories")
async def get_categories():
    """获取工具分类列表"""
    svc = get_tool_service()
    return {"categories": svc.get_categories()}


@router.get("/{name}")
async def get_tool(name: str):
    """获取工具详情"""
    svc = get_tool_service()
    tool = svc.get_tool(name)
    if not tool:
        raise HTTPException(404, f"工具 {name} 不存在")
    return tool


@router.post("/{name}/toggle")
async def toggle_tool(name: str, req: ToolToggleRequest):
    """启用/禁用工具"""
    svc = get_tool_service()
    result = svc.set_enabled(name, req.enabled)
    if not result.get("success"):
        raise HTTPException(400, result.get("error"))
    return result


@router.post("/{name}/enable")
async def enable_tool(name: str):
    """启用工具"""
    svc = get_tool_service()
    result = svc.enable_tool(name)
    if not result.get("success"):
        raise HTTPException(400, result.get("error"))
    return result


@router.post("/{name}/disable")
async def disable_tool(name: str):
    """禁用工具"""
    svc = get_tool_service()
    result = svc.disable_tool(name)
    if not result.get("success"):
        raise HTTPException(400, result.get("error"))
    return result


@router.post("/reload")
async def reload_config():
    """重新加载工具配置"""
    svc = get_tool_service()
    return svc.reload_config()


# ==================== MCP 工具管理 ====================


@router.get("/mcp/servers")
async def get_mcp_servers():
    """获取所有 MCP 服务器及其工具统计"""
    svc = get_tool_service()
    return {"servers": svc.get_mcp_servers()}


@router.get("/mcp/{server_name}")
async def get_mcp_server_tools(server_name: str):
    """获取指定 MCP 服务器的工具列表"""
    svc = get_tool_service()
    tools = svc.list_by_source("mcp", server_name)
    return {"server": server_name, "tools": tools}


@router.get("/source/{source}")
async def list_by_source(source: str, source_name: str = ""):
    """按来源列出工具"""
    svc = get_tool_service()
    return {"tools": svc.list_by_source(source, source_name)}
