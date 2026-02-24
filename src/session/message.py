"""待聚合消息数据结构"""

import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PendingMessage:
    """待聚合的单条消息"""
    sender_name: str
    sender_qq: int
    message_id: int
    text: str
    image_urls: list[str] = field(default_factory=list)
    reply_context: str | None = None
    reply_to_id: int | None = None
    at_targets: list[str] = field(default_factory=list)
    forward_summary: str | None = None
    file_descriptions: list[str] = field(default_factory=list)
    audio_text: str | None = None
    audio_path: str | None = None
    timestamp: float = field(default_factory=time.time)

    def format(self) -> str:
        """格式化为可读文本（聊天记录风格）"""
        dt = datetime.fromtimestamp(self.timestamp)
        time_str = f"{dt.year}年{dt.month}月{dt.day}日{dt.hour}时{dt.minute}分"
        header = f"{self.sender_name}({self.sender_qq}) {time_str} #{self.message_id}"

        if self.reply_context:
            if ": " in self.reply_context:
                header += f" 回复{self.reply_context.split(': ')[0]}"
            else:
                header += " 回复"

        if self.at_targets:
            header += " " + " ".join(f"@{t}" for t in self.at_targets)

        parts = [header + ":"]

        if self.reply_context:
            content = self.reply_context.split(": ", 1)[1] if ": " in self.reply_context else self.reply_context
            if len(content) > 50:
                content = content[:50] + "..."
            parts.append(f"> {content}")

        if self.text:
            parts.append(self.text)
        elif self.audio_text:
            parts.append(f"[语音转文字]: {self.audio_text}")
        elif self.audio_path:
            parts.append("[语音消息]")
        elif self.image_urls:
            parts.append(f"[图片x{len(self.image_urls)}]")

        if self.file_descriptions:
            parts.append("\n".join(self.file_descriptions))

        if self.forward_summary:
            parts.append(f"[转发消息]\n{self.forward_summary}")

        return "\n".join(parts) if parts else "(空消息)"
