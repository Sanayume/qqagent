"""LLM 工厂、Fallback 和响应解析"""

from langchain_openai import ChatOpenAI
from src.core.resilience import CircuitBreaker
from src.utils.logger import log


def create_llm(
    model: str = "gpt-4o-mini",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.7,
) -> ChatOpenAI:
    """创建 LLM 实例"""
    import httpx

    kwargs = {
        "model": model,
        "temperature": temperature,
        "http_client": httpx.Client(trust_env=False),
        "http_async_client": httpx.AsyncClient(trust_env=False),
    }

    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url

    log.info(f"Creating LLM: model={model}, base_url={base_url or 'default'}")
    return ChatOpenAI(**kwargs)


class FallbackLLM:
    """多模型 Fallback — 主模型失败时自动切换备用模型"""

    def __init__(self, model_configs: list[dict]):
        """
        Args:
            model_configs: [{"model": "gpt-4o", "api_key": "...", "base_url": "..."}, ...]
        """
        self._llms: list[tuple[ChatOpenAI, CircuitBreaker]] = []
        for i, cfg in enumerate(model_configs):
            llm = create_llm(
                model=cfg.get("model", "gpt-4o-mini"),
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
            )
            cb = CircuitBreaker(
                name=f"LLM_{cfg.get('model', i)}",
                failure_threshold=cfg.get("failure_threshold", 3),
                recovery_timeout=cfg.get("recovery_timeout", 60.0),
            )
            self._llms.append((llm, cb))
        if not self._llms:
            raise ValueError("At least one model config is required")

    def bind_tools(self, tools):
        """返回一个 FallbackBound，行为类似 llm.bind_tools() 的结果"""
        return _FallbackBound(self._llms, tools)


class _FallbackBound:
    """bind_tools 后的 Fallback 包装，提供 ainvoke"""

    def __init__(self, llms, tools):
        self._bounds = [(llm.bind_tools(tools), cb) for llm, cb in llms]

    async def ainvoke(self, messages):
        last_err = None
        for bound, cb in self._bounds:
            if not cb.allow_request():
                continue
            try:
                result = await bound.ainvoke(messages)
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure(e)
                last_err = e
                log.warning(f"[Fallback] {cb.name} failed: {e}, trying next...")
        raise last_err or RuntimeError("All models unavailable")


def extract_response_content(ai_message) -> str:
    """从 AI 消息中提取回复内容，支持思考模型的多种响应格式"""
    if not hasattr(ai_message, "content"):
        return str(ai_message)

    content = ai_message.content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        thinking_parts = []

        for item in content:
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "text":
                    text_parts.append(item.get("text", ""))
                elif item_type == "thinking":
                    thinking_parts.append(item.get("thinking", ""))
                elif "text" in item:
                    text_parts.append(item["text"])
            elif isinstance(item, str):
                text_parts.append(item)

        if thinking_parts:
            summary = thinking_parts[0][:200] + "..." if len(thinking_parts[0]) > 200 else thinking_parts[0]
            log.debug(f"Thinking chain: {summary}")

        if text_parts:
            return "".join(text_parts)
        if thinking_parts:
            return thinking_parts[-1][:500] if thinking_parts[-1] else ""

    if hasattr(ai_message, "additional_kwargs"):
        kwargs = ai_message.additional_kwargs
        if "thinking" in kwargs:
            log.debug(f"Thinking from kwargs: {kwargs['thinking'][:100]}...")
        if "content" in kwargs and isinstance(kwargs["content"], str):
            return kwargs["content"]

    return str(content) if content else ""
