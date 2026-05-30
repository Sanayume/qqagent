"""Log streaming endpoints."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.admin.auth import authenticate_websocket
from src.admin.services.log_service import get_log_service

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.websocket("/stream")
async def log_stream(websocket: WebSocket):
    user = await authenticate_websocket(websocket)
    if user is None:
        return

    service = get_log_service()
    await service.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        service.disconnect(websocket)
    except Exception:
        service.disconnect(websocket)


@router.post("/test")
async def generate_test_logs():
    from src.utils.logger import log

    log.debug("Admin console test log: DEBUG")
    log.info("Admin console test log: INFO")
    log.success("Admin console test log: SUCCESS")
    log.warning("Admin console test log: WARNING")
    log.error("Admin console test log: ERROR")

    return {"status": "ok", "message": "Generated 5 test log entries"}
