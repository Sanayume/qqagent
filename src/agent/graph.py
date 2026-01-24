"""
LangGraph Agent 图定义

使用 LangGraph 构建 ReAct 风格的 Agent。
支持思考模型 (Thinking Models) 如 Gemini 2.5 Pro, Claude 3.5 with thinking 等。
"""

import time
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.agent.state import AgentState, ChatResponse
from src.core.llm_message import extract_tool_images, extract_send_commands
from src.utils.logger import log


def sanitize_messages_for_api(messages: list[BaseMessage]) -> list[BaseMessage]:
    """清理消息列表，使其兼容 Gemini API 的 tool calling 格式要求

    只清理历史消息中的 tool_calls/ToolMessage，当前轮次保持原样以维持 agent 循环。
    """
    if not messages:
        return messages

    # 找到最后一个 HumanMessage 的位置（当前轮次开始）
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    if last_human_idx == -1:
        return messages

    # 分离历史和当前轮次
    history = messages[:last_human_idx]
    current_round = messages[last_human_idx:]

    # ==================== 只清理历史消息 ====================
    sanitized_history = []
    
    for msg in history:
        if isinstance(msg, ToolMessage):
            # ToolMessage 转为 AIMessage 纯文本
            tool_name = getattr(msg, 'name', None) or 'tool'
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if len(content) > 200:
                content = content[:200] + "..."
            sanitized_history.append(AIMessage(content=f"[{tool_name}结果: {content}]"))

        elif isinstance(msg, AIMessage):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # AIMessage with tool_calls 转为纯文本
                tool_names = [tc.get('name', 'unknown') for tc in msg.tool_calls]
                text_content = msg.content or f"[调用了工具: {', '.join(tool_names)}]"
                sanitized_history.append(AIMessage(content=text_content))
            else:
                sanitized_history.append(msg)
        else:
            sanitized_history.append(msg)

    # 当前轮次保持原样（包括 tool_calls 和 ToolMessage）
    return sanitized_history + list(current_round)


def create_llm(
    model: str = "gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.7,
) -> ChatOpenAI:
    """创建 LLM 实例

    Args:
        model: 模型名称
        api_key: API Key
        base_url: API Base URL (用于本地模型/代理)
        temperature: 温度参数
    """
    import httpx

    kwargs = {
        "model": model,
        "temperature": temperature,
        # 禁用系统代理，避免本地 API 请求被代理拦截
        "http_client": httpx.Client(trust_env=False),
        "http_async_client": httpx.AsyncClient(trust_env=False),
    }

    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    log.info(f"Creating LLM: model={model}, base_url={base_url or 'default'}")

    return ChatOpenAI(**kwargs)


def extract_response_content(ai_message) -> str:
    """从 AI 消息中提取回复内容
    
    支持思考模型的多种响应格式:
    1. 普通文本 content
    2. 带 thinking chain 的响应 (content 是列表)
    3. additional_kwargs 中的 thinking 字段
    """
    # 如果没有 content 属性
    if not hasattr(ai_message, "content"):
        return str(ai_message)
    
    content = ai_message.content
    
    # 情况 1: content 是字符串
    if isinstance(content, str):
        return content
    
    # 情况 2: content 是列表 (思考模型格式)
    # 格式可能是: [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": "..."}]
    if isinstance(content, list):
        text_parts = []
        thinking_parts = []
        
        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                
                # 提取文本内容
                if item_type == "text":
                    text_parts.append(item.get("text", ""))
                elif item_type == "thinking":
                    thinking_parts.append(item.get("thinking", ""))
                # OpenAI 格式
                elif "text" in item:
                    text_parts.append(item["text"])
            elif isinstance(item, str):
                text_parts.append(item)
        
        # 如果有思考过程，记录日志
        if thinking_parts:
            thinking_summary = thinking_parts[0][:200] + "..." if len(thinking_parts[0]) > 200 else thinking_parts[0]
            log.debug(f"Thinking chain: {thinking_summary}")
        
        # 返回文本部分
        if text_parts:
            return "".join(text_parts)
        
        # 如果只有思考没有文本，返回思考内容的摘要
        if thinking_parts:
            return thinking_parts[-1][:500] if thinking_parts[-1] else ""
    
    # 情况 3: 检查 additional_kwargs
    if hasattr(ai_message, "additional_kwargs"):
        kwargs = ai_message.additional_kwargs
        
        # Gemini 风格
        if "thinking" in kwargs:
            log.debug(f"Thinking from kwargs: {kwargs['thinking'][:100]}...")
        
        # 某些模型将内容放在这里
        if "content" in kwargs and isinstance(kwargs["content"], str):
            return kwargs["content"]
    
    # 兜底: 转为字符串
    return str(content) if content else ""


