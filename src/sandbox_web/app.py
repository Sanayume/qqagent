"""
Web 沙盒 - FastAPI 应用

提供 HTTP API 和 WebSocket 实时通信。
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.sandbox_web.models import Simulator, User, Group, Message
from src.agent.graph import QQAgent
from src.agent.tools import DEFAULT_TOOLS, set_send_message_callback
from src.adapters.mcp import MCPManager
from src.memory import MemoryStore
from src.presets import PresetManager
from src.utils.config import load_settings
from src.utils.config_loader import get_config_loader
from src.utils.env_loader import get_env_loader
from src.utils.logger import setup_logger, log
from src.core.llm_message import build_rich_context_message, build_multimodal_message


# 加载 .env 文件
env_loader = get_env_loader()


# 全局状态
simulator: Simulator | None = None
agent: QQAgent | None = None
mcp_manager: MCPManager | None = None
memory_store: MemoryStore | None = None
preset_manager: PresetManager | None = None
current_preset_name: str = "default"
connected_clients: list[WebSocket] = []

# 实时消息队列 - 用于 send_message 工具的实时广播
_realtime_message_queue: asyncio.Queue | None = None
_current_original_msg: Message | None = None  # 当前正在处理的原始消息


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global simulator, agent, mcp_manager, memory_store, preset_manager, current_preset_name

    # 设置日志
    setup_logger(level="DEBUG")
    log.info("=" * 60)
    log.info("Web 沙盒启动中...")
    log.info("=" * 60)

    # 加载配置
    settings = load_settings()
    config_loader = get_config_loader()

    log.info(f"LLM Model: {settings.llm.default_model}")
    log.info(f"API Base: {settings.llm.openai_api_base or 'default'}")

    # 设置 LangSmith 环境变量
    if settings.langchain_api_key:
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
        log.info(f"LangSmith: Enabled ({settings.langchain_project})")
    else:
        log.info("LangSmith: Disabled")

    # 初始化模拟器
    simulator = Simulator(bot_qq=settings.agent.bot_qq if hasattr(settings.agent, 'bot_qq') else 10000)
    simulator.create_default_data()
    log.info(f"模拟器初始化: {len(simulator.users)} 用户, {len(simulator.groups)} 群")

    # 初始化 MCP
    mcp_manager = MCPManager("config/mcp_servers.json", timeout=120.0, retry_count=2)
    log.info("启动 MCP 服务器...")
    await mcp_manager.start()
    mcp_tools = mcp_manager.get_tools()
    log.info(f"MCP 工具: {len(mcp_tools)} 个")

    # 初始化 MemoryStore 和 PresetManager
    memory_store = MemoryStore(db_path="data/sandbox_web_sessions.db", max_messages=20)
    preset_manager = PresetManager(config_loader=config_loader, preset_dir="config/presets")
    default_preset = preset_manager.get_default()
    current_preset_name = default_preset.name

    all_tools = DEFAULT_TOOLS + mcp_tools

    agent = QQAgent(
        model=settings.llm.default_model,
        api_key=settings.llm.openai_api_key,
        base_url=settings.llm.openai_api_base,
        default_system_prompt=default_preset.system_prompt,
        memory_store=memory_store,
        tools=all_tools,
    )
    log.info(f"Agent 初始化完成: {len(all_tools)} 工具")
    log.info(f"当前预设: {current_preset_name}")

    log.success("Web 沙盒就绪!")

    yield

    # 清理
    if mcp_manager:
        await mcp_manager.stop()
    log.info("Web 沙盒已关闭")


app = FastAPI(title="QQ Agent 沙盒", lifespan=lifespan)

# 静态文件
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ==================== Pydantic 模型 ====================


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
    chat_type: str = "group"
    group_id: int | None = None
    target_qq: int | None = None


# ==================== HTTP 路由 ====================


@app.get("/")
async def index():
    """主页"""
    return FileResponse(static_dir / "index.html")


@app.get("/api/state")
async def get_state():
    """获取完整状态"""
    return {
        **simulator.to_dict(),
        "current_preset": current_preset_name,
    }


@app.get("/api/users")
async def list_users():
    """列出所有用户"""
    return [u.to_dict() for u in simulator.list_users()]


@app.post("/api/users")
async def create_user(req: CreateUserRequest):
    """创建用户"""
    user = User(qq=req.qq, nickname=req.nickname, avatar=req.avatar)
    simulator.add_user(user)
    await broadcast({"type": "user_added", "user": user.to_dict()})
    return user.to_dict()


@app.delete("/api/users/{qq}")
async def delete_user(qq: int):
    """删除用户"""
    if simulator.remove_user(qq):
        await broadcast({"type": "user_removed", "qq": qq})
        return {"success": True}
    return {"success": False, "error": "Cannot delete user"}


@app.get("/api/groups")
async def list_groups():
    """列出所有群"""
    return [g.to_dict() for g in simulator.list_groups()]


@app.post("/api/groups")
async def create_group(req: CreateGroupRequest):
    """创建群"""
    group = Group(group_id=req.group_id, name=req.name, members=req.members)
    simulator.add_group(group)
    await broadcast({"type": "group_added", "group": group.to_dict()})
    return group.to_dict()


@app.delete("/api/groups/{group_id}")
async def delete_group(group_id: int):
    """删除群"""
    if simulator.remove_group(group_id):
        await broadcast({"type": "group_removed", "group_id": group_id})
        return {"success": True}
    return {"success": False, "error": "Group not found"}


@app.post("/api/groups/{group_id}/members/{qq}")
async def add_group_member(group_id: int, qq: int):
    """添加群成员"""
    if simulator.add_member_to_group(group_id, qq):
        await broadcast({"type": "member_added", "group_id": group_id, "qq": qq})
        return {"success": True}
    return {"success": False}


@app.delete("/api/groups/{group_id}/members/{qq}")
async def remove_group_member(group_id: int, qq: int):
    """移除群成员"""
    if simulator.remove_member_from_group(group_id, qq):
        await broadcast({"type": "member_removed", "group_id": group_id, "qq": qq})
        return {"success": True}
    return {"success": False}


@app.get("/api/messages")
async def get_messages(chat_type: str = "group", group_id: int = None, user_qq: int = None):
    """获取消息历史"""
    messages = simulator.get_chat_messages(chat_type, group_id, user_qq)
    return [m.to_dict() for m in messages]


# ==================== 预设管理 ====================


@app.get("/api/presets")
async def list_presets():
    """列出所有预设"""
    presets = preset_manager.list_presets()
    return {
        "current": current_preset_name,
        "presets": [
            {
                "name": p.name,
                "keywords": p.keywords,
                "is_current": p.name == current_preset_name,
            }
            for p in presets
        ]
    }


@app.post("/api/presets/{name}")
async def switch_preset(name: str):
    """切换预设"""
    global current_preset_name, agent

    preset = preset_manager.get(name)
    if not preset:
        return {"success": False, "error": f"预设不存在: {name}"}

    current_preset_name = preset.name
    agent.default_system_prompt = preset.system_prompt

    log.info(f"切换预设: {current_preset_name}")
    await broadcast({"type": "preset_changed", "preset": current_preset_name})

    return {"success": True, "preset": current_preset_name}


# ==================== 会话管理 ====================


@app.get("/api/sessions")
async def list_sessions():
    """列出所有会话"""
    session_ids = memory_store.get_all_session_ids()
    return {
        "sessions": [
            {
                "session_id": sid,
                "message_count": len(memory_store.get_history(sid)),
            }
            for sid in session_ids
        ]
    }


@app.delete("/api/sessions/{session_id}")
async def clear_session(session_id: str):
    """清空指定会话"""
    memory_store.clear(session_id)
    agent.clear_session(session_id)
    log.info(f"清空会话: {session_id}")
    await broadcast({"type": "session_cleared", "session_id": session_id})
    return {"success": True}


@app.delete("/api/sessions")
async def clear_all_sessions():
    """清空所有会话"""
    session_ids = memory_store.get_all_session_ids()
    for sid in session_ids:
        memory_store.clear(sid)
        agent.clear_session(sid)
    log.info(f"清空所有会话: {len(session_ids)} 个")
    await broadcast({"type": "all_sessions_cleared"})
    return {"success": True, "cleared": len(session_ids)}


@app.delete("/api/simulator/messages")
async def clear_simulator_messages():
    """清空模拟器消息（不清空 Agent 会话）"""
    count = len(simulator.messages)
    simulator.messages.clear()
    simulator._message_id_counter = 1000
    log.info(f"清空模拟器消息: {count} 条")
    await broadcast({"type": "messages_cleared"})
    return {"success": True, "cleared": count}


@app.post("/api/reset")
async def reset_all():
    """完全重置（清空会话 + 清空消息）"""
    # 清空会话
    session_ids = memory_store.get_all_session_ids()
    for sid in session_ids:
        memory_store.clear(sid)
        agent.clear_session(sid)

    # 清空模拟器消息
    simulator.messages.clear()
    simulator._message_id_counter = 1000

    log.info("完全重置")
    await broadcast({"type": "reset"})
    return {"success": True}


# ==================== WebSocket ====================


async def broadcast(data: dict):
    """广播消息给所有连接的客户端"""
    message = json.dumps(data, ensure_ascii=False)
    for client in connected_clients[:]:
        try:
            await client.send_text(message)
        except:
            connected_clients.remove(client)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 连接"""
    await ws.accept()
    connected_clients.append(ws)
    log.info(f"WebSocket 连接: {len(connected_clients)} 个客户端")

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "send_message":
                await handle_user_message(msg)

    except WebSocketDisconnect:
        connected_clients.remove(ws)
        log.info(f"WebSocket 断开: {len(connected_clients)} 个客户端")


