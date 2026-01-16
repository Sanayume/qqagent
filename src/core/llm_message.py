"""
LLM 消息构建工具 - 构建 LangChain 消息对象

本模块提供纯函数，用于：
- 构建纯文本 HumanMessage
- 构建多模态 HumanMessage (含图片)
- 从消息中提取文本内容

注意：
- 本模块不知道 QQ、OneBot 协议
- 本模块不知道 Agent 业务逻辑
- 只依赖 langchain_core 基础类型
"""

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)


def build_text_message(text: str) -> HumanMessage:
    """构建纯文本 HumanMessage

    Args:
        text: 文本内容

    Returns:
        包含文本内容的 HumanMessage

    Example:
        >>> msg = build_text_message("Hello")
        >>> msg.content
        'Hello'
    """
    return HumanMessage(content=text)


def build_multimodal_message(
    text: str,
    images: list[tuple[str, str]],
) -> HumanMessage:
    """构建多模态 HumanMessage (含图片)

    Args:
        text: 文本内容
        images: 图片列表，每个元素为 (base64_data, mime_type) 元组

    Returns:
        包含文本和图片的 HumanMessage

    Example:
        >>> msg = build_multimodal_message(
        ...     text="这是什么？",
        ...     images=[("iVBORw0...", "image/png")]
        ... )
        >>> len(msg.content)
        2
        >>> msg.content[0]["type"]
        'text'
        >>> msg.content[1]["type"]
        'image_url'

    Note:
        如果 images 为空，返回纯文本消息。
    """
    if not images:
        return HumanMessage(content=text)

    content: list[dict] = []

    # 文本部分
    if text:
        content.append({"type": "text", "text": text})

    # 图片部分
    for b64_data, mime_type in images:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{b64_data}"
            }
        })

    return HumanMessage(content=content)


def build_multimodal_message_from_urls(
    text: str,
    image_urls: list[str],
) -> HumanMessage:
    """构建多模态 HumanMessage (使用图片 URL)

    Args:
        text: 文本内容
        image_urls: 图片 URL 列表 (可以是 http URL 或 data URL)

    Returns:
        包含文本和图片的 HumanMessage

    Note:
        使用 URL 而非 base64 时，LLM 可能需要自己下载图片，
        建议优先使用 build_multimodal_message 传入 base64 数据。
    """
    if not image_urls:
        return HumanMessage(content=text)

    content: list[dict] = []

    if text:
        content.append({"type": "text", "text": text})

    for url in image_urls:
        content.append({
            "type": "image_url",
            "image_url": {"url": url}
        })

    return HumanMessage(content=content)


def message_to_text(message: BaseMessage) -> str:
    """从消息中提取纯文本内容

    Args:
        message: LangChain 消息对象

    Returns:
        消息的文本内容

    Note:
        对于多模态消息，只提取 type=text 的部分。
        图片部分会被描述为 "[图片]"。

    Example:
        >>> msg = HumanMessage(content="Hello")
        >>> message_to_text(msg)
        'Hello'
        >>> msg2 = HumanMessage(content=[
        ...     {"type": "text", "text": "看图"},
        ...     {"type": "image_url", "image_url": {"url": "data:..."}}
        ... ])
        >>> message_to_text(msg2)
        '看图 [图片]'
    """
    content = message.content

    # 字符串内容
    if isinstance(content, str):
        return content

    # 多模态内容 (列表)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "text":
                    parts.append(item.get("text", ""))
                elif item_type == "image_url":
                    parts.append("[图片]")
        return " ".join(parts)

    return str(content)


def message_to_storage_text(message: BaseMessage) -> str:
    """将消息转换为适合存储的纯文本格式

    与 message_to_text 类似，但格式更适合历史存储：
    - 多张图片合并为 "[图片x3]" 而非 "[图片] [图片] [图片]"

    Args:
        message: LangChain 消息对象

    Returns:
        适合存储的文本格式
    """
    content = message.content

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []
        image_count = 0

        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "text":
                    text_parts.append(item.get("text", ""))
                elif item_type == "image_url":
                    image_count += 1

        result_parts = []
        if image_count > 0:
            result_parts.append(f"[图片x{image_count}]")
        if text_parts:
            result_parts.append(" ".join(text_parts))

        return " ".join(result_parts)

    return str(content)


