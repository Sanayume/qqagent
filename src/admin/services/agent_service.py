"""
Agent 控制服务

通过 AppContext 访问运行中的 Agent 组件，提供完整控制能力。
"""

from datetime import datetime
from typing import Any, Optional

from src.core.context import get_app_context, AppContext
from src.utils.logger import log


class AgentService:
    """Agent 控制服务"""

    def __init__(self):
        self._ctx: AppContext = get_app_context()

    def get_status(self) -> dict[str, Any]:
        """获取 Agent 完整状态"""
        ctx = self._ctx

        status = {
            "running": ctx.is_agent_running,
            "stats": ctx.stats.to_dict(),
            "model": None,
            "base_url": None,
            "tools_count": 0,
            "tools": [],
            "session_count": 0,
        }

        if ctx.agent:
            agent = ctx.agent
            status["model"] = agent.model
            status["base_url"] = agent.base_url
            status["tools_count"] = len(agent._tools) if agent._tools else 0
            status["tools"] = [t.name for t in agent._tools] if agent._tools else []

        if ctx.memory_store:
            status["session_count"] = ctx.memory_store.get_session_count()

        return status

    def get_llm_config(self) -> dict[str, Any]:
        """获取当前 LLM 配置"""
        ctx = self._ctx

        if not ctx.agent:
            return {"error": "Agent 未运行"}

        agent = ctx.agent
        return {
            "model": agent.model,
            "base_url": agent.base_url,
            "api_key_set": bool(agent.api_key),
        }

    def reload_llm_config(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """热重载 LLM 配置

        Args:
            model: 新的模型名称（可选）
            api_key: 新的 API Key（可选）
            base_url: 新的 Base URL（可选）

        Returns:
            操作结果
        """
        ctx = self._ctx

        if not ctx.agent:
            return {"success": False, "error": "Agent 未运行"}

        agent = ctx.agent

        # 更新配置
        changed = False
        if model and model != agent.model:
            agent.model = model
            changed = True
        if api_key and api_key != agent.api_key:
            agent.api_key = api_key
            changed = True
        if base_url is not None and base_url != agent.base_url:
            agent.base_url = base_url
            changed = True

        if changed:
            # 重新创建 graph 以应用新配置
            agent.graph = agent._create_graph()
            log.success(f"Agent LLM config reloaded: model={agent.model}")
            return {
                "success": True,
                "message": "LLM 配置已更新",
                "config": {
                    "model": agent.model,
                    "base_url": agent.base_url,
                },
            }

        return {"success": True, "message": "配置未变更"}

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有会话"""
        ctx = self._ctx

        if not ctx.memory_store:
            return []

        store = ctx.memory_store
        session_ids = store.get_all_session_ids()

        sessions = []
        for sid in session_ids:
            history = store.get_history(sid)
            sessions.append({
                "session_id": sid,
                "message_count": len(history),
            })

        return sessions

    def get_session(self, session_id: str) -> dict[str, Any]:
        """获取单个会话详情"""
        ctx = self._ctx

        if not ctx.memory_store:
            return {"error": "MemoryStore 未初始化"}

        history = ctx.memory_store.get_history(session_id)

        messages = []
        for msg in history:
            msg_type = msg.__class__.__name__
            content = msg.content
            if isinstance(content, list):
                # 多模态消息，提取文本部分
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif isinstance(item, str):
                        text_parts.append(item)
                content = " ".join(text_parts) or "[多模态内容]"

            messages.append({
                "type": msg_type,
                "content": content[:500] if isinstance(content, str) else str(content)[:500],
            })

        return {
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages,
        }

    def clear_session(self, session_id: str) -> dict[str, Any]:
        """清除会话历史"""
        ctx = self._ctx

        if not ctx.memory_store:
            return {"success": False, "error": "MemoryStore 未初始化"}

        ctx.memory_store.clear(session_id)
        log.info(f"Session cleared via Admin: {session_id}")

        return {"success": True, "message": f"会话 {session_id} 已清除"}

    def clear_all_sessions(self) -> dict[str, Any]:
        """清除所有会话历史"""
        ctx = self._ctx

        if not ctx.memory_store:
            return {"success": False, "error": "MemoryStore 未初始化"}

        session_ids = ctx.memory_store.get_all_session_ids()
        count = len(session_ids)

        for sid in session_ids:
            ctx.memory_store.clear(sid)

        log.info(f"All {count} sessions cleared via Admin")

        return {"success": True, "message": f"已清除 {count} 个会话"}

    async def send_test_message(
        self,
        message: str,
        session_id: str = "admin-test",
        user_name: str = "Admin",
    ) -> dict[str, Any]:
        """发送测试消息（沙盒模式）

        使用真实 Agent 处理消息，但不发送到 QQ。
        """
        ctx = self._ctx

        if not ctx.agent:
            return {"success": False, "error": "Agent 未运行"}

        try:
            response = await ctx.agent.chat(
                message=message,
                session_id=session_id,
                user_id=0,
                user_name=user_name,
            )

            return {
                "success": True,
                "response": {
                    "text": response.text,
                    "images": response.images,
                },
            }
        except Exception as e:
            log.error(f"Test message failed: {e}")
            return {"success": False, "error": str(e)}


# 全局单例
_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    """获取 AgentService 单例"""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
