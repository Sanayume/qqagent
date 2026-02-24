"""LangGraph Agent 图定义

使用 LangGraph 构建 ReAct 风格的 Agent。
"""

import time
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.agent.state import AgentState, ChatResponse
from src.agent.llm import create_llm, extract_response_content, FallbackLLM
from src.agent.compat import sanitize_messages_for_api  # noqa: F401 — 导入即触发猴子补丁
from src.core.llm_message import extract_tool_images, extract_send_commands
from src.utils.logger import log


def create_agent_graph(
    llm: ChatOpenAI | FallbackLLM | None = None,
    tools: list | None = None,
    model: str = "gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    knowledge_store=None,
):
    """创建 Agent 图"""
    if llm is None:
        llm = create_llm(model=model, api_key=api_key, base_url=base_url)

    if tools is None:
        tools = []

    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    async def call_model(state: AgentState) -> dict:
        """调用 LLM 生成回复"""
        loop_num = state.get("loop_count", 0) + 1
        messages = list(state["messages"])

        system_prompt = state.get("system_prompt", "")

        # 知识库记忆注入（仅第一轮）
        if knowledge_store and loop_num == 1:
            # 取最后一条用户消息作为查询
            user_query = ""
            for m in reversed(messages):
                if isinstance(m, HumanMessage):
                    user_query = m.content if isinstance(m.content, str) else ""
                    break
            if user_query:
                try:
                    import asyncio
                    memories = await asyncio.get_event_loop().run_in_executor(
                        None, knowledge_store.search, user_query, state.get("session_id", ""), 3
                    )
                    if memories:
                        mem_text = "\n".join(f"- {m['content'][:200]}" for m in memories)
                        system_prompt += f"\n\n## 相关记忆\n{mem_text}"
                except Exception as e:
                    log.debug(f"Knowledge search failed: {e}")

        if system_prompt:
            if not messages or not isinstance(messages[0], SystemMessage):
                messages.insert(0, SystemMessage(content=system_prompt))

        messages = sanitize_messages_for_api(messages)
        log.info(f"Agent #{loop_num} | 调用LLM ({len(messages)} 条消息)")

        start_time = time.time()
        response = await llm_with_tools.ainvoke(messages)
        elapsed = time.time() - start_time

        content_preview = extract_response_content(response)
        has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls

        if has_tool_calls:
            tool_names = [tc.get('name', '?') for tc in response.tool_calls]
            log.info(f"Agent #{loop_num} | 调用工具: {', '.join(tool_names)} ({elapsed:.2f}s)")
        elif content_preview:
            preview = content_preview[:80].replace('\n', ' ')
            log.info(f"Agent #{loop_num} | 回复: {preview}{'...' if len(content_preview) > 80 else ''} ({elapsed:.2f}s)")
        else:
            log.info(f"Agent #{loop_num} | 回复: [空] ({elapsed:.2f}s)")

        return {"messages": [response], "loop_count": loop_num}

    async def execute_tools(state: AgentState) -> dict:
        """执行工具并记录日志"""
        messages = state["messages"]
        last_message = messages[-1]
        loop_num = state.get("loop_count", 0)

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tc in last_message.tool_calls:
                tool_name = tc.get('name', '?')
                args_preview = str(tc.get('args', {}))[:100]
                log.info(f"工具执行 | {tool_name}({args_preview}{'...' if len(str(tc.get('args', {}))) > 100 else ''})")

        start_time = time.time()
        result = await tool_node.ainvoke(state)
        elapsed = time.time() - start_time

        if "messages" in result:
            for msg in result["messages"]:
                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, 'name', '?')
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    preview = content[:80].replace('\n', ' ')
                    log.info(f"工具结果 | {tool_name}: {preview}{'...' if len(content) > 80 else ''} ({elapsed:.2f}s)")

        return result

    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        """决定是否继续调用工具"""
        messages = state["messages"]
        last_message = messages[-1]
        loop_num = state.get("loop_count", 0)

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        total_time = time.time() - state.get("loop_start_time", time.time())
        log.info(f"Agent 完成 | 共 {loop_num} 轮循环, 耗时 {total_time:.2f}s")
        return "end"

    # 构建图
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", execute_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")
    compiled = graph.compile()

    log.info(f"Agent graph created with {len(tools)} tools: {[t.name for t in tools]}")
    return compiled