def build_ai_message(text: str) -> AIMessage:
    """构建 AI 响应消息

    Args:
        text: 响应文本

    Returns:
        AIMessage 对象
    """
    return AIMessage(content=text)


def build_system_message(text: str) -> SystemMessage:
    """构建系统消息

    Args:
        text: 系统提示文本

    Returns:
        SystemMessage 对象
    """
    return SystemMessage(content=text)


def is_multimodal_message(message: BaseMessage) -> bool:
    """判断消息是否是多模态消息

    Args:
        message: LangChain 消息对象

    Returns:
        如果消息包含图片则返回 True
    """
    content = message.content

    if not isinstance(content, list):
        return False

    for item in content:
        if isinstance(item, dict) and item.get("type") == "image_url":
            return True

    return False


def count_images_in_message(message: BaseMessage) -> int:
    """统计消息中的图片数量

    Args:
        message: LangChain 消息对象

    Returns:
        图片数量
    """
    content = message.content

    if not isinstance(content, list):
        return 0

    count = 0
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image_url":
            count += 1

    return count


def strip_images_from_message(message: HumanMessage) -> HumanMessage:
    """从消息中移除图片，只保留文本

    Args:
        message: 原始 HumanMessage

    Returns:
        只包含文本的新 HumanMessage

    Note:
        用于将多模态消息转换为纯文本消息存储到历史。
    """
    text = message_to_storage_text(message)
    return HumanMessage(content=text)


# ==================== 批量操作 ====================


def merge_text_messages(messages: list[str]) -> str:
    """合并多条文本为一条

    Args:
        messages: 文本列表

    Returns:
        合并后的文本，用换行分隔
    """
    return "\n".join(m for m in messages if m)


def build_context_message(
    main_text: str,
    reply_context: str | None = None,
    forward_summary: str | None = None,
) -> str:
    """构建包含上下文的文本（旧版，保持兼容）

    Args:
        main_text: 主要文本内容
        reply_context: 引用消息的上下文
        forward_summary: 合并转发的摘要

    Returns:
        组合后的完整文本
    """
    parts = []

    if reply_context:
        parts.append(f"[引用消息: {reply_context}]")

    if forward_summary:
        parts.append(f"[合并转发:\n{forward_summary}]")

    parts.append(main_text)

    return "\n".join(parts)


def build_rich_context_message(
    main_text: str,
    sender_name: str = "",
    sender_qq: int = 0,
    message_id: int = 0,
    group_id: int | None = None,
    reply_to_id: int | None = None,
    reply_context: str | None = None,
    at_targets: list[str] | None = None,
    forward_summary: str | None = None,
) -> str:
    """构建包含完整上下文的消息文本

    让 LLM 知道：谁发的、消息ID、引用了什么、@了谁

    Args:
        main_text: 主要文本内容
        sender_name: 发送者昵称
        sender_qq: 发送者 QQ 号
        message_id: 当前消息 ID
        group_id: 群号（私聊为 None）
        reply_to_id: 引用的消息 ID
        reply_context: 引用消息的内容描述
        at_targets: @ 的目标 QQ 号列表
        forward_summary: 合并转发的摘要

    Returns:
        格式化的完整消息文本
    """
    parts = []

    # 消息上下文部分
    context_lines = []

    if sender_name or sender_qq:
        if sender_name and sender_qq:
            context_lines.append(f"发送者: {sender_name} (QQ: {sender_qq})")
        elif sender_qq:
            context_lines.append(f"发送者 QQ: {sender_qq}")
        else:
            context_lines.append(f"发送者: {sender_name}")

    if message_id:
        context_lines.append(f"消息ID: {message_id}")

    if group_id:
        context_lines.append(f"群号: {group_id}")

    if reply_to_id and reply_context:
        context_lines.append(f"引用: 消息ID {reply_to_id}，内容为「{reply_context}」")
    elif reply_context:
        context_lines.append(f"引用: {reply_context}")

    if at_targets:
        context_lines.append(f"@了: {', '.join(at_targets)}")

    if context_lines:
        parts.append("[消息上下文]\n" + "\n".join(context_lines))

    # 合并转发
    if forward_summary:
        parts.append(f"[合并转发]\n{forward_summary}")

    # 消息正文
    if main_text:
        parts.append(f"[消息内容]\n{main_text}")
    else:
        parts.append("[消息内容]\n（无文字）")

    return "\n\n".join(parts)


