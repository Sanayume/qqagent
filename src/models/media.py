"""
多模态消息数据模型

定义用于处理 QQ 消息中各种媒体类型的数据结构：
- 图片 (ImageData)
- 文件 (FileData)
- 引用消息 (ReplyContext)
- 合并转发 (ForwardNode)
- 多模态消息 (MultimodalMessage)
"""

from dataclasses import dataclass, field
from enum import Enum


class MediaType(Enum):
    """媒体类型枚举"""
    IMAGE = "image"
    STICKER = "sticker"  # 表情包/动画表情
    FILE = "file"
    RECORD = "record"    # 语音
    VIDEO = "video"


@dataclass
class ImageData:
    """图片数据

    Attributes:
        url: 原始 URL (QQ CDN，可能会过期)
        base64: base64 编码的图片数据 (按需下载填充)
        file_name: 文件名
        file_id: OneBot file ID
        mime_type: MIME 类型
        is_flash: 是否闪照
        is_sticker: 是否表情包
        summary: 图片描述 (表情包可能有)
    """
    url: str = ""
    base64: str | None = None
    file_name: str = ""
    file_id: str = ""
    mime_type: str = "image/png"
    is_flash: bool = False
    is_sticker: bool = False
    summary: str = ""

    def has_data(self) -> bool:
        """是否有可用的图片数据"""
        return bool(self.base64 or self.url)

    def get_data_url(self) -> str | None:
        """获取 data URL 格式 (用于 LLM)"""
        if self.base64:
            return f"data:{self.mime_type};base64,{self.base64}"
        return None


@dataclass
class FileData:
    """文件数据

    Attributes:
        url: 文件下载 URL
        file_name: 文件名
        file_id: OneBot file ID
        file_size: 文件大小 (字节)
        content: 解析后的文本内容 (用于 txt/md 等)
        mime_type: MIME 类型
    """
    url: str = ""
    file_name: str = ""
    file_id: str = ""
    file_size: int = 0
    content: str | None = None
    mime_type: str = ""

    @property
    def extension(self) -> str:
        """获取文件扩展名"""
        if "." in self.file_name:
            return self.file_name.rsplit(".", 1)[-1].lower()
        return ""

    def is_text_file(self) -> bool:
        """是否是文本文件"""
        return self.extension in ("txt", "md", "json", "yaml", "yml", "csv", "log")


@dataclass
class ReplyContext:
    """引用消息上下文

    当用户回复某条消息时，记录被引用消息的内容。

    Attributes:
        message_id: 被引用消息的 ID
        sender_id: 发送者 QQ 号
        sender_name: 发送者昵称
        text: 被引用消息的文本内容
        images: 被引用消息中的图片列表
        raw_message: 原始消息段 (用于深度解析)
    """
    message_id: int
    sender_id: int | None = None
    sender_name: str = ""
    text: str = ""
    images: list[ImageData] = field(default_factory=list)
    raw_message: list[dict] = field(default_factory=list)

    def has_images(self) -> bool:
        """是否包含图片"""
        return bool(self.images)

    def get_summary(self, max_length: int = 50) -> str:
        """获取引用消息摘要"""
        text = self.text[:max_length]
        if len(self.text) > max_length:
            text += "..."
        if self.images:
            text += f" [含{len(self.images)}张图片]"
        return text


@dataclass
class ForwardNode:
    """转发节点

    合并转发消息中的单条消息。

    Attributes:
        sender_id: 发送者 QQ 号
        sender_name: 发送者昵称
        content: 消息内容 (纯文本)
        time: 发送时间戳
    """
    sender_id: int
    sender_name: str
    content: str
    time: int | None = None


@dataclass
class MultimodalMessage:
    """多模态消息

    封装一条 QQ 消息中的所有内容，包括文本、图片、文件、
    引用消息、合并转发等。

    Attributes:
        text: 纯文本内容
        images: 图片列表
        files: 文件列表
        reply_to: 引用消息上下文
        forward_messages: 合并转发消息列表
        face_text: QQ 表情转换后的文本描述
        raw_segments: 原始 OneBot 消息段
    """
    text: str = ""
    images: list[ImageData] = field(default_factory=list)
    files: list[FileData] = field(default_factory=list)
    reply_to: ReplyContext | None = None
    forward_messages: list[ForwardNode] | None = None
    face_text: str = ""
    raw_segments: list[dict] = field(default_factory=list)

    def has_images(self) -> bool:
        """是否包含图片 (不含引用消息中的)"""
        return bool(self.images)

    def has_files(self) -> bool:
        """是否包含文件"""
        return bool(self.files)

    def has_reply(self) -> bool:
        """是否是回复消息"""
        return self.reply_to is not None

    def has_forward(self) -> bool:
        """是否包含合并转发"""
        return bool(self.forward_messages)

    def get_full_text(self) -> str:
        """获取完整文本 (包含表情描述)"""
        parts = []
        if self.text:
            parts.append(self.text)
        if self.face_text:
            parts.append(self.face_text)
        return " ".join(parts)

    def get_all_images(self) -> list[ImageData]:
        """获取所有图片 (包括引用消息中的)"""
        all_images = list(self.images)
        if self.reply_to and self.reply_to.images:
            all_images.extend(self.reply_to.images)
        return all_images

    def get_reply_images(self) -> list[ImageData]:
        """获取引用消息中的图片"""
        if self.reply_to:
            return self.reply_to.images
        return []

    def is_image_only(self) -> bool:
        """是否只有图片没有文本"""
        return self.has_images() and not self.text.strip()

    def is_image_edit_request(self) -> bool:
        """判断是否是图片编辑请求

        当消息包含图片 (直接发送或引用) 且文本中包含编辑关键词时，
        认为是图片编辑请求。
        """
        edit_keywords = [
            "编辑", "修改", "P图", "处理", "生成", "画",
            "改", "加", "去掉", "换", "删除", "添加",
            "变成", "改成", "换成", "把", "帮我",
        ]
        all_images = self.get_all_images()
        text = self.get_full_text()
        return bool(all_images) and any(k in text for k in edit_keywords)

    def get_context_description(self) -> str:
        """获取消息的上下文描述 (用于日志)"""
        parts = []
        if self.text:
            parts.append(f"文本:{len(self.text)}字")
        if self.images:
            parts.append(f"图片:{len(self.images)}张")
        if self.files:
            parts.append(f"文件:{len(self.files)}个")
        if self.reply_to:
            parts.append(f"引用消息")
            if self.reply_to.images:
                parts.append(f"(含{len(self.reply_to.images)}图)")
        if self.forward_messages:
            parts.append(f"转发:{len(self.forward_messages)}条")
        return ", ".join(parts) if parts else "空消息"
