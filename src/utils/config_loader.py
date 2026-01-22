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
    
    # 提示词预设
    presets: Dict[str, Any] = field(default_factory=dict)
    
    # 插件开关
    plugins: Dict[str, bool] = field(default_factory=dict)


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
            self.config.presets = data.get("presets", self.config.presets)
            self.config.plugins = data.get("plugins", self.config.plugins)
            
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