async def handle_user_message(data: dict):
    """处理用户发送的消息"""
    global simulator, agent

    sender_qq = data.get("sender_qq")
    content = data.get("content", "")
    image = data.get("image", "")
    at_users = data.get("at_users", [])
    reply_to = data.get("reply_to", 0)
    chat_type = data.get("chat_type", "group")
    group_id = data.get("group_id")
    target_qq = data.get("target_qq")

    sender = simulator.get_user(sender_qq)
    if not sender:
        return

    # 创建消息
    msg = Message(
        message_id=simulator.next_message_id(),
        sender_qq=sender_qq,
        content=content,
        image=image,
        at_users=at_users,
        reply_to=reply_to,
        chat_type=chat_type,
        group_id=group_id,
        target_qq=target_qq,
    )
    simulator.add_message(msg)

    # 广播消息
    await broadcast({
        "type": "new_message",
        "message": msg.to_dict(),
        "sender": sender.to_dict(),
    })

    # 检查是否需要触发 Agent
    should_trigger = False

    # 私聊触发
    if chat_type == "private" and target_qq == simulator.bot_qq:
        should_trigger = True

    # 群聊触发（沙盒环境：所有群消息都触发）
    if chat_type == "group":
        should_trigger = True

    if should_trigger:
        await trigger_agent(msg, sender)