class QQAgent:
    """QQ Agent 封装类"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str = "",
        tools: list | None = None,
        default_system_prompt: str = "你是一个有帮助的AI助手。",
        memory_store: "MemoryStore | None" = None,
        knowledge_store=None,
        fallback_llm: FallbackLLM | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.default_system_prompt = default_system_prompt
        self._tools = tools or []
        self._knowledge_store = knowledge_store
        self._fallback_llm = fallback_llm

        log.info(f"Initializing QQAgent with model: {model}")
        self.graph = self._create_graph()

        self._memory_store = memory_store
        self._internal_sessions: dict[str, list] | None = None if memory_store else {}

    def _create_graph(self):
        log.debug(f"Creating agent graph with model={self.model}, base_url={self.base_url[:30] if self.base_url else 'default'}...")
        llm = self._fallback_llm or None
        return create_agent_graph(
            llm=llm, model=self.model, api_key=self.api_key,
            base_url=self.base_url, tools=self._tools,
            knowledge_store=self._knowledge_store,
        )

    def _generate_tools_description(self) -> str:
        """生成工具描述，附加到 system prompt"""
        if not self._tools:
            return ""
        lines = ["\n\n## 可用工具\n你可以使用以下工具来帮助用户：\n"]
        for tool in self._tools:
            name = tool.name
            desc = tool.description.split('\n')[0][:100] if tool.description else "无描述"
            lines.append(f"- **{name}**: {desc}")
        lines.append("\n当用户的请求需要使用工具时，请主动调用相应的工具。")
        return "\n".join(lines)

    def _get_full_system_prompt(self, base_prompt: str) -> str:
        """获取完整的 system prompt (基础 + 工具列表)"""
        return base_prompt + self._generate_tools_description()

    def _get_history(self, session_id: str) -> list:
        if self._memory_store:
            return self._memory_store.get_history(session_id)
        return self._internal_sessions.get(session_id, [])

    def _set_history(self, session_id: str, messages: list):
        if self._memory_store:
            self._memory_store.set_history(session_id, messages)
        else:
            self._internal_sessions[session_id] = messages

    async def chat(
        self,
        message: str | HumanMessage,
        session_id: str = "default",
        user_id: int = 0,
        group_id: int | None = None,
        user_name: str = "用户",
        system_prompt: str | None = None,
    ) -> ChatResponse:
        """发送消息并获取回复"""
        log.info(f"{'─' * 50}")
        log.info(f"Agent 开始 | model={self.model} | session={session_id[:20]}")

        history = self._get_history(session_id)
        log.info(f"历史消息: {len(history)} 条")

        if isinstance(message, str):
            user_message = HumanMessage(content=message)
            msg_preview = message[:50]
        elif isinstance(message, HumanMessage):
            user_message = message
            msg_preview = message.content[:50] if isinstance(message.content, str) else "[多模态消息]"
        else:
            user_message = HumanMessage(content=str(message))
            msg_preview = str(message)[:50]

        log.info(f"用户输入: {msg_preview}{'...' if len(msg_preview) >= 50 else ''}")
        history.append(user_message)

        state: AgentState = {
            "messages": history,
            "session_id": session_id,
            "user_id": user_id,
            "group_id": group_id,
            "user_name": user_name,
            "preset_name": "default",
            "system_prompt": self._get_full_system_prompt(system_prompt or self.default_system_prompt),
            "should_respond": True,
            "loop_count": 0,
            "loop_start_time": time.time(),
        }

        result = await self.graph.ainvoke(state, {"recursion_limit": 15})

        # 检测 Agent 是否调用了 send_message
        has_send = any(
            isinstance(m, ToolMessage) and getattr(m, "name", None) == "send_message"
            for m in result["messages"]
        )
        if not has_send and extract_response_content(result["messages"][-1]):
            log.warning("Agent 未调用 send_message，追加提示重试")
            hint = HumanMessage(content="[系统提示] 你刚才的回复没有通过 send_message 发送，用户无法看到。请调用 send_message 工具发送你的回复。如果你是有意保持沉默则无需操作。")
            retry_state = dict(result)
            retry_state["messages"] = [hint]
            retry_state["loop_count"] = 0
            retry_state["loop_start_time"] = time.time()
            result = await self.graph.ainvoke(retry_state, {"recursion_limit": 15})

        ai_message = result["messages"][-1]
        response_text = extract_response_content(ai_message)
        tool_images = extract_tool_images(result["messages"])
        pending_sends = extract_send_commands(result["messages"])

        self._set_history(session_id, list(result["messages"]))

        # 存入长期记忆（在线程池中执行，避免阻塞事件循环）
        if self._knowledge_store:
            import asyncio
            ks = self._knowledge_store
            user_text = msg_preview if len(msg_preview) < 50 else (message if isinstance(message, str) else str(message.content)[:500])

            def _save():
                try:
                    ks.store(session_id, user_text, "user")
                    if response_text:
                        ks.store(session_id, response_text[:500], "assistant")
                except Exception as e:
                    log.debug(f"Knowledge store save failed: {e}")

            asyncio.get_event_loop().run_in_executor(None, _save)

        log.info(f"{'─' * 50}")

        return ChatResponse(text=response_text, images=tool_images, pending_sends=pending_sends)

    def clear_session(self, session_id: str):
        if self._memory_store:
            self._memory_store.clear(session_id)
        elif session_id in self._internal_sessions:
            del self._internal_sessions[session_id]
            log.info(f"Session {session_id} cleared")

    def get_session_ids(self) -> list[str]:
        if self._memory_store:
            return self._memory_store.get_all_session_ids()
        return list(self._internal_sessions.keys())
