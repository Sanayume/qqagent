"""
状态 API

提供系统状态信息，通过 AppContext 获取真实运行状态。
"""

from fastapi import APIRouter
from pathlib import Path
import json

from src.admin.services.mcp_service import get_mcp_service
from src.admin.services.preset_service import get_preset_service
from src.core.context import get_app_context

router = APIRouter(prefix="/api/status", tags=["状态"])


@router.get("")
async def get_status():
    """获取系统状态"""
    ctx = get_app_context()
    mcp_svc = get_mcp_service()
    preset_svc = get_preset_service()

    # 获取 MCP 服务器数量
    mcp_servers = mcp_svc.list_servers()
    mcp_count = len(mcp_servers)
    mcp_names = list(mcp_servers.keys())

    # 获取预设列表
    presets = preset_svc.list_presets()
    preset_count = len(presets)

    # 获取当前使用的预设（从 config.yaml 读取）
    current_preset = "未知"
    config_path = Path("config.yaml")
    if config_path.exists():
        import yaml
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                # 尝试从配置中获取当前预设
                if config and "agent" in config:
                    current_preset = config["agent"].get("preset", "default")
                elif config and "presets" in config:
                    # 如果有 presets 配置，取第一个
                    current_preset = list(config.get("presets", {}).keys())[0] if config.get("presets") else "default"
        except Exception:
            pass

    # 使用 AppContext 获取真实 Agent 状态
    agent_status = "stopped"
    agent_uptime = "N/A"
    agent_model = None
    session_count = 0
    messages_processed = 0

    if ctx.is_agent_running:
        agent_status = "running"
        agent_uptime = ctx.stats.uptime_formatted
        agent_model = ctx.agent.model if ctx.agent else None
        messages_processed = ctx.stats.messages_processed

        if ctx.memory_store:
            session_count = ctx.memory_store.get_session_count()

    # 获取 MCP 运行时状态
    mcp_runtime_status = {}
    if ctx.mcp_manager:
        for name in ctx.mcp_manager.servers:
            status = ctx.mcp_manager.get_server_status(name)
            mcp_runtime_status[name] = status

    # 获取聚合器配置
    aggregator_config = {}
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                aggregator_config = config.get("aggregator", {})
        except Exception:
            pass

    return {
        "agent": {
            "status": agent_status,
            "uptime": agent_uptime,
            "model": agent_model,
            "session_count": session_count,
            "messages_processed": messages_processed,
        },
        "mcp": {
            "count": mcp_count,
            "servers": mcp_names,
            "runtime_status": mcp_runtime_status,
        },
        "presets": {
            "count": preset_count,
            "list": presets,
            "current": current_preset,
        },
        "aggregator": aggregator_config,
        "stats": ctx.stats.to_dict(),
    }