async def trigger_agent(msg: Message, sender: User):
    """触发 Agent 处理消息"""
    global simulator, agent, _realtime_message_queue, _current_original_msg

    log.info(f"触发 Agent: {sender.nickname} 说 '{msg.content}'")

    # 构建会话 ID
    if msg.chat_type == "group":
        session_id = f"sandbox_group_{msg.group_id}"
    else:
        session_id = f"sandbox_private_{msg.sender_qq}"

    # 获取引用消息上下文
    reply_context = None
    if msg.reply_to:
        reply_msg = simulator.get_message(msg.reply_to)
        if reply_msg:
            reply_sender = simulator.get_user(reply_msg.sender_qq)
            reply_name = reply_sender.nickname if reply_sender else "某人"
            reply_context = f"{reply_name}: {reply_msg.content}"

    # 构建 LLM 消息
    context_text = build_rich_context_message(
        main_text=msg.content,
        sender_name=sender.nickname,
        sender_qq=sender.qq,
        message_id=msg.message_id,
        group_id=msg.group_id,
        reply_to_id=msg.reply_to if msg.reply_to else None,
        reply_context=reply_context,
        at_targets=[str(qq) for qq in msg.at_users] if msg.at_users else None,
    )

    # 设置实时消息回调
    _current_original_msg = msg
    _realtime_message_queue = asyncio.Queue()

    # 获取当前事件循环
    loop = asyncio.get_running_loop()

    def realtime_callback(cmd: dict):
        """实时消息回调 - 在工具调用时立即触发"""
        # 从同步回调中安全地向异步队列添加消息
        loop.call_soon_threadsafe(_realtime_message_queue.put_nowait, cmd)

    set_send_message_callback(realtime_callback)

    # 启动后台任务处理实时消息
    message_count = 0
    async def process_realtime_messages():
        nonlocal message_count
        while True:
            try:
                # 非阻塞检查队列
                cmd = _realtime_message_queue.get_nowait()
                await send_bot_message(cmd, msg)
                message_count += 1
            except asyncio.QueueEmpty:
                # 队列为空，等待一小段时间
                await asyncio.sleep(0.05)

    # 创建后台任务
    processor_task = asyncio.create_task(process_realtime_messages())

    # 调用 Agent
    try:
        response = await agent.chat(
            message=context_text,
            session_id=session_id,
            user_id=msg.sender_qq,
            group_id=msg.group_id,
            user_name=sender.nickname,
        )

        # 等待一小段时间确保队列中的消息都被处理
        await asyncio.sleep(0.1)

        # 处理队列中剩余的消息
        while not _realtime_message_queue.empty():
            try:
                cmd = _realtime_message_queue.get_nowait()
                await send_bot_message(cmd, msg)
                message_count += 1
            except asyncio.QueueEmpty:
                break

        if message_count == 0:
            log.info("Agent 选择沉默")
        else:
            log.info(f"Agent 共发送 {message_count} 条消息")

    except Exception as e:
        log.exception(f"Agent 处理失败: {e}")
        # 发送错误消息
        error_msg = Message(
            message_id=simulator.next_message_id(),
            sender_qq=simulator.bot_qq,
            content=f"[错误] {str(e)[:100]}",
            chat_type=msg.chat_type,
            group_id=msg.group_id,
            target_qq=msg.sender_qq if msg.chat_type == "private" else None,
        )
        simulator.add_message(error_msg)
        await broadcast({
            "type": "new_message",
            "message": error_msg.to_dict(),
            "sender": simulator.get_user(simulator.bot_qq).to_dict(),
        })
    finally:
        # 清理
        processor_task.cancel()
        try:
            await processor_task
        except asyncio.CancelledError:
            pass
        set_send_message_callback(None)
        _current_original_msg = None
        _realtime_message_queue = None


async def send_bot_message(cmd: dict, original_msg: Message):
    """发送机器人消息"""
    global simulator

    text = cmd.get("text", "")
    image = cmd.get("image", "")
    at_users = cmd.get("at_users", [])
    reply_to = cmd.get("reply_to", 0)

    bot_msg = Message(
        message_id=simulator.next_message_id(),
        sender_qq=simulator.bot_qq,
        content=text,
        image=image,
        at_users=at_users,
        reply_to=reply_to,
        chat_type=original_msg.chat_type,
        group_id=original_msg.group_id,
        target_qq=original_msg.sender_qq if original_msg.chat_type == "private" else None,
    )
    simulator.add_message(bot_msg)

    bot_user = simulator.get_user(simulator.bot_qq)
    await broadcast({
        "type": "new_message",
        "message": bot_msg.to_dict(),
        "sender": bot_user.to_dict(),
    })

    log.info(f"Bot 发送: {text[:50]}{'...' if len(text) > 50 else ''}")


# ==================== 启动 ====================


def run():
    """启动服务器"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    run()
