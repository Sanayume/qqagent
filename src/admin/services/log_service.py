"""
日志服务

负责日志的收集、缓冲和 WebSocket 广播。
"""

import asyncio
from datetime import datetime
from collections import deque
from typing import Any

from fastapi import WebSocket

from src.utils.logger import log


class LogService:
    """日志服务"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self._history: deque = deque(maxlen=max_history)
        self._clients: set[WebSocket] = set()
        self._setup_sink()
        
    def _setup_sink(self):
        """配置 loguru sink"""
        log.add(self._log_sink, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="DEBUG")
        
    def _log_sink(self, message: Any):
        """Loguru sink 回调"""
        # message 是一个带有 record 属性的字符串对象
        record = message.record
        
        log_entry = {
            "time": record["time"].strftime("%Y-%m-%d %H:%M:%S"),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["name"],
            "line": record["line"],
            "timestamp": datetime.now().timestamp()
        }
        
        # 添加到历史
        self._history.append(log_entry)
        
        # 广播给客户端
        self._broadcast(log_entry)
        
    def _broadcast(self, data: dict):
        """广播日志"""
        if not self._clients:
            return

        # 安全地调度异步任务（处理无事件循环的情况）
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_to_clients(data))
        except RuntimeError:
            # 没有运行中的事件循环，尝试使用 call_soon_threadsafe
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(
                        lambda: loop.create_task(self._send_to_clients(data))
                    )
                # 如果循环没运行，跳过广播（日志仍会存入历史）
            except RuntimeError:
                pass  # 完全没有事件循环，跳过实时广播
        
    async def _send_to_clients(self, data: dict):
        """异步发送给所有客户端"""
        dead_clients = set()
        
        for ws in self._clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead_clients.add(ws)
                
        # 清理断开的连接
        for ws in dead_clients:
            self._clients.discard(ws)
            
    async def connect(self, ws: WebSocket):
        """处理新连接"""
        await ws.accept()
        self._clients.add(ws)
        
        # 发送最近的历史日志
        try:
            # 批量发送历史日志避免阻塞
            history_list = list(self._history)
            for i in range(0, len(history_list), 50):
                batch = history_list[i:i+50]
                for entry in batch:
                    await ws.send_json(entry)
        except Exception:
            self._clients.discard(ws)
            
    def disconnect(self, ws: WebSocket):
        """断开连接"""
        self._clients.discard(ws)


# 全局单例
_log_service: LogService | None = None

def get_log_service() -> LogService:
    global _log_service
    if _log_service is None:
        _log_service = LogService()
    return _log_service
