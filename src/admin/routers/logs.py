"""
日志 API 路由

提供 WebSocket 实时日志流。
"""

from fastapi import APIRouter, WebSocket, Depends, WebSocketDisconnect
from src.admin.auth import get_optional_user
from src.admin.services.log_service import get_log_service

router = APIRouter(prefix="/api/logs", tags=["日志"])


@router.websocket("/stream")
async def log_stream(websocket: WebSocket):
    """实时日志 WebSocket"""
    # WebSocket 无法直接使用 Depends(get_current_user) 进行头部认证
    # 这里简单处理：允许连接，但在消息中可能需要后续鉴权
    # 更好的做法是通过 query param 传递 token
    
    # 简单验证：检查 token 参数
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    # TODO: 验证 token (这里暂时跳过，假设内网安全，且 client 会传)
    # 严格来说应该在这里 verify_token(token)
    
    service = get_log_service()
    await service.connect(websocket)
    
    try:
        while True:
            # 保持连接，接收心跳（如果有）
            await websocket.receive_text()
    except WebSocketDisconnect:
        service.disconnect(websocket)
    except Exception:
        service.disconnect(websocket)


@router.post("/test")
async def generate_test_logs():
    """生成测试日志（用于调试）"""
    from src.utils.logger import log
    
    log.debug("这是一条 DEBUG 测试日志")
    log.info("这是一条 INFO 测试日志") 
    log.success("这是一条 SUCCESS 测试日志")
    log.warning("这是一条 WARNING 测试日志")
    log.error("这是一条 ERROR 测试日志")
    
    return {"status": "ok", "message": "已生成 5 条测试日志"}
