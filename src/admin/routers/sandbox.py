"""
沙盒 API 路由

提供沙盒环境的管理和交互接口。
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Literal

from src.admin.services.sandbox_service import get_sandbox_service, User, Group, Message

router = APIRouter(prefix="/api/sandbox", tags=["沙盒"])

# ==================== Request Models ====================

class CreateUserRequest(BaseModel):
    qq: int
    nickname: str
    avatar: str = ""

class CreateGroupRequest(BaseModel):
    group_id: int
    name: str
    members: list[int] = []

class SendMessageRequest(BaseModel):
    sender_qq: int
    content: str
    image: str = ""
    at_users: list[int] = []
    reply_to: int = 0
    chat_type: Literal["group", "private"] = "group"
    group_id: int | None = None
    target_qq: int | None = None


class RealAgentModeRequest(BaseModel):
    enabled: bool


# ==================== Routes ====================

@router.get("/state")
async def get_state():
    """获取完整沙盒状态"""
    svc = get_sandbox_service()
    return {
        "users": list(svc.users.values()),
        "groups": list(svc.groups.values()),
        "use_real_agent": svc.use_real_agent,
        "real_agent_available": svc.is_real_agent_available(),
        # 消息可能太多，只返回最近的
        "messages": svc.get_chat_messages("group", limit=100) + svc.get_chat_messages("private", limit=100)
    }

@router.get("/users")
async def list_users():
    svc = get_sandbox_service()
    return list(svc.users.values())

@router.post("/users")
async def create_user(req: CreateUserRequest):
    svc = get_sandbox_service()
    if req.qq in svc.users:
        raise HTTPException(400, "用户已存在")
    user = User(req.qq, req.nickname, req.avatar)
    svc.add_user(user)
    await svc.broadcast({"type": "user_update", "data": user.to_dict()})
    return user

@router.get("/groups")
async def list_groups():
    svc = get_sandbox_service()
    return list(svc.groups.values())

@router.post("/groups")
async def create_group(req: CreateGroupRequest):
    svc = get_sandbox_service()
    if req.group_id in svc.groups:
        raise HTTPException(400, "群已存在")
    group = Group(req.group_id, req.name, req.members)
    svc.add_group(group)
    await svc.broadcast({"type": "group_update", "data": group.to_dict()})
    return group

@router.post("/send")
async def send_message(req: SendMessageRequest, background_tasks: BackgroundTasks):
    """发送消息"""
    svc = get_sandbox_service()
    
    # 验证发送者
    if req.sender_qq not in svc.users:
        raise HTTPException(404, "发送者不存在")
        
    # 创建消息
    msg = Message(
        message_id=svc.next_message_id(),
        sender_qq=req.sender_qq,
        content=req.content,
        image=req.image,
        at_users=req.at_users,
        reply_to=req.reply_to,
        chat_type=req.chat_type,
        group_id=req.group_id,
        target_qq=req.target_qq
    )
    
    svc.add_message(msg)
    
    # 广播新消息
    await svc.broadcast({
        "type": "new_message", 
        "data": svc._enrich_message(msg)
    })
    
    # 触发模拟 Bot 回复（如果不是 Bot 发的）
    if not svc.users[req.sender_qq].is_bot:
        background_tasks.add_task(svc.simulate_bot_reply, msg)
        
    return {"status": "sent", "message_id": msg.message_id}

@router.post("/reset")
async def reset_sandbox():
    """重置沙盒"""
    global _sandbox_service
    # 强制重新初始化
    import src.admin.services.sandbox_service as mod
    mod._sandbox_service = mod.SandboxService()
    return {"status": "reset"}


@router.get("/mode")
async def get_agent_mode():
    """获取当前 Agent 模式"""
    svc = get_sandbox_service()
    return {
        "use_real_agent": svc.use_real_agent,
        "real_agent_available": svc.is_real_agent_available(),
    }


@router.post("/mode")
async def set_agent_mode(req: RealAgentModeRequest):
    """设置 Agent 模式"""
    svc = get_sandbox_service()
    success = svc.set_real_agent_mode(req.enabled)

    if not success and req.enabled:
        raise HTTPException(400, "无法启用真实 Agent 模式: Agent 未运行")

    return {
        "success": success,
        "use_real_agent": svc.use_real_agent,
    }


# ==================== WebSocket ====================

@router.websocket("/ws")
async def sandbox_ws(websocket: WebSocket):
    svc = get_sandbox_service()
    await websocket.accept()
    
    # 定义回调函数
    async def broadcast_callback(data: dict):
        try:
            await websocket.send_json(data)
        except Exception:
            pass # 连接可能已断开
            
    # 设置广播回调 (注意：这里简单的覆盖了原来的 callback，
    # 实际上应该支持多个 client。LogService 处理得更好，
    # 这里为了简单先这样，或者我们改进 SandboxService 支持多 client)
    # 改进 SandboxService 支持多 listeners
    
    # 临时 hack: 我们不仅要接收广播，还要保持连接
    # 更好的做法是在 Service 里维护 clients 列表，像 LogService 那样
    
    # 让我们现场改进 Service
    if not hasattr(svc, "_listeners"):
        svc._listeners = set()
        
        # 替换 broadcast 方法以支持多 listeners
        original_broadcast = svc.broadcast
        
        async def multi_broadcast(data: dict):
            # 调用原来的 callback (如果有)
            if svc._ws_broadcast:
                try:
                    await svc._ws_broadcast(data)
                except:
                    pass
            
            # 发送给所有连接的 websocket
            dead = set()
            for ws in svc._listeners:
                try:
                    await ws.send_json(data)
                except:
                    dead.add(ws)
            for ws in dead:
                svc._listeners.discard(ws)
                
        svc.broadcast = multi_broadcast

    svc._listeners.add(websocket)
    
    try:
        while True:
            # 保持连接
            await websocket.receive_text()
    except WebSocketDisconnect:
        if hasattr(svc, "_listeners"):
            svc._listeners.discard(websocket)
