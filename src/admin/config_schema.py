from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.utils.config_loader import DynamicConfig


ONEBOT_DEFAULTS = {
    "ws_url": "ws://127.0.0.1:3001",
    "reverse_ws_host": "127.0.0.1",
    "reverse_ws_port": 5140,
    "reverse_ws_path": "/onebot",
    "token": "",
    "mode": "reverse",
}

AGENT_DEFAULTS = {
    "bot_names": ["???", "bot"],
    "bot_qq": 0,
    "allow_at_reply": True,
    "allow_private": True,
    "allow_all_group_msg": False,
    "random_reply_freq": 0.0,
    "msg_cooldown": 3,
    "default_preset": "default",
    "silent_errors": False,
    "max_history_messages": 200,
    "voice_mode": "auto",
    "stt_provider": "noop",
    "stt_api_base": "",
    "stt_api_key": "",
    "stt_model": "whisper-1",
}

LLM_DEFAULTS = {
    "openai_api_key": "",
    "openai_api_base": "https://api.openai.com/v1",
    "google_api_key": "",
    "default_model": "gpt-4o-mini",
    "models": [],
}

EMBEDDINGS_DEFAULTS = {
    "model": "text-embedding-3-small",
    "api_key": "",
    "api_base": "",
}

OBSERVABILITY_DEFAULTS = {
    "log_level": "INFO",
    "langchain_tracing_v2": False,
    "langchain_api_key": "",
    "langchain_project": "langgraph-qq-agent",
}

INTEGRATIONS_DEFAULTS = {
    "brave_search_api_key": "",
    "openclaw_gateway_url": "http://127.0.0.1:18789",
    "openclaw_gateway_token": "",
    "tg_proxy": "",
}

TELEGRAM_DEFAULTS = {
    "enabled": False,
    "api_id": 0,
    "api_hash": "",
    "phone": "",
    "session_name": "tg_session",
    "proxy_url": "",
    "monitor": {
        "groups": [],
        "keywords": [],
        "min_length": 20,
        "aggregate_seconds": 60,
        "cooldown_seconds": 300,
        "summarize": True,
    },
    "broadcast": {
        "tg_self": True,
        "qq_groups": [],
        "qq_users": [],
    },
}

PLUGIN_DEFAULTS = {
    "weather": True,
    "search": False,
}

PRESET_DEFAULTS = {
    "default": {
        "system_prompt": "???????? AI ???"
    }
}