def create_agent_graph(
    llm: ChatOpenAI | None = None,
    tools: list | None = None,
    model: str = "gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
):
    """创建 Agent 图

    Args:
        llm: 预配置的 LLM 实例 (可选)
        tools: 工具列表 (默认使用内置工具)
        model: 模型名称 (当 llm 为 None 时使用)
        api_key: API Key (当 llm 为 None 时使用)
        base_url: API Base URL (当 llm 为 None 时使用)

    Returns:
        编译后的 LangGraph Agent
    """
    # 创建 LLM
    if llm is None:
        llm = create_llm(model=model, api_key=api_key, base_url=base_url)

    # 使用传入的工具或空列表（调用方应提供工具）
    if tools is None:
        tools = []

    # 绑定工具到 LLM
    llm_with_tools = llm.bind_tools(tools)

    # 创建工具节点
    tool_node = ToolNode(tools)

    # 循环计数器（用于日志）
    loop_counter = {"count": 0, "start_time": 0}

    # ==================== 节点函数 ====================

    def call_model(state: AgentState) -> dict:
        """调用 LLM 生成回复"""
        loop_counter["count"] += 1
        loop_num = loop_counter["count"]

        messages = list(state["messages"])

        # 如果有系统提示词，确保它在最前面
        system_prompt = state.get("system_prompt", "")
        if system_prompt:
            # 检查是否已有系统消息
            if not messages or not isinstance(messages[0], SystemMessage):
                messages.insert(0, SystemMessage(content=system_prompt))

        # 清理消息格式，修复 Gemini API 的 tool_calls/ToolMessage 匹配要求
        messages = sanitize_messages_for_api(messages)

        # 日志：显示循环状态
        log.info(f"🤖 Agent 循环 #{loop_num} | 📨 调用 LLM ({len(messages)} 条消息)")

        # 调用 LLM
        start_time = time.time()
        response = llm_with_tools.invoke(messages)
        elapsed = time.time() - start_time

        # 提取内容用于日志
        content_preview = extract_response_content(response)

        # 检查是否有工具调用
        has_tool_calls = hasattr(response, "tool_calls") and response.tool_calls

        if has_tool_calls:
            tool_names = [tc.get('name', '?') for tc in response.tool_calls]
            log.info(f"🤖 Agent 循环 #{loop_num} | ⚡ LLM 决定调用工具: {', '.join(tool_names)} ({elapsed:.2f}s)")
        elif content_preview:
            preview = content_preview[:80].replace('\n', ' ')
            log.info(f"🤖 Agent 循环 #{loop_num} | 💬 LLM 回复: {preview}{'...' if len(content_preview) > 80 else ''} ({elapsed:.2f}s)")
        else:
            log.info(f"🤖 Agent 循环 #{loop_num} | 💬 LLM 回复: [空] ({elapsed:.2f}s)")

        return {"messages": [response]}

    def execute_tools(state: AgentState) -> dict:
        """执行工具并记录日志"""
        messages = state["messages"]
        last_message = messages[-1]
        loop_num = loop_counter["count"]

        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tc in last_message.tool_calls:
                tool_name = tc.get('name', '?')
                tool_args = tc.get('args', {})
                # 简化参数显示
                args_preview = str(tool_args)[:100]
                log.info(f"🔧 工具执行 | {tool_name}({args_preview}{'...' if len(str(tool_args)) > 100 else ''})")

        # 调用原始工具节点
        start_time = time.time()
        result = tool_node.invoke(state)
        elapsed = time.time() - start_time

        # 记录工具结果
        if "messages" in result:
            for msg in result["messages"]:
                if isinstance(msg, ToolMessage):
                    tool_name = getattr(msg, 'name', '?')
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    preview = content[:80].replace('\n', ' ')
                    log.info(f"🔧 工具结果 | {tool_name}: {preview}{'...' if len(content) > 80 else ''} ({elapsed:.2f}s)")

        return result

    def should_continue(state: AgentState) -> Literal["tools", "end"]:
        """决定是否继续调用工具"""
        messages = state["messages"]
        last_message = messages[-1]
        loop_num = loop_counter["count"]

        # 如果最后一条消息有工具调用，继续执行工具
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"

        # 结束循环
        total_time = time.time() - loop_counter["start_time"]
        log.info(f"🤖 Agent 完成 | 共 {loop_num} 轮循环, 耗时 {total_time:.2f}s")
        return "end"

    # ==================== 构建图 ====================

    # 创建状态图
    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("agent", call_model)
    graph.add_node("tools", execute_tools)  # 使用自定义的工具执行函数

    # 设置入口点
    graph.set_entry_point("agent")

    # 添加条件边
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        }
    )

    # 工具执行后返回 agent
    graph.add_edge("tools", "agent")

    # 编译图，设置递归限制防止无限循环
    # recursion_limit 限制图的最大步数（每个节点执行算一步）
    # 设为 20 意味着大约 10 轮 agent-tools 循环
    compiled = graph.compile()

    # 保存循环计数器到编译后的图
    compiled._loop_counter = loop_counter

    log.info(f"Agent graph created with {len(tools)} tools: {[t.name for t in tools]}")

    return compiled


