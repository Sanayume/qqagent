"""聚合消息格式化

将聚合后的消息列表格式化为 LLM 可读的文本。
"""

from src.session.message import PendingMessage


def collect_images_from_messages(messages: list[PendingMessage]) -> list[str]:
    """从聚合消息中收集所有图片 URL"""
    urls = []
    for msg in messages:
        urls.extend(msg.image_urls)
    return urls


def format_aggregated_messages(
    messages: list[PendingMessage],
    group_id: int,
    image_paths: list[str] | None = None,
) -> str:
    """格式化聚合后的群消息为 LLM 可读文本（聊天记录风格）"""
    if not messages:
        return "[无消息]"

    parts = [f"[群{group_id} 聊天记录]", ""]

    for msg in messages:
        parts.append(msg.format())
        parts.append("")

    if image_paths:
        parts.append("[图片路径]")
        parts.append("\n".join(image_paths))

    return "\n".join(parts)


def format_private_aggregated_messages(
    messages: list[PendingMessage],
    image_paths: list[str] | None = None,
) -> str:
    """格式化私聊聚合消息为 LLM 可读文本"""
    if not messages:
        return "[无消息]"

    from src.core.llm_message import build_rich_context_message

    first_msg = messages[0]
    last_msg = messages[-1]

    merged_text = "\n".join(m.text for m in messages if m.text)

    reply_context = reply_to_id = None
    for m in messages:
        if m.reply_context:
            reply_context = m.reply_context
            reply_to_id = m.reply_to_id
            break

    all_file_descs = [d for m in messages for d in m.file_descriptions]
    forward_parts = [m.forward_summary for m in messages if m.forward_summary]
    all_at = [t for m in messages for t in m.at_targets]

    return build_rich_context_message(
        main_text=merged_text,
        sender_name=first_msg.sender_name,
        sender_qq=first_msg.sender_qq,
        message_id=last_msg.message_id,
        group_id=None,
        reply_to_id=reply_to_id,
        reply_context=reply_context,
        at_targets=all_at or None,
        forward_summary="\n".join(forward_parts) if forward_parts else None,
        file_descriptions=all_file_descs or None,
        image_paths=image_paths or None,
    )
