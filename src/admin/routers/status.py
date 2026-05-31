"""System status endpoints for the admin console."""

from __future__ import annotations

from fastapi import APIRouter

from src.admin.services.mcp_service import get_mcp_service
from src.admin.services.preset_service import get_preset_service
from src.admin.security import get_admin_security_warnings
from src.core.context import get_app_context
from src.utils.config_loader import get_config_loader

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("")
async def get_status():
    ctx = get_app_context()
    config_loader = get_config_loader()
    mcp_svc = get_mcp_service()
    preset_svc = get_preset_service()
    bot_app = ctx.get("bot_app")

    mcp_servers = mcp_svc.list_servers()
    preset_list = preset_svc.list_presets()
    if bot_app and bot_app.settings:
        current_preset = bot_app.settings.agent.default_preset
    elif ctx.preset_manager and ctx.preset_manager.get_default():
        current_preset = ctx.preset_manager.get_default().name
    else:
        current_preset = None

    runtime_status = bot_app.get_runtime_status() if bot_app else {
        "admin": {
            "port": config_loader.config.admin.get("port", 8088),
            "static_ready": False,
        },
        "agent": {
            "model": ctx.agent.model if ctx.agent else None,
            "base_url": ctx.agent.base_url if ctx.agent else None,
            "voice_mode": None,
            "default_preset": current_preset,
            "fallback_models": [],
            "fallback_count": 0,
        },
        "onebot": {
            "mode": None,
            "connected": ctx.is_adapter_connected,
            "forward_connected": False,
            "reverse_connected": False,
            "ws_url": None,
            "reverse_endpoint": None,
            "token_configured": False,
        },
        "telegram": {
            "enabled": bool(config_loader.config._raw.get("telegram", {}).get("enabled", False)),
            "running": False,
            "connected": False,
            "session_path": None,
            "has_proxy": False,
            "reconnect_attempt": 0,
            "last_error": None,
            "last_error_at": None,
            "last_connected_at": None,
            "monitor_channels": [],
            "monitor_keywords": [],
        },
        "reloads": {},
        "behavior": {
            "allow_at": None,
            "allow_private": None,
            "allow_all_group": None,
            "bot_names": [],
        },
    }

    mcp_runtime_status = {}
    if ctx.mcp_manager:
        for name in ctx.mcp_manager.servers:
            mcp_runtime_status[name] = ctx.mcp_manager.get_server_status(name)

    session_count = ctx.memory_store.get_session_count() if ctx.memory_store else 0

    return {
        "agent": {
            "status": "running" if ctx.is_agent_running else "stopped",
            "running": ctx.is_agent_running,
            "uptime": ctx.stats.uptime_formatted if ctx.is_agent_running else "N/A",
            "uptime_seconds": ctx.stats.uptime_seconds if ctx.is_agent_running else 0,
            "model": runtime_status["agent"]["model"],
            "base_url": runtime_status["agent"]["base_url"],
            "voice_mode": runtime_status["agent"]["voice_mode"],
            "default_preset": runtime_status["agent"]["default_preset"],
            "session_count": session_count,
            "messages_processed": ctx.stats.messages_processed,
            "errors_count": ctx.stats.errors_count,
            "last_message_time": ctx.stats.last_message_time.isoformat() if ctx.stats.last_message_time else None,
            "fallback_models": runtime_status["agent"]["fallback_models"],
            "fallback_count": runtime_status["agent"]["fallback_count"],
        },
        "onebot": runtime_status["onebot"],
        "telegram": runtime_status["telegram"],
        "admin": runtime_status["admin"],
        "behavior": runtime_status["behavior"],
        "reloads": runtime_status["reloads"],
        "scheduler": runtime_status.get("scheduler", {}),
        "social": runtime_status.get("social", {}),
        "config": runtime_status.get("config", {}),
        "security": {
            "warnings": get_admin_security_warnings(config_loader.config.admin),
        },
        "mcp": {
            "count": len(mcp_servers),
            "servers": list(mcp_servers.keys()),
            "runtime_status": mcp_runtime_status,
        },
        "presets": {
            "count": len(preset_list),
            "list": preset_list,
            "current": current_preset,
        },
        "aggregator": config_loader.config.aggregator,
        "stats": ctx.stats.to_dict(),
    }