class QQAgent:
    """QQ Agent 封装类

    提供更简便的接口来使用 Agent。
    支持思考模型 (Thinking Models)。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str = "",
        base_url: str = "",
        tools: list | None = None,
        default_system_prompt: str = "你是一个有帮助的AI助手。",
        memory_store: "MemoryStore | None" = None,
    ):
        """初始化 Agent

        Args:
            model: 模型名称
            api_key: API Key
            base_url: API Base URL
            tools: 工具列表
            default_system_prompt: 默认系统提示词
            memory_store: 会话历史存储 (可选，不传则使用内存存储)
        """
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.default_system_prompt = default_system_prompt
        self._tools = tools or []

        log.info(f"Initializing QQAgent with model: {model}")

        # 创建 Agent 图
        self.graph = self._create_graph()

        # 使用外部存储或内部字典
        self._memory_store = memory_store
        self._internal_sessions: dict[str, list] | None = None if memory_store else {}

    def _create_graph(self):
        """创建 LangGraph Agent 图
        
        用于初始化或热重载时重新创建 graph。
        """
        log.debug(f"Creating agent graph with model={self.model}, base_url={self.base_url[:30] if self.base_url else 'default'}...")
        return create_agent_graph(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            tools=self._tools,
        )

    def _generate_tools_description(self) -> str:
        """生成工具描述，附加到 system prompt"""
        if not self._tools:
            return ""

        lines = ["\n\n## 可用工具\n你可以使用以下工具来帮助用户：\n"]
        for tool in self._tools:
            # 获取工具名和描述
            name = tool.name
            desc = tool.description.split('\n')[0][:100] if tool.description else "无描述"
            lines.append(f"- **{name}**: {desc}")

        lines.append("\n当用户的请求需要使用工具时，请主动调用相应的工具。")
        return "\n".join(lines)

    def _get_full_system_prompt(self, base_prompt: str) -> str:
        """获取完整的 system prompt (基础 + 工具列表)"""
        tools_desc = self._generate_tools_description()
        return base_prompt + tools_desc

    def _get_history(self, session_id: str) -> list:
        """获取会话历史"""
        if self._memory_store:
            return self._memory_store.get_history(session_id)
        return self._internal_sessions.get(session_id, [])

    def _set_history(self, session_id: str, messages: list):
        """设置会话历史"""
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
        """发送消息并获取回复

        Args:
            message: 用户消息 (字符串或 HumanMessage，支持多模态)
            session_id: 会话ID (用于隔离对话历史)
            user_id: 用户QQ号
            group_id: 群号 (私聊为 None)
            user_name: 用户昵称
            system_prompt: 系统提示词 (可选，覆盖默认值)

        Returns:
            ChatResponse 对象，包含文本回复和图片列表
        """
        # 重置循环计数器
        if hasattr(self.graph, '_loop_counter'):
            self.graph._loop_counter["count"] = 0
            self.graph._loop_counter["start_time"] = time.time()

        # 日志：开始处理
        log.info(f"{'─' * 50}")
        log.info(f"🚀 Agent 开始 | model={self.model} | session={session_id[:20]}")

        # 获取会话历史
        history = self._get_history(session_id)
        log.info(f"📚 历史消息: {len(history)} 条")

        # 处理消息：支持字符串或 HumanMessage
        if isinstance(message, str):
            user_message = HumanMessage(content=message)
            msg_preview = message[:50]
        elif isinstance(message, HumanMessage):
            user_message = message
            # 提取预览
            if isinstance(message.content, str):
                msg_preview = message.content[:50]
            else:
                msg_preview = "[多模态消息]"
        else:
            # 其他类型，尝试转换
            user_message = HumanMessage(content=str(message))
            msg_preview = str(message)[:50]

        log.info(f"📝 用户输入: {msg_preview}{'...' if len(msg_preview) >= 50 else ''}")

        # 添加用户消息
        history.append(user_message)

        # 构建状态
        state: AgentState = {
            "messages": history,
            "session_id": session_id,
            "user_id": user_id,
            "group_id": group_id,
            "user_name": user_name,
            "preset_name": "default",
            "system_prompt": self._get_full_system_prompt(system_prompt or self.default_system_prompt),
            "should_respond": True,
        }

        # 运行 Agent，设置递归限制防止无限循环
        # recursion_limit 限制图的最大步数，设为 15 约等于 7 轮工具调用
        result = await self.graph.ainvoke(state, {"recursion_limit": 15})

        # 获取最后的 AI 回复
        ai_message = result["messages"][-1]

        # 使用专门的函数提取内容 (支持思考模型)
        response_text = extract_response_content(ai_message)

        # 提取工具返回的图片
        tool_images = extract_tool_images(result["messages"])

        # 提取 send_message 工具的发送指令
        pending_sends = extract_send_commands(result["messages"])

        # 更新会话历史 (存储时将多模态消息转为纯文本描述)
        final_messages = list(result["messages"])
        self._set_history(session_id, final_messages)

        log.info(f"{'─' * 50}")

        return ChatResponse(text=response_text, images=tool_images, pending_sends=pending_sends)

    def clear_session(self, session_id: str):
        """清除会话历史"""
        if self._memory_store:
            self._memory_store.clear(session_id)
        elif session_id in self._internal_sessions:
            del self._internal_sessions[session_id]
            log.info(f"Session {session_id} cleared")

    def get_session_ids(self) -> list[str]:
        """获取所有活跃的会话ID"""
        if self._memory_store:
            return self._memory_store.get_all_session_ids()
        return list(self._internal_sessions.keys())