# ==================== 工具消息处理 ====================


def extract_tool_images(messages: list[BaseMessage]) -> list[tuple[str, str]]:
    """从消息列表中提取工具返回的图片

    只提取最后一个 HumanMessage 之后的工具返回的图片，
    避免重复发送历史图片。

    Args:
        messages: LangChain 消息列表

    Returns:
        图片列表 [(base64_data, mime_type), ...]

    Example:
        >>> from langchain_core.messages import HumanMessage, ToolMessage
        >>> messages = [
        ...     HumanMessage(content="生成图片"),
        ...     ToolMessage(content=[{"type": "image", "base64": "iVBORw..."}], tool_call_id="1"),
        ... ]
        >>> images = extract_tool_images(messages)
        >>> len(images)
        1
    """
    images = []

    # 找到最后一个 HumanMessage 的位置
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i

    # 只处理最后一个 HumanMessage 之后的消息
    start_idx = last_human_idx + 1 if last_human_idx >= 0 else 0

    for msg in messages[start_idx:]:
        if not isinstance(msg, ToolMessage):
            continue

        content = msg.content

        # ToolMessage content 可能是字符串或列表
        if isinstance(content, str):
            continue

        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue

                # 检查是否是图片类型
                if item.get("type") == "image":
                    base64_data = item.get("base64", "")
                    if base64_data:
                        # 根据 base64 开头检测 MIME 类型
                        mime_type = _detect_image_mime_from_base64(base64_data)
                        images.append((base64_data, mime_type))

    return images


def _detect_image_mime_from_base64(base64_data: str) -> str:
    """根据 base64 数据开头检测图片 MIME 类型

    Args:
        base64_data: base64 编码的图片数据

    Returns:
        MIME 类型字符串
    """
    if base64_data.startswith("/9j/"):
        return "image/jpeg"
    elif base64_data.startswith("iVBORw"):
        return "image/png"
    elif base64_data.startswith("R0lGOD"):
        return "image/gif"
    elif base64_data.startswith("UklGR"):
        return "image/webp"
    else:
        return "image/png"  # 默认


def extract_send_commands(messages: list[BaseMessage]) -> list[dict]:
    """从消息列表中提取 send_message 工具的发送指令

    遍历所有 ToolMessage，提取 __CMD__: 标记后的 JSON 指令。

    Args:
        messages: LangChain 消息列表

    Returns:
        发送指令列表，每个指令包含 text, image, at_users, reply_to

    Example:
        >>> commands = extract_send_commands(messages)
        >>> for cmd in commands:
        ...     print(cmd["text"], cmd["image"])
    """
    import json

    CMD_PREFIX = "__CMD__:"

    commands = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue

        content = msg.content
        if not isinstance(content, str):
            continue

        # 查找 __CMD__: 标记
        if CMD_PREFIX in content:
            try:
                # 提取 __CMD__: 之后的 JSON
                cmd_start = content.index(CMD_PREFIX) + len(CMD_PREFIX)
                json_str = content[cmd_start:].strip()
                data = json.loads(json_str)
                if isinstance(data, dict) and data.get("_type") == "send_message_command":
                    commands.append(data)
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    return commands
