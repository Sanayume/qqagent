"""
媒体处理工具 - 下载、编码、MIME 检测

本模块提供纯函数，用于：
- 下载网络图片
- Base64 编码/解码
- MIME 类型检测
- Data URL 生成

注意：
- 本模块不知道 OneBot 协议
- 本模块不知道业务逻辑
- 所有函数输入输出明确，抛出异常让调用者处理
"""

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

# MIME 类型魔数映射
MIME_SIGNATURES: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # WebP (需要额外检查)
    b"BM": "image/bmp",
    b"\x00\x00\x01\x00": "image/x-icon",  # ICO
    b"\x00\x00\x02\x00": "image/x-icon",  # CUR
}

# 扩展名到 MIME 类型映射
EXT_TO_MIME: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "ico": "image/x-icon",
    "svg": "image/svg+xml",
    "tiff": "image/tiff",
    "tif": "image/tiff",
}


def encode_base64(data: bytes) -> str:
    """将二进制数据编码为 base64 字符串

    Args:
        data: 二进制数据

    Returns:
        base64 编码的字符串

    Example:
        >>> encode_base64(b"hello")
        'aGVsbG8='
    """
    return base64.b64encode(data).decode("utf-8")


def decode_base64(data: str) -> bytes:
    """将 base64 字符串解码为二进制数据

    Args:
        data: base64 编码的字符串

    Returns:
        解码后的二进制数据

    Raises:
        ValueError: base64 格式无效时
    """
    try:
        return base64.b64decode(data)
    except Exception as e:
        raise ValueError(f"Invalid base64 data: {e}") from e


def detect_mime_type(data: bytes) -> str:
    """根据文件头魔数检测 MIME 类型

    Args:
        data: 二进制数据 (至少需要前 12 字节)

    Returns:
        检测到的 MIME 类型，未知类型返回 "application/octet-stream"

    Example:
        >>> data = b'\\x89PNG\\r\\n\\x1a\\n...'
        >>> detect_mime_type(data)
        'image/png'
    """
    if len(data) < 4:
        return "application/octet-stream"

    # 检查各种魔数
    for signature, mime_type in MIME_SIGNATURES.items():
        if data.startswith(signature):
            # WebP 需要额外检查
            if signature == b"RIFF" and len(data) >= 12:
                if data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime_type

    return "application/octet-stream"


def detect_mime_from_extension(filename: str) -> str:
    """根据文件扩展名检测 MIME 类型

    Args:
        filename: 文件名或路径

    Returns:
        对应的 MIME 类型，未知扩展名返回 "application/octet-stream"
    """
    if "." not in filename:
        return "application/octet-stream"

    ext = filename.rsplit(".", 1)[-1].lower()
    return EXT_TO_MIME.get(ext, "application/octet-stream")


def make_data_url(data: bytes, mime_type: str | None = None) -> str:
    """生成 data URL (用于 LLM 多模态输入)

    Args:
        data: 二进制数据
        mime_type: MIME 类型，为 None 时自动检测

    Returns:
        data URL 格式字符串: data:<mime>;base64,<base64_data>

    Example:
        >>> data = b'\\x89PNG...'  # PNG 图片数据
        >>> url = make_data_url(data)
        >>> url.startswith('data:image/png;base64,')
        True
    """
    if mime_type is None:
        mime_type = detect_mime_type(data)

    b64 = encode_base64(data)
    return f"data:{mime_type};base64,{b64}"


def make_data_url_from_base64(base64_data: str, mime_type: str) -> str:
    """从已有的 base64 数据生成 data URL

    Args:
        base64_data: base64 编码的数据
        mime_type: MIME 类型

    Returns:
        data URL 格式字符串
    """
    return f"data:{mime_type};base64,{base64_data}"


def parse_data_url(data_url: str) -> tuple[bytes, str]:
    """解析 data URL

    Args:
        data_url: data URL 字符串

    Returns:
        (二进制数据, MIME 类型) 元组

    Raises:
        ValueError: data URL 格式无效时
    """
    if not data_url.startswith("data:"):
        raise ValueError("Invalid data URL: must start with 'data:'")

    # data:image/png;base64,xxxxx
    try:
        header, b64_data = data_url.split(",", 1)
        mime_type = header.split(";")[0].replace("data:", "")
        data = decode_base64(b64_data)
        return data, mime_type
    except Exception as e:
        raise ValueError(f"Invalid data URL format: {e}") from e


