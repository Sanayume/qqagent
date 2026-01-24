"""
Agent API 路由

提供 Agent 状态查看、配置热重载、会话管理等 API。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from src.admin.services.agent_service import get_agent_service

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class LLMConfigUpdate(BaseModel):
    """LLM 配置更新请求"""
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class TestMessageRequest(BaseModel):
    """测试消息请求"""
    message: str
    session_id: str = "admin-test"
    user_name: str = "Admin"


@router.get("/status")
async def get_agent_status():
    """获取 Agent 状态"""
    svc = get_agent_service()
    return svc.get_status()


@router.get("/llm")
async def get_llm_config():
    """获取 LLM 配置"""
    svc = get_agent_service()
    return svc.get_llm_config()


@router.post("/llm/reload")
async def reload_llm_config(config: LLMConfigUpdate):
    """热重载 LLM 配置"""
    svc = get_agent_service()
    result = svc.reload_llm_config(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    svc = get_agent_service()
    return {"sessions": svc.list_sessions()}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    svc = get_agent_service()
    result = svc.get_session(session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/sessions/{session_id}")
async def clear_session(session_id: str):
    """清除会话历史"""
    svc = get_agent_service()
    result = svc.clear_session(session_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.delete("/sessions")
async def clear_all_sessions():
    """清除所有会话历史"""
    svc = get_agent_service()
    result = svc.clear_all_sessions()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.post("/test")
async def send_test_message(request: TestMessageRequest):
    """发送测试消息（使用真实 Agent）"""
    svc = get_agent_service()
    result = await svc.send_test_message(
        message=request.message,
        session_id=request.session_id,
        user_name=request.user_name,
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result