CONFIG_SCHEMA = [
    {
        "key": "admin",
        "title": "Admin Console",
        "description": "????????????????",
        "fields": [
            {"key": "username", "label": "Username", "type": "string", "help": "?????????"},
            {"key": "password", "label": "Password", "type": "password", "help": "????????"},
            {"key": "port", "label": "Port", "type": "int", "help": "????????"},
            {"key": "secret_key", "label": "JWT Secret", "type": "password", "help": "??????? JWT?"},
        ],
    },
    {
        "key": "onebot",
        "title": "OneBot / NapCat",
        "description": "??????????????? config.yaml??????????",
        "fields": [
            {"key": "ws_url", "label": "Forward WS URL", "type": "string", "help": "?? WebSocket ???"},
            {"key": "reverse_ws_host", "label": "Reverse WS Host", "type": "string", "help": "?? WebSocket ?????"},
            {"key": "reverse_ws_port", "label": "Reverse WS Port", "type": "int", "help": "?? WebSocket ?????"},
            {"key": "reverse_ws_path", "label": "Reverse WS Path", "type": "string", "help": "?? WebSocket ???"},
            {"key": "token", "label": "Access Token", "type": "password", "help": "OneBot ?????"},
            {"key": "mode", "label": "Mode", "type": "string", "help": "forward / reverse / both?"},
        ],
    },
    {
        "key": "agent",
        "title": "Agent Runtime",
        "description": "??????????????????/STT ????????",
        "fields": [
            {"key": "bot_names", "label": "Bot Names", "type": "string_list", "help": "???????????????"},
            {"key": "bot_qq", "label": "Bot QQ", "type": "int", "help": "????? QQ ??"},
            {"key": "allow_at_reply", "label": "Allow @ Reply", "type": "bool", "help": "???? @ ???"},
            {"key": "allow_private", "label": "Allow Private", "type": "bool", "help": "???????"},
            {"key": "allow_all_group_msg", "label": "Allow All Group Messages", "type": "bool", "help": "??????????"},
            {"key": "random_reply_freq", "label": "Random Reply Frequency", "type": "float", "help": "???????"},
            {"key": "msg_cooldown", "label": "Message Cooldown", "type": "int", "help": "??????????"},
            {"key": "default_preset", "label": "Default Preset", "type": "string", "help": "??????"},
            {"key": "silent_errors", "label": "Silent Errors", "type": "bool", "help": "????????????"},
            {"key": "max_history_messages", "label": "Max History Messages", "type": "int", "help": "???????????????"},
            {"key": "voice_mode", "label": "Voice Mode", "type": "string", "help": "stt / native / auto?"},
            {"key": "stt_provider", "label": "STT Provider", "type": "string", "help": "STT ??????"},
            {"key": "stt_api_base", "label": "STT API Base", "type": "string", "help": "STT ?????"},
            {"key": "stt_api_key", "label": "STT API Key", "type": "password", "help": "STT ?????"},
            {"key": "stt_model", "label": "STT Model", "type": "string", "help": "STT ????"},
        ],
    },
    {
        "key": "session",
        "title": "Session Routing",
        "description": "??????????",
        "fields": [
            {"key": "global_users", "label": "Global Users", "type": "int_list", "help": "??????????????? QQ ??"},
            {"key": "per_user_groups", "label": "Per-user Groups", "type": "int_list", "help": "???????????????????"},
            {"key": "all_groups_per_user", "label": "All Groups Per User", "type": "bool", "help": "????????????"},
        ],
    },
    {
        "key": "aggregator",
        "title": "Group Aggregator",
        "description": "????????????",
        "fields": [
            {"key": "initial_wait", "label": "Initial Wait", "type": "float", "help": "????????????????"},
            {"key": "extended_wait", "label": "Extended Wait", "type": "float", "help": "??????????????????"},
            {"key": "density_enabled", "label": "Density Enabled", "type": "bool", "help": "???????????"},
            {"key": "density_threshold", "label": "Density Threshold", "type": "int", "help": "??????????"},
            {"key": "density_window", "label": "Density Window", "type": "float", "help": "??????????"},
            {"key": "density_cooldown", "label": "Density Cooldown", "type": "float", "help": "??????????????"},
        ],
    },
    {
        "key": "private_aggregator",
        "title": "Private Aggregator",
        "description": "????????",
        "fields": [
            {"key": "enabled", "label": "Enabled", "type": "bool", "help": "?????????"},
            {"key": "initial_wait", "label": "Initial Wait", "type": "float", "help": "????????????????"},
            {"key": "extended_wait", "label": "Extended Wait", "type": "float", "help": "??????????????????"},
        ],
    },
    {
        "key": "llm",
        "title": "LLM Provider + Fallback",
        "description": "???????????????????? config.yaml?",
        "fields": [
            {"key": "default_model", "label": "Default Model", "type": "string", "help": "??????"},
            {"key": "openai_api_base", "label": "OpenAI API Base", "type": "string", "help": "OpenAI ???????"},
            {"key": "openai_api_key", "label": "OpenAI API Key", "type": "password", "help": "? LLM API Key?"},
            {"key": "google_api_key", "label": "Google API Key", "type": "password", "help": "Google ??? API Key?"},
            {"key": "models", "label": "Fallback Models", "type": "llm_models", "help": "???????????????"},
        ],
    },
    {
        "key": "embeddings",
        "title": "Embeddings",
        "description": "???????????",
        "fields": [
            {"key": "model", "label": "Embedding Model", "type": "string", "help": "??????"},
            {"key": "api_base", "label": "Embedding API Base", "type": "string", "help": "Embedding ??????????? LLM base?"},
            {"key": "api_key", "label": "Embedding API Key", "type": "password", "help": "Embedding ??????????? LLM key?"},
        ],
    },
    {
        "key": "telegram",
        "title": "Telegram Monitor",
        "description": "Telegram ???????????????????????????",
        "fields": [
            {"key": "enabled", "label": "Enabled", "type": "bool", "help": "???? Telegram ???"},
            {"key": "api_id", "label": "API ID", "type": "int", "help": "Telegram API ID?"},
            {"key": "api_hash", "label": "API Hash", "type": "password", "help": "Telegram API Hash?"},
            {"key": "phone", "label": "Phone", "type": "string", "help": "????????????"},
            {"key": "session_name", "label": "Session Name", "type": "string", "help": "session ??????? data/ ???"},
            {"key": "proxy_url", "label": "Proxy URL", "type": "string", "help": "??????? socks5://host:port?"},
            {"key": "monitor.groups", "label": "Monitor Groups", "type": "mixed_list", "help": "????? username ? chat_id??????"},
            {"key": "monitor.keywords", "label": "Keywords", "type": "string_list", "help": "????????????????"},
            {"key": "monitor.min_length", "label": "Min Length", "type": "int", "help": "?????????????"},
            {"key": "monitor.aggregate_seconds", "label": "Aggregate Seconds", "type": "float", "help": "????????"},
            {"key": "monitor.cooldown_seconds", "label": "Cooldown Seconds", "type": "float", "help": "???????????????"},
            {"key": "monitor.summarize", "label": "Summarize", "type": "bool", "help": "???? Agent ???????"},
            {"key": "broadcast.tg_self", "label": "Broadcast to TG Saved", "type": "bool", "help": "????? Telegram Saved Messages?"},
            {"key": "broadcast.qq_groups", "label": "QQ Groups", "type": "int_list", "help": "???? QQ ????????"},
            {"key": "broadcast.qq_users", "label": "QQ Users", "type": "int_list", "help": "???? QQ ???????"},
        ],
    },
    {
        "key": "observability",
        "title": "Logging + LangSmith",
        "description": "????? LangSmith ?????",
        "fields": [
            {"key": "log_level", "label": "Log Level", "type": "string", "help": "DEBUG / INFO / WARNING / ERROR?"},
            {"key": "langchain_tracing_v2", "label": "LangSmith Tracing", "type": "bool", "help": "???? LangSmith tracing?"},
            {"key": "langchain_api_key", "label": "LangSmith API Key", "type": "password", "help": "LangSmith API Key?"},
            {"key": "langchain_project", "label": "LangSmith Project", "type": "string", "help": "LangSmith ????"},
        ],
    },
    {
        "key": "integrations",
        "title": "External Integrations",
        "description": "Brave Search?OpenClaw?TG_PROXY ???????????",
        "fields": [
            {"key": "brave_search_api_key", "label": "Brave Search API Key", "type": "password", "help": "Web ??????? Brave Search API Key?"},
            {"key": "openclaw_gateway_url", "label": "OpenClaw Gateway URL", "type": "string", "help": "OpenClaw Gateway ???"},
            {"key": "openclaw_gateway_token", "label": "OpenClaw Gateway Token", "type": "password", "help": "OpenClaw Gateway ?????"},
            {"key": "tg_proxy", "label": "TG Proxy", "type": "string", "help": "?????? Telegram ?????"},
        ],
    },
    {
        "key": "plugins",
        "title": "Plugins",
        "description": "???????????????? config.yaml?",
        "fields": [
            {"key": "items", "path": "", "label": "Plugin Toggles", "type": "bool_map", "help": "????????"},
        ],
    },
    {
        "key": "tuning",
        "title": "Tuning",
        "description": "??????????????????",
        "fields": [
            {"key": "max_agent_loops", "label": "Max Agent Loops", "type": "int", "help": "?? Agent ?????????"},
            {"key": "llm_failure_threshold", "label": "LLM Failure Threshold", "type": "int", "help": "?? LLM ??????????"},
            {"key": "llm_recovery_timeout", "label": "LLM Recovery Timeout", "type": "float", "help": "LLM ??????????"},
            {"key": "onebot_failure_threshold", "label": "OneBot Failure Threshold", "type": "int", "help": "?? OneBot ??????????"},
            {"key": "onebot_recovery_timeout", "label": "OneBot Recovery Timeout", "type": "float", "help": "OneBot ??????????"},
            {"key": "media_failure_threshold", "label": "Media Failure Threshold", "type": "int", "help": "????????????????"},
            {"key": "media_recovery_timeout", "label": "Media Recovery Timeout", "type": "float", "help": "??????????????"},
            {"key": "download_timeout", "label": "Download Timeout", "type": "float", "help": "??????????"},
            {"key": "api_timeout", "label": "API Timeout", "type": "int", "help": "OneBot API ????????"},
            {"key": "ws_max_message_size_mb", "label": "WS Max Size (MB)", "type": "int", "help": "WebSocket ???????"},
            {"key": "audio_max_duration_seconds", "label": "Audio Max Duration", "type": "int", "help": "????????????"},
            {"key": "knowledge_vector_search_limit", "label": "Knowledge Vector Limit", "type": "int", "help": "??????????"},
            {"key": "knowledge_cosine_threshold", "label": "Knowledge Cosine Threshold", "type": "float", "help": "???????????"},
            {"key": "knowledge_bm25_weight", "label": "Knowledge BM25 Weight", "type": "float", "help": "???? BM25 ???"},
            {"key": "knowledge_vector_weight", "label": "Knowledge Vector Weight", "type": "float", "help": "?????????"},
            {"key": "openclaw_timeout", "label": "OpenClaw Timeout", "type": "int", "help": "OpenClaw ???????"},
            {"key": "openclaw_model", "label": "OpenClaw Model", "type": "string", "help": "OpenClaw ? Agent ????"},
            {"key": "openclaw_stream_chunk_timeout", "label": "OpenClaw Stream Chunk Timeout", "type": "int", "help": "?????????"},
            {"key": "openclaw_system_prompt", "label": "OpenClaw System Prompt", "type": "textarea", "help": "????????????"},
        ],
    },
    {
        "key": "presets",
        "title": "Preset Templates",
        "description": "config.yaml ?????????? Presets ???????",
        "fields": [
            {"key": "items", "path": "", "label": "Preset Templates", "type": "preset_map", "help": "??? -> system_prompt?"},
        ],
    },
]