# ==================== 异步下载函数 ====================


async def download_image(
    url: str,
    client: "httpx.AsyncClient | None" = None,
    timeout: float = 30.0,
) -> bytes:
    """下载图片

    Args:
        url: 图片 URL
        client: httpx 异步客户端，为 None 时创建临时客户端
        timeout: 下载超时时间（秒）

    Returns:
        图片二进制数据

    Raises:
        httpx.HTTPError: 下载失败时
        httpx.TimeoutException: 超时时

    Example:
        >>> import httpx
        >>> async with httpx.AsyncClient() as client:
        ...     data = await download_image("https://example.com/image.png", client)
    """
    import httpx

    if client is None:
        async with httpx.AsyncClient(timeout=timeout) as temp_client:
            resp = await temp_client.get(url)
            resp.raise_for_status()
            return resp.content
    else:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.content


async def download_and_encode(
    url: str,
    client: "httpx.AsyncClient | None" = None,
    timeout: float = 30.0,
) -> tuple[str, str]:
    """下载图片并编码为 base64

    Args:
        url: 图片 URL
        client: httpx 异步客户端
        timeout: 下载超时时间（秒）

    Returns:
        (base64_data, mime_type) 元组

    Raises:
        httpx.HTTPError: 下载失败时

    Example:
        >>> b64, mime = await download_and_encode("https://example.com/image.png")
        >>> mime
        'image/png'
    """
    data = await download_image(url, client, timeout)
    mime_type = detect_mime_type(data)
    b64 = encode_base64(data)
    return b64, mime_type


async def download_to_data_url(
    url: str,
    client: "httpx.AsyncClient | None" = None,
    timeout: float = 30.0,
) -> str:
    """下载图片并生成 data URL

    Args:
        url: 图片 URL
        client: httpx 异步客户端
        timeout: 下载超时时间（秒）

    Returns:
        data URL 格式字符串

    Raises:
        httpx.HTTPError: 下载失败时
    """
    data = await download_image(url, client, timeout)
    return make_data_url(data)


# ==================== 同步下载函数 (用于非异步场景) ====================


def download_image_sync(
    url: str,
    timeout: float = 30.0,
) -> bytes:
    """同步下载图片

    Args:
        url: 图片 URL
        timeout: 下载超时时间（秒）

    Returns:
        图片二进制数据

    Raises:
        httpx.HTTPError: 下载失败时
    """
    import httpx

    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content


def download_and_encode_sync(
    url: str,
    timeout: float = 30.0,
) -> tuple[str, str]:
    """同步下载图片并编码

    Args:
        url: 图片 URL
        timeout: 下载超时时间（秒）

    Returns:
        (base64_data, mime_type) 元组
    """
    data = download_image_sync(url, timeout)
    mime_type = detect_mime_type(data)
    b64 = encode_base64(data)
    return b64, mime_type


# ==================== 工具函数 ====================


def is_image_url(url: str) -> bool:
    """判断 URL 是否可能是图片

    Args:
        url: URL 字符串

    Returns:
        如果 URL 扩展名是图片格式则返回 True
    """
    url_lower = url.lower().split("?")[0]  # 去掉查询参数
    return any(url_lower.endswith(f".{ext}") for ext in EXT_TO_MIME)


def get_image_size_estimate(base64_data: str) -> int:
    """估算 base64 图片的原始大小（字节）

    Args:
        base64_data: base64 编码的图片数据

    Returns:
        估算的原始字节数
    """
    # base64 编码后大小约为原始的 4/3
    return int(len(base64_data) * 3 / 4)


def is_base64_image_too_large(base64_data: str, max_size_mb: float = 10.0) -> bool:
    """检查 base64 图片是否超过大小限制

    Args:
        base64_data: base64 编码的图片数据
        max_size_mb: 最大允许的大小（MB）

    Returns:
        如果超过限制返回 True
    """
    size = get_image_size_estimate(base64_data)
    return size > max_size_mb * 1024 * 1024
