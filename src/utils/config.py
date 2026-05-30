"""Configuration loading with env fallback and config.yaml overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OneBotConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ONEBOT_")

    ws_url: str = Field(default="ws://127.0.0.1:3001")
    reverse_ws_host: str = Field(default="127.0.0.1")
    reverse_ws_port: int = Field(default=5140)
    reverse_ws_path: str = Field(default="/onebot")
    token: str = Field(default="")
    mode: str = Field(default="reverse")


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_api_base: str = Field(default="https://api.openai.com/v1", alias="OPENAI_API_BASE")
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    default_model: str = Field(default="gpt-4o-mini", alias="DEFAULT_MODEL")


class EmbeddingsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    api_base: str = Field(default="", alias="EMBEDDING_API_BASE")


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    bot_names: list[str] = Field(default=["???", "bot"])
    bot_qq: int = Field(default=0)
    allow_at_reply: bool = Field(default=True)
    allow_private: bool = Field(default=True)
    allow_all_group_msg: bool = Field(default=False)
    random_reply_freq: float = Field(default=0.0)
    msg_cooldown: int = Field(default=3)
    session_global_users: set[int] = Field(default_factory=set)
    session_per_user_groups: set[int] = Field(default_factory=set)
    session_all_groups_per_user: bool = Field(default=False)
    default_preset: str = Field(default="default")
    preset_dir: Path = Field(default=Path("config/presets"))
    silent_errors: bool = Field(default=False)
    max_history_messages: int = Field(default=200)
    voice_mode: str = Field(default="auto")
    stt_provider: str = Field(default="noop")
    stt_api_base: str = Field(default="")
    stt_api_key: str = Field(default="")
    stt_model: str = Field(default="whisper-1")


class IntegrationsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    brave_search_api_key: str = Field(default="", alias="BRAVE_SEARCH_API_KEY")
    openclaw_gateway_url: str = Field(default="http://127.0.0.1:18789", alias="OPENCLAW_GATEWAY_URL")
    openclaw_gateway_token: str = Field(default="", alias="OPENCLAW_GATEWAY_TOKEN")
    tg_proxy: str = Field(default="", alias="TG_PROXY")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="langgraph-qq-agent", alias="LANGCHAIN_PROJECT")


def _load_yaml_config(config_path: str = "config.yaml") -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _apply_nested_overrides(target: Any, source: dict[str, Any], allowed_keys: list[str]) -> None:
    for key in allowed_keys:
        if key in source:
            setattr(target, key, source[key])


def load_settings(config_path: str = "config.yaml") -> Settings:
    settings = Settings()
    raw = _load_yaml_config(config_path)

    onebot_cfg = raw.get("onebot", {})
    if isinstance(onebot_cfg, dict):
        _apply_nested_overrides(
            settings.onebot,
            onebot_cfg,
            ["ws_url", "reverse_ws_host", "reverse_ws_port", "reverse_ws_path", "token", "mode"],
        )

    llm_cfg = raw.get("llm", {})
    if isinstance(llm_cfg, dict):
        _apply_nested_overrides(
            settings.llm,
            llm_cfg,
            ["openai_api_key", "openai_api_base", "google_api_key", "default_model"],
        )

    agent_cfg = raw.get("agent", {})
    if isinstance(agent_cfg, dict):
        _apply_nested_overrides(
            settings.agent,
            agent_cfg,
            [
                "bot_names",
                "bot_qq",
                "allow_at_reply",
                "allow_private",
                "allow_all_group_msg",
                "random_reply_freq",
                "msg_cooldown",
                "default_preset",
                "silent_errors",
                "max_history_messages",
                "voice_mode",
                "stt_provider",
                "stt_api_base",
                "stt_api_key",
                "stt_model",
            ],
        )

    embeddings_cfg = raw.get("embeddings", {})
    if isinstance(embeddings_cfg, dict):
        _apply_nested_overrides(
            settings.embeddings,
            embeddings_cfg,
            ["model", "api_key", "api_base"],
        )

    integrations_cfg = raw.get("integrations", {})
    if isinstance(integrations_cfg, dict):
        _apply_nested_overrides(
            settings.integrations,
            integrations_cfg,
            ["brave_search_api_key", "openclaw_gateway_url", "openclaw_gateway_token", "tg_proxy"],
        )

    observability_cfg = raw.get("observability", {})
    if isinstance(observability_cfg, dict):
        for key in ["log_level", "langchain_tracing_v2", "langchain_api_key", "langchain_project"]:
            if key in observability_cfg:
                setattr(settings, key, observability_cfg[key])

    return settings