def build_default_config() -> dict[str, Any]:
    dynamic = DynamicConfig()
    return {
        "admin": deepcopy(dynamic.admin),
        "onebot": deepcopy(ONEBOT_DEFAULTS),
        "agent": deepcopy(AGENT_DEFAULTS),
        "session": deepcopy(dynamic.session),
        "aggregator": deepcopy(dynamic.aggregator),
        "private_aggregator": deepcopy(dynamic.private_aggregator),
        "llm": deepcopy(LLM_DEFAULTS),
        "embeddings": deepcopy(EMBEDDINGS_DEFAULTS),
        "telegram": deepcopy(TELEGRAM_DEFAULTS),
        "observability": deepcopy(OBSERVABILITY_DEFAULTS),
        "integrations": deepcopy(INTEGRATIONS_DEFAULTS),
        "plugins": deepcopy(PLUGIN_DEFAULTS),
        "tuning": deepcopy(dynamic.tuning),
        "presets": deepcopy(PRESET_DEFAULTS),
    }


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        merged = deepcopy(base)
        for key, value in override.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged
    return deepcopy(override)


def get_by_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    if not path:
        return data
    cur: Any = data
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def set_by_path(data: dict[str, Any], path: str, value: Any) -> None:
    if not path:
        if isinstance(value, dict):
            data.clear()
            data.update(value)
        return
    cur = data
    parts = path.split('.')
    for part in parts[:-1]:
        next_value = cur.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cur[part] = next_value
        cur = next_value
    cur[parts[-1]] = value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int_list(value: Any) -> list[int]:
    items = value if isinstance(value, list) else []
    result: list[int] = []
    for item in items:
        if item in ("", None):
            continue
        result.append(int(item))
    return result


