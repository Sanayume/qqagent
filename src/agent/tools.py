"""
内置工具定义

提供 Agent 可以使用的基础工具。
"""

import contextvars
from typing import Any, Callable
from langchain_core.tools import tool


# ==================== 实时消息回调 ====================

# 使用 ContextVar 实现线程/协程安全的回调隔离
# 每个 invoke_agent 调用设置自己的回调，不会互相覆盖
_send_message_callback_var: contextvars.ContextVar[Callable[[dict], None] | None] = \
    contextvars.ContextVar("send_message_callback", default=None)


def set_send_message_callback(callback: Callable[[dict], None] | None):
    """设置当前上下文的 send_message 回调函数

    使用 ContextVar 实现隔离，不同协程/会话的回调互不影响。

    Args:
        callback: 回调函数，接收消息指令 dict，立即处理发送
                  设为 None 则禁用实时发送
    """
    _send_message_callback_var.set(callback)


def get_send_message_callback() -> Callable[[dict], None] | None:
    """获取当前上下文的回调函数"""
    return _send_message_callback_var.get()


# ==================== 工具定义 ====================


@tool
def send_message(
    text: str = "",
    image: str = "",
    record: str = "",
    at_users: Any = "",
    reply_to: int = 0,
    delay_minutes: int = 0,
) -> str:
    """发送消息到当前对话。这是你与用户交流的唯一方式。

    你的普通文字输出不会被任何人看到，只有调用此工具才能真正发送消息。

    【关键行为规则】
    1. 调用一次 send_message 就会发送一条消息，无需确认或重试
    2. 如果要发送多条消息，在一轮对话中连续调用多次，每次内容不同
    3. 绝对不要用相同或相似的内容重复调用此工具

    Args:
        text: 文本内容
        image: 图片 URL（可选）
        record: 语音文件路径（可选，支持 mp3/wav/ogg 等格式，超过55秒会自动切分）
        at_users: 要 @的用户 QQ 号，多个用逗号分隔，如 "123,456"（可选）
        reply_to: 要回复的消息 ID（可选）
        delay_minutes: 延迟发送的分钟数（可选，1~1440，即最多24小时）。
                       设为 0 表示立即发送（默认）。

    组合示例:
        - 纯文本: text="你好"
        - 纯图片: image="http://example.com/img.jpg"
        - 文本+图片: text="看这个", image="http://..."
        - @某人+文本: at_users="123456", text="你觉得呢"
        - 回复消息: reply_to=12345, text="同意"
        - 发送语音: record="workspace/tts/output.mp3"
        - 定时发送: text="早上好", delay_minutes=60（1小时后发送）

    Returns:
        发送状态确认（看到确认后请结束对话，不要继续调用工具）
    """
    import json

    # 解析 at_users - 兼容多种输入格式
    at_list = []
    if at_users:
        # 如果是整数，直接添加
        if isinstance(at_users, int):
            at_list.append(at_users)
        # 如果是列表，遍历添加
        elif isinstance(at_users, list):
            for item in at_users:
                if isinstance(item, int):
                    at_list.append(item)
                elif isinstance(item, str) and item.strip().isdigit():
                    at_list.append(int(item.strip()))
        # 如果是字符串，按逗号分隔
        elif isinstance(at_users, str):
            for qq in at_users.split(","):
                qq = qq.strip()
                if qq.isdigit():
                    at_list.append(int(qq))

    # 校验 delay_minutes
    try:
        delay_minutes = max(0, int(delay_minutes))
    except (ValueError, TypeError):
        delay_minutes = 0
    if delay_minutes > 1440:
        return "错误: delay_minutes 不能超过 1440（24小时）"

    # 构建发送指令
    command = {
        "_type": "send_message_command",
        "text": text,
        "image": image,
        "record": record,
        "at_users": at_list,
        "reply_to": reply_to,
        "delay_minutes": delay_minutes,
    }

    # 如果设置了实时回调，立即发送消息（或安排延迟发送）
    callback = get_send_message_callback()
    if callback is not None:
        try:
            callback(command)
        except Exception:
            # 回调失败不影响工具返回
            pass

    # 返回确认信息，明确告知消息已发送，LLM 应停止
    parts = []
    if text:
        parts.append(f"文本: {text[:50]}{'...' if len(text) > 50 else ''}")
    if image:
        parts.append(f"图片: {image[:30]}...")
    if record:
        parts.append(f"语音: {record[:30]}...")
    if at_list:
        parts.append(f"@: {at_list}")
    if reply_to:
        parts.append(f"回复: {reply_to}")

    # 区分立即发送和定时发送的返回消息
    if delay_minutes > 0:
        if delay_minutes >= 60:
            hours = delay_minutes // 60
            mins = delay_minutes % 60
            time_desc = f"{hours}小时{mins}分钟" if mins else f"{hours}小时"
        else:
            time_desc = f"{delay_minutes}分钟"
        return f"✓ 已安排定时发送，将在 {time_desc} 后发送。({', '.join(parts) or '空消息'}) 【任务完成，请结束对话】"

    return f"✓ 消息发送成功！({', '.join(parts) or '空消息'}) 【任务完成，请结束对话】"


# ==================== 文件下载回调 ====================

# 文件下载回调，由 main.py 设置
_download_file_callback_var: contextvars.ContextVar[Callable[[str], dict | None] | None] = \
    contextvars.ContextVar("download_file_callback", default=None)


def set_download_file_callback(callback: Callable[[str], dict | None] | None):
    """设置文件下载回调函数"""
    _download_file_callback_var.set(callback)


