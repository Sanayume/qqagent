"""
MCP Management API
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from src.admin.services.mcp_service import get_mcp_service

router = APIRouter(prefix="/api/mcp", tags=["MCP"])

class MCPServerConfig(BaseModel):
    command: str
    args: list[str] = []
    env: Dict[str, str] = {}
    
class AddServerRequest(BaseModel):
    name: str
    config: MCPServerConfig

@router.get("/servers")
async def list_servers():
    svc = get_mcp_service()
    return svc.list_servers()

@router.get("/servers/{name}")
async def get_server(name: str):
    svc = get_mcp_service()
    server = svc.get_server(name)
    if not server:
        raise HTTPException(404, "Server not found")
    return server

@router.post("/servers")
async def add_server(req: AddServerRequest):
    svc = get_mcp_service()
    success = svc.add_server(req.name, req.config.dict())
    if not success:
        raise HTTPException(500, "Failed to save configuration")
    return {"status": "ok", "message": "Server added. Please restart Agent to apply changes."}

@router.put("/servers/{name}")
async def update_server(name: str, config: MCPServerConfig):
    svc = get_mcp_service()
    if not svc.get_server(name):
        raise HTTPException(404, "Server not found")
    
    success = svc.add_server(name, config.dict())
    if not success:
        raise HTTPException(500, "Failed to save configuration")
    return {"status": "ok", "message": "Server updated. Please restart Agent to apply changes."}

@router.delete("/servers/{name}")
async def delete_server(name: str):
    svc = get_mcp_service()
    if not svc.delete_server(name):
        raise HTTPException(404, "Server not found or failed to delete")
    return {"status": "ok", "message": "Server deleted. Please restart Agent to apply changes."}


@router.get("/status")
async def get_runtime_status():
    """获取 MCP 运行时状态"""
    svc = get_mcp_service()
    return await svc.get_runtime_status()


@router.post("/reload")
async def reload_all_servers():
    """重载所有 MCP 服务器"""
    svc = get_mcp_service()
    result = await svc.reload_all()
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Reload failed"))
    return result


@router.post("/servers/{name}/restart")
async def restart_server(name: str):
    """重启单个 MCP 服务器"""
    svc = get_mcp_service()
    result = await svc.restart_server(name)
    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Restart failed"))
    return result