def _coerce_string_list(value: Any) -> list[str]:
    items = value if isinstance(value, list) else []
    return [str(item).strip() for item in items if str(item).strip()]


def _coerce_mixed_list(value: Any) -> list[Any]:
    items = value if isinstance(value, list) else []
    result: list[Any] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, int):
            result.append(item)
            continue
        text = str(item).strip()
        if not text:
            continue
        result.append(int(text) if text.lstrip('-').isdigit() else text)
    return result


def _coerce_bool_map(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _coerce_bool(val) for key, val in value.items() if str(key).strip()}


def _coerce_preset_map(value: Any) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    presets: dict[str, dict[str, str]] = {}
    for key, val in value.items():
        name = str(key).strip()
        if not name:
            continue
        prompt = str(val.get("system_prompt", "")) if isinstance(val, dict) else str(val)
        presets[name] = {"system_prompt": prompt}
    return presets


def _coerce_llm_models(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model", "")).strip()
        api_key = str(item.get("api_key", "")).strip()
        base_url = str(item.get("base_url", "")).strip()
        if not any([model, api_key, base_url]):
            continue
        row: dict[str, Any] = {"model": model}
        if api_key:
            row["api_key"] = api_key
        if base_url:
            row["base_url"] = base_url
        items.append(row)
    return items


def coerce_value(field_type: str, value: Any) -> Any:
    if field_type == "bool":
        return _coerce_bool(value)
    if field_type == "int":
        return int(value or 0)
    if field_type == "float":
        return float(value or 0)
    if field_type in {"string", "password", "textarea"}:
        return "" if value is None else str(value)
    if field_type == "int_list":
        return _coerce_int_list(value)
    if field_type == "string_list":
        return _coerce_string_list(value)
    if field_type == "mixed_list":
        return _coerce_mixed_list(value)
    if field_type == "bool_map":
        return _coerce_bool_map(value)
    if field_type == "preset_map":
        return _coerce_preset_map(value)
    if field_type == "llm_models":
        return _coerce_llm_models(value)
    return value


FIELD_EFFECTS: dict[str, dict[str, str]] = {
    "admin.username": {"kind": "new_login", "label": "New Login", "detail": "Applies to future admin logins only."},
    "admin.password": {"kind": "new_login", "label": "New Login", "detail": "Applies to future admin logins only."},
    "admin.port": {"kind": "restart", "label": "Restart Required", "detail": "Admin server port changes require restarting the service."},
    "admin.secret_key": {"kind": "relogin", "label": "Re-login", "detail": "JWT secret changes invalidate existing admin tokens."},

    "onebot.ws_url": {"kind": "reconnect", "label": "Reconnect", "detail": "Current forward connection is closed and reconnected with the new URL."},
    "onebot.token": {"kind": "reconnect", "label": "Reconnect", "detail": "Current OneBot connection is re-authenticated with the new token."},
    "onebot.mode": {"kind": "restart", "label": "Restart Required", "detail": "Changing listener mode requires restarting the adapter."},
    "onebot.reverse_ws_host": {"kind": "restart", "label": "Restart Required", "detail": "Reverse WS listener host is fixed after startup."},
    "onebot.reverse_ws_port": {"kind": "restart", "label": "Restart Required", "detail": "Reverse WS listener port is fixed after startup."},
    "onebot.reverse_ws_path": {"kind": "restart", "label": "Restart Required", "detail": "Reverse WS listener path is fixed after startup."},

    "agent.bot_names": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Trigger names are refreshed immediately."},
    "agent.allow_at_reply": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Mention handling updates immediately."},
    "agent.allow_private": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Private-message handling updates immediately."},
    "agent.allow_all_group_msg": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Group trigger strategy updates immediately."},
    "agent.default_preset": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Default system prompt is rebuilt immediately."},
    "agent.voice_mode": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Audio handling mode refreshes immediately."},
    "agent.stt_provider": {"kind": "hot_reload", "label": "Hot Reload", "detail": "STT provider instance refreshes immediately."},
    "agent.stt_api_base": {"kind": "hot_reload", "label": "Hot Reload", "detail": "STT runtime settings refresh immediately."},
    "agent.stt_api_key": {"kind": "hot_reload", "label": "Hot Reload", "detail": "STT runtime settings refresh immediately."},
    "agent.stt_model": {"kind": "hot_reload", "label": "Hot Reload", "detail": "STT runtime settings refresh immediately."},
    "agent.bot_qq": {"kind": "restart", "label": "Restart Required", "detail": "Bot identity is bound during startup in multiple components."},
    "agent.random_reply_freq": {"kind": "stored_only", "label": "Stored Only", "detail": "Currently stored in config but not wired into live runtime behavior."},
    "agent.msg_cooldown": {"kind": "stored_only", "label": "Stored Only", "detail": "Currently stored in config but not wired into live runtime behavior."},
    "agent.silent_errors": {"kind": "next_request", "label": "Next Request", "detail": "Takes effect on subsequent message processing."},
    "agent.max_history_messages": {"kind": "restart", "label": "Restart Required", "detail": "Memory store retention is fixed when the store is created."},

    "session.global_users": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Session routing reads the latest config dynamically."},
    "session.per_user_groups": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Session routing reads the latest config dynamically."},
    "session.all_groups_per_user": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Session routing reads the latest config dynamically."},

    "aggregator.initial_wait": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "aggregator.extended_wait": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "aggregator.density_enabled": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "aggregator.density_threshold": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "aggregator.density_window": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "aggregator.density_cooldown": {"kind": "restart", "label": "Restart Required", "detail": "Existing aggregators are created only during startup."},
    "private_aggregator.enabled": {"kind": "restart", "label": "Restart Required", "detail": "Private aggregators are created only during startup."},
    "private_aggregator.initial_wait": {"kind": "restart", "label": "Restart Required", "detail": "Private aggregators are created only during startup."},
    "private_aggregator.extended_wait": {"kind": "restart", "label": "Restart Required", "detail": "Private aggregators are created only during startup."},

    "llm.default_model": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Agent runtime is rebuilt with the new primary model immediately."},
    "llm.openai_api_base": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Agent runtime is rebuilt with the new base URL immediately."},
    "llm.openai_api_key": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Agent runtime is rebuilt with the new API key immediately."},
    "llm.models": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Fallback model list refreshes immediately."},
    "llm.google_api_key": {"kind": "next_request", "label": "Next Request", "detail": "Applied the next time a Google-backed provider is used."},

    "embeddings.model": {"kind": "next_request", "label": "Next Request", "detail": "Embedding calls load the latest settings when invoked."},
    "embeddings.api_base": {"kind": "next_request", "label": "Next Request", "detail": "Embedding calls load the latest settings when invoked."},
    "embeddings.api_key": {"kind": "next_request", "label": "Next Request", "detail": "Embedding calls load the latest settings when invoked."},

    "telegram.enabled": {"kind": "restart", "label": "Restart Required", "detail": "Telegram monitoring task is only constructed during startup."},
    "telegram.api_id": {"kind": "restart", "label": "Restart Required", "detail": "Telegram client credentials are only applied when the adapter is created."},
    "telegram.api_hash": {"kind": "restart", "label": "Restart Required", "detail": "Telegram client credentials are only applied when the adapter is created."},
    "telegram.phone": {"kind": "restart", "label": "Restart Required", "detail": "Phone-based login is only used during adapter startup."},
    "telegram.session_name": {"kind": "restart", "label": "Restart Required", "detail": "Session file path is bound when the adapter is created."},
    "telegram.proxy_url": {"kind": "restart", "label": "Restart Required", "detail": "Proxy changes require a fresh Telegram connection."},
    "telegram.monitor.groups": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures monitor targets during startup."},
    "telegram.monitor.keywords": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures keyword filters during startup."},
    "telegram.monitor.min_length": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures monitor thresholds during startup."},
    "telegram.monitor.aggregate_seconds": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures monitor thresholds during startup."},
    "telegram.monitor.cooldown_seconds": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures monitor thresholds during startup."},
    "telegram.monitor.summarize": {"kind": "restart", "label": "Restart Required", "detail": "NewsMonitor captures summarize mode during startup."},
    "telegram.broadcast.tg_self": {"kind": "restart", "label": "Restart Required", "detail": "Broadcast dispatcher is constructed during startup."},
    "telegram.broadcast.qq_groups": {"kind": "restart", "label": "Restart Required", "detail": "Broadcast dispatcher is constructed during startup."},
    "telegram.broadcast.qq_users": {"kind": "restart", "label": "Restart Required", "detail": "Broadcast dispatcher is constructed during startup."},

    "observability.log_level": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Logger level updates immediately."},
    "observability.langchain_tracing_v2": {"kind": "restart", "label": "Restart Required", "detail": "LangSmith env wiring is not refreshed in the main app runtime."},
    "observability.langchain_api_key": {"kind": "restart", "label": "Restart Required", "detail": "LangSmith env wiring is not refreshed in the main app runtime."},
    "observability.langchain_project": {"kind": "restart", "label": "Restart Required", "detail": "LangSmith env wiring is not refreshed in the main app runtime."},

    "integrations.brave_search_api_key": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next web search tool invocation."},
    "integrations.openclaw_gateway_url": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw tool invocation."},
    "integrations.openclaw_gateway_token": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw tool invocation."},
    "integrations.tg_proxy": {"kind": "restart", "label": "Restart Required", "detail": "Telegram proxy changes require rebuilding the Telegram connection."},

    "plugins": {"kind": "stored_only", "label": "Stored Only", "detail": "Plugin toggles are visible and saved, but not yet wired into runtime reload."},

    "tuning.max_agent_loops": {"kind": "next_request", "label": "Next Request", "detail": "Read dynamically when a new agent execution starts."},
    "tuning.llm_failure_threshold": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.llm_recovery_timeout": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.onebot_failure_threshold": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.onebot_recovery_timeout": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.media_failure_threshold": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.media_recovery_timeout": {"kind": "restart", "label": "Restart Required", "detail": "Existing circuit-breaker instances keep their thresholds until restart."},
    "tuning.download_timeout": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next media download."},
    "tuning.api_timeout": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OneBot API call."},
    "tuning.ws_max_message_size_mb": {"kind": "reconnect", "label": "Reconnect", "detail": "Applied when the WebSocket connection is reopened."},
    "tuning.audio_max_duration_seconds": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next audio processing task."},
    "tuning.knowledge_vector_search_limit": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next knowledge search."},
    "tuning.knowledge_cosine_threshold": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next knowledge search."},
    "tuning.knowledge_bm25_weight": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next knowledge search."},
    "tuning.knowledge_vector_weight": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next knowledge search."},
    "tuning.openclaw_timeout": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw call."},
    "tuning.openclaw_model": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw call."},
    "tuning.openclaw_stream_chunk_timeout": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw call."},
    "tuning.openclaw_system_prompt": {"kind": "next_request", "label": "Next Request", "detail": "Applied on the next OpenClaw call."},

    "presets": {"kind": "hot_reload", "label": "Hot Reload", "detail": "Preset definitions are reloaded via ConfigLoader callbacks."},
}


def _field_effect(section_key: str, field: dict[str, Any]) -> dict[str, str]:
    path = field.get("path", field["key"])
    lookup_key = section_key if path == "" else f"{section_key}.{path}"
    return deepcopy(FIELD_EFFECTS.get(lookup_key, {"kind": "unknown", "label": "Unknown", "detail": "Effect has not been classified yet."}))


def _annotate_sections() -> list[dict[str, Any]]:
    sections = deepcopy(CONFIG_SCHEMA)
    for section in sections:
        for field in section["fields"]:
            field["effect"] = _field_effect(section["key"], field)
    return sections


def build_full_config(current_raw: dict[str, Any] | None = None, submitted: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = build_default_config()
    merged = deep_merge(defaults, current_raw or {})
    incoming = submitted or {}

    for section in CONFIG_SCHEMA:
        section_key = section["key"]
        section_payload = incoming.get(section_key)
        if section_payload is None:
            continue

        if section_key not in merged or not isinstance(merged.get(section_key), dict):
            merged[section_key] = {}

        for field in section["fields"]:
            path = field.get("path", field["key"])
            raw_value = section_payload if path == "" else get_by_path(section_payload, path)
            if raw_value is None and path != "":
                continue
            coerced = coerce_value(field["type"], raw_value)
            set_by_path(merged[section_key], path, coerced)

    return merged


def build_schema_payload(current_raw: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = build_default_config()
    values = deep_merge(defaults, current_raw or {})
    return {
        "sections": _annotate_sections(),
        "defaults": defaults,
        "values": values,
    }
