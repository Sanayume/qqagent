"""Gemini 思考模型兼容补丁

Gemini 思考模型的 tool_calls 带 extra_content（含 thought_signature），
下次请求必须原样传回，否则报错。

问题链路：
  1. _convert_dict_to_message 解析响应时丢弃 extra_content
  2. _convert_message_to_dict 序列化时只保留 {id, type, function}

修复：两端都 patch
  - 解析端：把原始 tool_calls 存到 additional_kwargs["_raw_tool_calls"]
  - 序列化端：检测到 _raw_tool_calls 时，用它替换标准序列化结果
"""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage
import langchain_openai.chat_models.base as _lc_openai_mod

# --- Patch 1: 解析响应时保留原始 tool_calls ---
_original_convert_from = _lc_openai_mod._convert_dict_to_message


def _patched_convert_dict_to_message(_dict):
    msg = _original_convert_from(_dict)
    if isinstance(msg, AIMessage) and msg.tool_calls:
        raw_tcs = _dict.get("tool_calls", [])
        if any(tc.get("extra_content") for tc in raw_tcs):
            msg.additional_kwargs["_raw_tool_calls"] = raw_tcs
    return msg


_lc_openai_mod._convert_dict_to_message = _patched_convert_dict_to_message

# --- Patch 2: 序列化时恢复 extra_content ---
_original_convert_to = _lc_openai_mod._convert_message_to_dict


def _patched_convert_message_to_dict(message, api="chat/completions"):
    result = _original_convert_to(message, api=api)
    if (
        isinstance(message, AIMessage)
        and "_raw_tool_calls" in message.additional_kwargs
        and "tool_calls" in result
    ):
        raw = message.additional_kwargs["_raw_tool_calls"]
        extra_map = {
            tc["id"]: tc.get("extra_content")
            for tc in raw if tc.get("extra_content")
        }
        for tc in result["tool_calls"]:
            ec = extra_map.get(tc.get("id"))
            if ec:
                tc["extra_content"] = ec
    return result


_lc_openai_mod._convert_message_to_dict = _patched_convert_message_to_dict


def _format_send_message(args: dict) -> str:
    """将 send_message 工具调用格式化为聊天记录风格，与 PendingMessage.format() 对齐"""
    text = args.get('text', '')
    image = args.get('image', '')
    record = args.get('record', '')
    at_users = args.get('at_users', '')
    reply_to = args.get('reply_to', 0)
    delay = args.get('delay_minutes', 0)

    # header 行：模仿 PendingMessage.format() 的 "名字(QQ) 时间 #ID:" 风格
    header = "我(bot)"
    if reply_to:
        header += f" 回复#{reply_to}"
    if at_users:
        at_str = ", ".join(str(u) for u in at_users) if isinstance(at_users, list) else str(at_users)
        header += f" @{at_str}"
    header += ":"

    # 内容行
    body_parts = []
    if text:
        body_parts.append(text)
    if image:
        body_parts.append("[图片]")
    if record:
        body_parts.append("[语音]")
    if delay:
        body_parts.append(f"(定时{delay}分钟后发送)")
    if not body_parts:
        body_parts.append("(空消息)")

    return header + "\n" + "\n".join(body_parts)


def sanitize_messages_for_api(messages: list[BaseMessage]) -> list[BaseMessage]:
    """清理消息列表，使其兼容 Gemini API 的 tool calling 格式要求

    只清理历史消息中的 tool_calls/ToolMessage，当前轮次保持原样以维持 agent 循环。
    """
    if not messages:
        return messages

    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    if last_human_idx == -1:
        return messages

    history = messages[:last_human_idx]
    current_round = messages[last_human_idx:]

    sanitized_history = []
    for msg in history:
        if isinstance(msg, ToolMessage):
            continue
        elif isinstance(msg, AIMessage):
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                parts = []
                for tc in msg.tool_calls:
                    name = tc.get('name', '')
                    args = tc.get('args', {})
                    if name == 'send_message':
                        parts.append(_format_send_message(args))
                    elif name:
                        parts.append(f'[我使用了工具 {name}]')
                if parts:
                    sanitized_history.append(AIMessage(content="\n".join(parts)))
            else:
                sanitized_history.append(msg)
        else:
            sanitized_history.append(msg)

    return sanitized_history + list(current_round)
