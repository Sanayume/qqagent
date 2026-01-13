"""
OneBot 消息段工具 - 解析和构建 OneBot11 消息段

本模块提供纯函数，用于：
- 解析 OneBot 消息段数组，提取文本、图片、引用等信息
- 构建 OneBot 消息段，用于发送消息

注意：
- 本模块不做网络请求（不下载图片）
- 本模块不调用 OneBot API
- 本模块不依赖 Adapter 或任何业务逻辑
"""

from dataclasses import dataclass, field


@dataclass
class ParsedMessage:
    """解析后的消息结构

    Attributes:
        text: 提取的纯文本内容
        image_urls: 图片 URL 列表
        image_files: 图片文件名列表 (OneBot file ID)
        reply_id: 引用消息 ID (如果有)
        forward_id: 合并转发 ID (如果有)
        at_targets: @ 的目标列表 (QQ号或'all')
        face_ids: QQ 表情 ID 列表
        mface_summaries: 商城表情描述列表
        file_urls: 文件 URL 列表
        file_names: 文件名列表
        has_record: 是否包含语音
        has_video: 是否包含视频
        raw_segments: 原始消息段
    """
    text: str = ""
    image_urls: list[str] = field(default_factory=list)
    image_files: list[str] = field(default_factory=list)
    reply_id: int | None = None
    forward_id: str | None = None
    at_targets: list[str] = field(default_factory=list)
    face_ids: list[int] = field(default_factory=list)
    mface_summaries: list[str] = field(default_factory=list)
    file_urls: list[str] = field(default_factory=list)
    file_names: list[str] = field(default_factory=list)
    has_record: bool = False
    has_video: bool = False
    raw_segments: list[dict] = field(default_factory=list)

    def has_images(self) -> bool:
        """是否包含图片"""
        return bool(self.image_urls or self.image_files)

    def has_files(self) -> bool:
        """是否包含文件"""
        return bool(self.file_urls or self.file_names)

    def has_reply(self) -> bool:
        """是否是回复消息"""
        return self.reply_id is not None

    def has_forward(self) -> bool:
        """是否包含合并转发"""
        return self.forward_id is not None

    def get_face_text(self) -> str:
        """获取表情的文本表示"""
        parts = []
        for face_id in self.face_ids:
            parts.append(f"[QQ表情:{face_id}]")
        for summary in self.mface_summaries:
            parts.append(f"[{summary}]")
        return " ".join(parts)


def parse_segments(segments: list[dict]) -> ParsedMessage:
    """解析 OneBot 消息段数组

    Args:
        segments: OneBot 消息段数组，每个元素格式为 {"type": "...", "data": {...}}

    Returns:
        ParsedMessage 对象，包含解析后的各类内容

    Example:
        >>> segments = [
        ...     {"type": "text", "data": {"text": "hello"}},
        ...     {"type": "image", "data": {"url": "http://...", "file": "abc.jpg"}}
        ... ]
        >>> result = parse_segments(segments)
        >>> result.text
        'hello'
        >>> result.image_urls
        ['http://...']
    """
    result = ParsedMessage(raw_segments=segments)
    text_parts = []

    for seg in segments:
        seg_type = seg.get("type", "")
        data = seg.get("data", {})

        if seg_type == "text":
            text_parts.append(data.get("text", ""))

        elif seg_type == "image":
            url = data.get("url", "")
            file_id = data.get("file", "")
            # NapCat sometimes puts the URL in the file field
            # Check if file field contains a URL
            if not url and file_id and (file_id.startswith("http://") or file_id.startswith("https://")):
                url = file_id
            if url:
                result.image_urls.append(url)
            if file_id:
                result.image_files.append(file_id)

        elif seg_type == "reply":
            reply_id = data.get("id")
            if reply_id is not None:
                try:
                    result.reply_id = int(reply_id)
                except (ValueError, TypeError):
                    pass

        elif seg_type == "forward":
            result.forward_id = data.get("id")

        elif seg_type == "at":
            qq = data.get("qq", "")
            if qq:
                result.at_targets.append(str(qq))

        elif seg_type == "face":
            face_id = data.get("id")
            if face_id is not None:
                try:
                    result.face_ids.append(int(face_id))
                except (ValueError, TypeError):
                    pass

        elif seg_type == "mface":
            summary = data.get("summary", "动画表情")
            result.mface_summaries.append(summary)

        elif seg_type == "file":
            url = data.get("url", "")
            name = data.get("name", data.get("file", ""))
            if url:
                result.file_urls.append(url)
            if name:
                result.file_names.append(name)

        elif seg_type == "record":
            result.has_record = True

        elif seg_type == "video":
            result.has_video = True

    result.text = "".join(text_parts).strip()
    return result


