"""
动态配置加载模块

负责加载 YAML 配置文件，并支持热重载。
"""

import yaml
from pathlib import Path
from typing import Any, Dict
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.logger import log


@dataclass
class DynamicConfig:
    """动态业务配置数据结构"""
    
    # 会话管理
    session: Dict[str, Any] = field(default_factory=lambda: {
        "global_users": [],
        "per_user_groups": [],
        "all_groups_per_user": False
    })
    
    # 消息聚合器配置
    aggregator: Dict[str, Any] = field(default_factory=lambda: {
        "initial_wait": 10.0,
        "extended_wait": 15.0,
        "density_enabled": False,
        "density_threshold": 10,
        "density_window": 60.0,
        "density_cooldown": 60.0,
    })

    # 私聊消息聚合器配置
    private_aggregator: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "initial_wait": 3.0,
        "extended_wait": 5.0,
    })

    # 社交人格运行时
    social: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "quiet_hour_start": 1,
        "quiet_hour_end": 7,
        "familiar_threshold": 12,
        "lively_threshold": 4,
        "recent_window_seconds": 180,
        "max_prompt_chars": 1400,
    })
    
    # 提示词预设
    presets: Dict[str, Any] = field(default_factory=dict)
    
    # 插件开关
    plugins: Dict[str, bool] = field(default_factory=dict)

    # LLM 动态配置
    llm: Dict[str, Any] = field(default_factory=lambda: {
        "openai_api_key": "",
        "openai_api_base": "https://api.openai.com/v1",
        "google_api_key": "",
        "default_model": "gpt-4o-mini",
        "models": []
    })

    # 管理后台配置
    admin: Dict[str, Any] = field(default_factory=lambda: {
        "username": "admin",
        "password": "admin123",
        "port": 8088,
        "secret_key": "change-me-to-a-random-string",
        "cors_origins": [
            "http://127.0.0.1:8088",
            "http://localhost:8088",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        "allow_query_token": False,
    })

    # 原始 YAML 数据（供未映射到 dataclass 字段的配置块使用，如 telegram）
    _raw: Dict[str, Any] = field(default_factory=dict)

    # 运维调优参数
    tuning: Dict[str, Any] = field(default_factory=lambda: {
        # Agent
        "max_agent_loops": 15,
        # 熔断器
        "llm_failure_threshold": 5,
        "llm_recovery_timeout": 60.0,
        "onebot_failure_threshold": 10,
        "onebot_recovery_timeout": 30.0,
        "media_failure_threshold": 8,
        "media_recovery_timeout": 30.0,
        # 网络
        "download_timeout": 30.0,
        "api_timeout": 30,
        "ws_max_message_size_mb": 200,
        # 音频
        "audio_max_duration_seconds": 55,
        # 知识库搜索
        "knowledge_vector_search_limit": 200,
        "knowledge_cosine_threshold": 0.3,
        "knowledge_bm25_weight": 0.4,
        "knowledge_vector_weight": 0.6,
        # OpenClaw sub-agent
        "openclaw_timeout": 120,
        "openclaw_model": "default",
        "openclaw_stream_chunk_timeout": 30,
        "openclaw_system_prompt": "",
    })


class ConfigFileHandler(FileSystemEventHandler):
    """监听配置文件变化"""
    
    def __init__(self, loader):
        self.loader = loader
    
    def on_modified(self, event):
        if event.src_path.endswith("config.yaml"):
            log.info(f"Config file changed: {event.src_path}")
            self.loader.reload()


class ConfigLoader:
    """配置加载器 (支持热重载)"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path).resolve()
        self.config = DynamicConfig()
        self._callbacks = []
        self._observer = None
        
        # 初始加载
        self.reload()
        
        # 启动监听
        self._start_watching()
    
    def reload(self):
        """重新加载配置"""
        try:
            if not self.config_path.exists():
                log.warning(f"Config file not found: {self.config_path}, creating default.")
                self._create_default_config()
            
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            
            # 更新配置对象
            self.config.session = data.get("session", self.config.session)
            self.config.aggregator = data.get("aggregator", self.config.aggregator)
            self.config.private_aggregator = data.get("private_aggregator", self.config.private_aggregator)
            self.config.social = {**DynamicConfig().social, **data.get("social", {})}
            self.config.presets = data.get("presets", self.config.presets)
            self.config.plugins = data.get("plugins", self.config.plugins)
            self.config.llm = {**DynamicConfig().llm, **data.get("llm", {})}
            self.config.admin = {**DynamicConfig().admin, **data.get("admin", {})}
            self.config.tuning = {**DynamicConfig().tuning, **data.get("tuning", {})}
            self.config._raw = data

            log.success(f"Config loaded from {self.config_path}")
            
            # 触发回调
            for callback in self._callbacks:
                try:
                    callback(self.config)
                except Exception as e:
                    log.error(f"Config callback error: {e}")
                    
        except Exception as e:
            log.error(f"Failed to load config: {e}")
    
    def _create_default_config(self):
        """创建默认配置文件"""
        default_data = {
            "session": {
                "global_users": [],       # 全局用户模式 QQ号列表
                "per_user_groups": [],    # 强制用户隔离的群号列表
                "all_groups_per_user": False  # 是否所有群开启用户隔离
            },
            "plugins": {
                "weather": True,
                "search": False
            },
            "presets": {
                "default": {
                    "system_prompt": "你是一个有帮助的AI助手。"
                }
            }
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(default_data, f, allow_unicode=True, sort_keys=False)
    
    def _start_watching(self):
        """启动文件监听"""
        try:
            handler = ConfigFileHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self.config_path.parent), recursive=False)
            self._observer.start()
            log.info(f"Watching config file: {self.config_path}")
        except Exception as e:
            log.warning(f"Failed to start config watcher: {e}")
    
    def add_callback(self, callback):
        """添加配置变更回调"""
        self._callbacks.append(callback)

    def get_fallback_llm_models(
        self,
        api_key: str = "",
        base_url: str = "",
        default_model: str = "",
    ) -> list[dict[str, Any]]:
        """获取标准化后的 fallback LLM 模型列表。"""
        raw_models = self.config.llm.get("models", [])
        if not isinstance(raw_models, list):
            return []

        normalized_models = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue

            model_cfg = dict(item)
            model_cfg.setdefault("api_key", api_key)
            model_cfg.setdefault("base_url", base_url)
            model_cfg.setdefault("model", default_model)
            normalized_models.append(model_cfg)

        return normalized_models
    
    def stop(self):
        """停止监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()

# 全局单例
_loader = None

def get_config_loader() -> ConfigLoader:
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader


def reset_config_loader():
    """重置全局 ConfigLoader 单例（用于测试）"""
    global _loader
    if _loader is not None:
        _loader.stop()
    _loader = None


def get_tuning(key: str, default=None):
    """从 tuning 配置中读取值，config_loader 未初始化时返回 default"""
    global _loader
    if _loader is None:
        return default
    return _loader.config.tuning.get(key, default)
