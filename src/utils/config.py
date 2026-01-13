"""Configuration management using pydantic-settings"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OneBotConfig(BaseSettings):
    """OneBot/NapCat connection settings"""
    
    model_config = SettingsConfigDict(env_prefix="ONEBOT_")
    
    # Forward WebSocket (Agent connects to NapCat)
    ws_url: str = Field(default="ws://127.0.0.1:3001", description="正向WS地址")
    
    # Reverse WebSocket (NapCat connects to Agent) 
    reverse_ws_host: str = Field(default="127.0.0.1", description="反向WS监听地址")
    reverse_ws_port: int = Field(default=5140, description="反向WS监听端口")
    reverse_ws_path: str = Field(default="/onebot", description="反向WS路径")
    
    # Authentication
    token: str = Field(default="", description="OneBot access token")
    
    # Connection mode
    mode: str = Field(default="reverse", description="连接模式: forward/reverse/both")


class LLMConfig(BaseSettings):
    """LLM provider settings"""
    
    model_config = SettingsConfigDict(extra="ignore")
    
    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_api_base: str = Field(default="https://api.openai.com/v1", alias="OPENAI_API_BASE")
    
    # Google
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    
    # Default model
    default_model: str = Field(default="gpt-4o-mini", alias="DEFAULT_MODEL")


class AgentConfig(BaseSettings):
    """Agent behavior settings"""

    model_config = SettingsConfigDict(env_prefix="AGENT_")

    # Bot identity
    bot_names: list[str] = Field(default=["琪露诺", "bot"], description="触发昵称")
    bot_qq: int = Field(default=0, description="机器人QQ号")
    
    # Trigger settings
    allow_at_reply: bool = Field(default=True, description="是否响应@")
    allow_private: bool = Field(default=True, description="是否响应私聊")
    random_reply_freq: float = Field(default=0.0, description="随机回复概率")
    msg_cooldown: int = Field(default=3, description="冷却时间(秒)")
    
    # Session settings
    session_global_users: set[int] = Field(default_factory=set, description="全局用户列表(共享上下文)")
    session_per_user_groups: set[int] = Field(default_factory=set, description="用户隔离的群列表")
    session_all_groups_per_user: bool = Field(default=False, description="是否所有群都用户隔离")
    
    # Preset
    default_preset: str = Field(default="default", description="默认预设")
    preset_dir: Path = Field(default=Path("config/presets"), description="预设目录")


class Settings(BaseSettings):
    """Main settings container"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL", description="日志级别: DEBUG/INFO/WARNING/ERROR")

    # LangSmith
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")
    langchain_project: str = Field(default="langgraph-qq-agent", alias="LANGCHAIN_PROJECT")


def load_settings() -> Settings:
    """Load settings from environment and .env file"""
    return Settings()