def extract_text(segments: list[dict]) -> str:
    """从消息段中提取纯文本

    Args:
        segments: OneBot 消息段数组

    Returns:
        拼接后的纯文本内容

    Example:
        >>> segments = [
        ...     {"type": "text", "data": {"text": "Hello "}},
        ...     {"type": "at", "data": {"qq": "123"}},
        ...     {"type": "text", "data": {"text": "World"}}
        ... ]
        >>> extract_text(segments)
        'Hello World'
    """
    text_parts = []
    for seg in segments:
        if seg.get("type") == "text":
            text_parts.append(seg.get("data", {}).get("text", ""))
    return "".join(text_parts).strip()


def extract_image_urls(segments: list[dict]) -> list[str]:
    """从消息段中提取图片 URL 列表

    Args:
        segments: OneBot 消息段数组

    Returns:
        图片 URL 列表 (不包括空 URL)

    Example:
        >>> segments = [
        ...     {"type": "image", "data": {"url": "http://a.jpg"}},
        ...     {"type": "image", "data": {"url": "http://b.jpg", "file": "b.jpg"}}
        ... ]
        >>> extract_image_urls(segments)
        ['http://a.jpg', 'http://b.jpg']
    """
    urls = []
    for seg in segments:
        if seg.get("type") == "image":
            url = seg.get("data", {}).get("url", "")
            if url:
                urls.append(url)
    return urls


def extract_reply_id(segments: list[dict]) -> int | None:
    """从消息段中提取引用消息 ID

    Args:
        segments: OneBot 消息段数组

    Returns:
        引用消息 ID，如果没有则返回 None

    Example:
        >>> segments = [
        ...     {"type": "reply", "data": {"id": "12345"}},
        ...     {"type": "text", "data": {"text": "回复内容"}}
        ... ]
        >>> extract_reply_id(segments)
        12345
    """
    for seg in segments:
        if seg.get("type") == "reply":
            reply_id = seg.get("data", {}).get("id")
            if reply_id is not None:
                try:
                    return int(reply_id)
                except (ValueError, TypeError):
                    pass
    return None


def extract_forward_id(segments: list[dict]) -> str | None:
    """从消息段中提取合并转发 ID

    Args:
        segments: OneBot 消息段数组

    Returns:
        合并转发 ID，如果没有则返回 None
    """
    for seg in segments:
        if seg.get("type") == "forward":
            return seg.get("data", {}).get("id")
    return None


def extract_at_targets(segments: list[dict]) -> list[str]:
    """从消息段中提取 @ 目标列表

    Args:
        segments: OneBot 消息段数组

    Returns:
        @ 目标列表 (QQ 号字符串或 'all')
    """
    targets = []
    for seg in segments:
        if seg.get("type") == "at":
            qq = seg.get("data", {}).get("qq", "")
            if qq:
                targets.append(str(qq))
    return targets


# ==================== 消息段构建函数 ====================


def build_text_segment(text: str) -> dict:
    """构建文本消息段

    Args:
        text: 文本内容

    Returns:
        OneBot 文本消息段

    Example:
        >>> build_text_segment("Hello")
        {'type': 'text', 'data': {'text': 'Hello'}}
    """
    return {"type": "text", "data": {"text": text}}


def build_image_segment(file: str, type_: str = "") -> dict:
    """构建图片消息段

    Args:
        file: 图片文件，支持以下格式:
            - base64://... (base64 编码)
            - file:///... (本地文件路径)
            - http(s)://... (网络 URL)
        type_: 图片类型，可选值:
            - "" (普通图片)
            - "flash" (闪照)
            - "show" (秀图)

    Returns:
        OneBot 图片消息段

    Example:
        >>> build_image_segment("base64://abc123")
        {'type': 'image', 'data': {'file': 'base64://abc123'}}
        >>> build_image_segment("http://example.com/a.jpg", "flash")
        {'type': 'image', 'data': {'file': 'http://example.com/a.jpg', 'type': 'flash'}}
    """
    data = {"file": file}
    if type_:
        data["type"] = type_
    return {"type": "image", "data": data}


