"""
.env 热加载模块

监听 .env 文件变化，自动重新加载环境变量。
"""

import os
from pathlib import Path
from typing import Callable
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from src.utils.logger import log


class EnvFileHandler(FileSystemEventHandler):
    """监听 .env 文件变化"""
    
    def __init__(self, loader: "EnvLoader"):
        self.loader = loader
    
    def on_modified(self, event):
        if event.src_path.endswith(".env"):
            log.info(f".env file changed: {event.src_path}")
            self.loader.reload()


class EnvLoader:
    """
    .env 文件加载器 (支持热重载)
    
    用法:
        loader = EnvLoader()
        loader.add_callback(lambda: print("env changed!"))
    """
    
    def __init__(self, env_path: str = ".env"):
        self.env_path = Path(env_path).resolve()
        self._callbacks: list[Callable[[], None]] = []
        self._observer: Observer | None = None
        
        # 初始加载
        self.reload()
        
        # 启动监听
        self._start_watching()
    
    def reload(self):
        """重新加载 .env 文件"""
        try:
            if not self.env_path.exists():
                log.warning(f".env file not found: {self.env_path}")
                return
            
            # 使用 override=True 覆盖已存在的环境变量
            load_dotenv(self.env_path, override=True)
            log.success(f".env reloaded from {self.env_path}")
            
            # 触发回调
            for callback in self._callbacks:
                try:
                    callback()
                except Exception as e:
                    log.error(f".env reload callback error: {e}")
                    
        except Exception as e:
            log.error(f"Failed to reload .env: {e}")
    
    def _start_watching(self):
        """启动文件监听"""
        try:
            handler = EnvFileHandler(self)
            self._observer = Observer()
            self._observer.schedule(handler, str(self.env_path.parent), recursive=False)
            self._observer.start()
            log.info(f"Watching .env file: {self.env_path}")
        except Exception as e:
            log.warning(f"Failed to start .env watcher: {e}")
    
    def add_callback(self, callback: Callable[[], None]):
        """添加 .env 变更回调"""
        self._callbacks.append(callback)
    
    def stop(self):
        """停止监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            log.info(".env watcher stopped")


# 全局单例
_env_loader: EnvLoader | None = None


def get_env_loader() -> EnvLoader:
    """获取全局 EnvLoader 实例"""
    global _env_loader
    if _env_loader is None:
        _env_loader = EnvLoader()
    return _env_loader