def get_download_file_callback() -> Callable[[str], dict | None] | None:
    """获取文件下载回调函数"""
    return _download_file_callback_var.get()


# 最大文件大小限制 (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024


@tool
def download_file(file_id: str) -> str:
    """下载用户发送的文件到本地工作目录。

    当用户发送文件时，消息中会包含 file_id。使用此工具可以下载文件到本地，
    然后你可以读取或处理该文件。

    Args:
        file_id: 文件ID，从用户发送的文件消息中获取

    Returns:
        成功时返回文件路径和大小信息，失败时返回错误信息

    注意:
        - 文件大小限制为 100MB，超过此大小的文件无法处理
        - 下载后的文件会保存在 workspace 目录中
    """
    import shutil
    from pathlib import Path

    if not file_id:
        return "错误: file_id 不能为空"

    callback = get_download_file_callback()
    if callback is None:
        return "错误: 文件下载服务不可用"

    try:
        # 调用回调获取文件信息
        file_info = callback(file_id)
        if file_info is None:
            return f"错误: 无法下载文件 (file_id: {file_id})"

        src_path = file_info.get("path", "")
        file_size = file_info.get("size", 0)

        # 确保 file_size 是整数
        try:
            file_size = int(file_size) if file_size else 0
        except (ValueError, TypeError):
            file_size = 0

        if not src_path:
            return "错误: 获取文件路径失败"

        # 检查文件大小
        if file_size > MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            return f"错误: 文件太大无法处理 ({size_mb:.1f}MB > 100MB 限制)"

        # 创建 workspace 目录
        workspace = Path("workspace")
        workspace.mkdir(exist_ok=True)

        # 复制文件到 workspace
        src = Path(src_path)
        if not src.exists():
            return f"错误: 源文件不存在 ({src_path})"

        dst = workspace / src.name
        # 如果目标文件已存在，添加序号
        if dst.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while dst.exists():
                dst = workspace / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.copy2(src, dst)

        from src.core.onebot import format_file_size
        size_str = format_file_size(file_size)

        return f"文件下载成功！\n文件路径: {str(dst.absolute()).replace(chr(92), '/')}\n文件大小: {size_str}"

    except Exception as e:
        return f"错误: 下载文件失败 ({e})"


@tool
def read_file(file_path: str) -> str | list:
    """读取文件内容。支持多种文件格式。

    使用此工具读取用户发送的文件内容。通常先用 download_file 下载文件，
    然后用此工具读取内容。

    Args:
        file_path: 文件的完整路径（从 download_file 返回的路径）

    Returns:
        文件内容：
        - 文本/代码/Office/PDF: 返回提取的文本内容
        - 图片: 返回特殊格式，LLM 可以直接"看到"图片

    支持的格式:
        - PDF (.pdf): 提取文本内容（需要 pymupdf 或 pdfplumber）
        - 图片 (.png, .jpg, .gif 等): 返回图片供 LLM 查看
        - 文本 (.txt, .md, .json, .yaml 等): 直接读取
        - 代码 (.py, .js, .ts, .java 等): 直接读取
        - Word (.docx): 提取段落和表格文本
        - Excel (.xlsx): 提取表格内容
        - PowerPoint (.pptx): 提取幻灯片文本

    注意:
        - 文本文件大小限制为 1MB
        - Office/PDF 需要安装对应的库
    """
    from src.core.file_reader import read_file as do_read_file, FileType
    from pathlib import Path

    if not file_path:
        return "错误: file_path 不能为空"

    # 路径容错：清理常见 LLM 错误（多余引号、转义符）
    file_path = file_path.strip().strip("'\"")

    p = Path(file_path)
    if not p.exists():
        from src.utils.path import fix_escaped_path
        fixed = fix_escaped_path(file_path)
        pf = Path(fixed)
        if pf.exists():
            p = pf
            file_path = fixed
        else:
            # 按文件名在 workspace 下搜索
            name = p.name or Path(fixed).name
            candidates = list(Path("workspace").rglob(name)) if name else []
            if candidates:
                p = candidates[0]
                file_path = str(p)
            else:
                return f"错误: 文件不存在: {file_path}\n提示: workspace 目录下的文件可以直接用相对路径，如 workspace/xxx.md"

    result = do_read_file(file_path)

    # 图片返回特殊格式，让框架构建多模态消息
    if result.success and result.is_base64 and result.file_type == FileType.IMAGE:
        return [
            {"type": "text", "text": f"[图片文件: {file_path}]"},
            {"type": "image", "base64": result.content, "mime_type": result.mime_type}
        ]

    return result.to_llm_format()


@tool
def render_text(text: str, width: int = 800) -> str:
    """将文本渲染成图片。当需要发送长文本或格式化内容时使用。

    【何时使用】
    - 需要发送超过3-4句话的长文本时
    - 需要展示代码、表格等格式化内容时
    - 想让内容更美观易读时

    【使用流程】
    1. 调用 render_text(text="内容") 获取图片路径
    2. 用 send_message(image="返回的路径") 发送图片

    Args:
        text: 要渲染的文本（支持 Markdown：标题#、列表-、代码块```、表格|）
        width: 图片宽度，默认 800

    Returns:
        成功返回图片路径，失败返回错误信息
    """
    from src.core.text_renderer import render_text as do_render

    if not text or not text.strip():
        return "错误: 文本内容不能为空"

    if len(text) > 50000:
        return f"错误: 文本过长 ({len(text)} > 50000 字符)"

    result = do_render(text, width=width)
    return result.to_tool_response()


# 默认工具列表
DEFAULT_TOOLS = [
    send_message,
]