def build_reply_segment(message_id: int | str) -> dict:
    """构建引用回复消息段

    Args:
        message_id: 被引用的消息 ID

    Returns:
        OneBot 引用消息段

    Example:
        >>> build_reply_segment(12345)
        {'type': 'reply', 'data': {'id': '12345'}}
    """
    return {"type": "reply", "data": {"id": str(message_id)}}


def build_at_segment(qq: int | str) -> dict:
    """构建 @ 消息段

    Args:
        qq: 要 @ 的 QQ 号，或 'all' 表示 @全体成员

    Returns:
        OneBot @ 消息段

    Example:
        >>> build_at_segment(123456)
        {'type': 'at', 'data': {'qq': '123456'}}
        >>> build_at_segment("all")
        {'type': 'at', 'data': {'qq': 'all'}}
    """
    return {"type": "at", "data": {"qq": str(qq)}}


def build_face_segment(face_id: int) -> dict:
    """构建 QQ 表情消息段

    Args:
        face_id: 表情 ID

    Returns:
        OneBot 表情消息段
    """
    return {"type": "face", "data": {"id": str(face_id)}}


def build_record_segment(file: str) -> dict:
    """构建语音消息段

    Args:
        file: 语音文件，格式同图片

    Returns:
        OneBot 语音消息段
    """
    return {"type": "record", "data": {"file": file}}


def build_video_segment(file: str) -> dict:
    """构建视频消息段

    Args:
        file: 视频文件，格式同图片

    Returns:
        OneBot 视频消息段
    """
    return {"type": "video", "data": {"file": file}}


def build_forward_node(
    user_id: int,
    nickname: str,
    content: list[dict] | str,
) -> dict:
    """构建合并转发节点

    Args:
        user_id: 发送者 QQ 号
        nickname: 发送者昵称
        content: 消息内容 (消息段数组或字符串)

    Returns:
        OneBot 转发节点
    """
    return {
        "type": "node",
        "data": {
            "user_id": str(user_id),
            "nickname": nickname,
            "content": content,
        }
    }


def build_message(*segments: dict) -> list[dict]:
    """组合多个消息段为消息数组

    Args:
        *segments: 任意数量的消息段

    Returns:
        消息段数组

    Example:
        >>> msg = build_message(
        ...     build_reply_segment(123),
        ...     build_text_segment("收到！"),
        ...     build_image_segment("base64://abc")
        ... )
        >>> len(msg)
        3
    """
    return list(segments)


# ==================== 便捷函数 ====================


def text_message(text: str) -> list[dict]:
    """快速创建纯文本消息

    Args:
        text: 文本内容

    Returns:
        只包含一个文本段的消息数组
    """
    return [build_text_segment(text)]


def image_message(file: str) -> list[dict]:
    """快速创建纯图片消息

    Args:
        file: 图片文件

    Returns:
        只包含一个图片段的消息数组
    """
    return [build_image_segment(file)]


def reply_text_message(message_id: int | str, text: str) -> list[dict]:
    """快速创建带引用的文本回复

    Args:
        message_id: 被引用的消息 ID
        text: 回复内容

    Returns:
        包含引用段和文本段的消息数组
    """
    return [
        build_reply_segment(message_id),
        build_text_segment(text),
    ]


def make_text_description(parsed: ParsedMessage) -> str:
    """生成消息的文本描述（用于历史存储）

    Args:
        parsed: 解析后的消息

    Returns:
        文本描述，例如 "[图片x2] 帮我P图"

    Note:
        此函数用于将多模态消息转换为纯文本存储，
        不保留 base64 数据，只保留描述信息。
    """
    parts = []

    # 媒体描述
    if parsed.has_images():
        count = len(parsed.image_urls) or len(parsed.image_files)
        parts.append(f"[图片x{count}]")

    if parsed.has_files():
        count = len(parsed.file_urls) or len(parsed.file_names)
        parts.append(f"[文件x{count}]")

    if parsed.has_record:
        parts.append("[语音]")

    if parsed.has_video:
        parts.append("[视频]")

    if parsed.has_forward():
        parts.append("[合并转发]")

    # 表情描述
    face_text = parsed.get_face_text()
    if face_text:
        parts.append(face_text)

    # 正文
    if parsed.text:
        parts.append(parsed.text)

    return " ".join(parts)
