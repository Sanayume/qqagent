"""
媒体处理工具 - 下载、编码、MIME 检测、GIF 预处理

本模块提供纯函数，用于：
- 下载网络图片
- Base64 编码/解码
- MIME 类型检测
- Data URL 生成
- GIF 帧提取（兼容不支持 GIF 的 LLM）

注意：
- 本模块不知道 OneBot 协议
- 本模块不知道业务逻辑
- 所有函数输入输出明确，抛出异常让调用者处理
"""

import base64
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

from src.utils.logger import log

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
    b"#!AMR": "audio/amr",
    b"#!SILK": "audio/silk",
    b"OggS": "audio/ogg",
    b"fLaC": "audio/flac",
    b"\xff\xfb": "audio/mpeg",  # MP3
    b"\xff\xf3": "audio/mpeg",  # MP3
    b"\xff\xf2": "audio/mpeg",  # MP3
    b"ID3": "audio/mpeg",       # MP3 with ID3 tag
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
    # Audio
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "amr": "audio/amr",
    "silk": "audio/silk",
    "m4a": "audio/mp4",
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


def extract_gif_frame(
    data: bytes,
    frame_index: int = 2,
    output_format: str = "PNG",
) -> tuple[bytes, str]:
    """从 GIF 中提取指定帧，转换为静态图片

    很多 LLM 不支持 GIF 格式，使用此函数提取某一帧作为静态图片。

    Args:
        data: GIF 图片的二进制数据
        frame_index: 要提取的帧索引（从 0 开始，默认第 3 帧即 index=2）
        output_format: 输出格式，默认 PNG

    Returns:
        (图片二进制数据, MIME 类型) 元组

    Note:
        - 如果帧数不足，会取最后一帧
        - 如果 Pillow 未安装，原样返回 GIF 数据
    """
    try:
        from PIL import Image

        # 打开 GIF
        img = Image.open(io.BytesIO(data))

        # 获取总帧数
        n_frames = getattr(img, 'n_frames', 1)

        # 调整帧索引（不超过总帧数）
        actual_index = min(frame_index, n_frames - 1)

        # 跳转到指定帧
        if n_frames > 1:
            img.seek(actual_index)

        # 转换为 RGBA（处理透明度）再转为 RGB
        if img.mode in ('RGBA', 'P'):
            # 创建白色背景
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # 输出到字节流
        output = io.BytesIO()
        img.save(output, format=output_format)
        output_data = output.getvalue()

        mime_type = f"image/{output_format.lower()}"
        log.debug(f"GIF 预处理: 提取第 {actual_index + 1}/{n_frames} 帧 -> {output_format}")

        return output_data, mime_type

    except ImportError:
        log.warning("Pillow 未安装，无法预处理 GIF")
        return data, "image/gif"
    except Exception as e:
        log.warning(f"GIF 预处理失败: {e}，使用原图")
        return data, "image/gif"


def preprocess_image(data: bytes) -> tuple[bytes, str]:
    """预处理图片，确保 LLM 兼容

    目前的预处理：
    - GIF → 提取第 3 帧转为 PNG

    Args:
        data: 图片二进制数据

    Returns:
        (处理后的数据, MIME 类型) 元组
    """
    mime_type = detect_mime_type(data)

    # GIF 预处理
    if mime_type == "image/gif":
        return extract_gif_frame(data, frame_index=2)

    return data, mime_type


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
    preprocess: bool = True,
) -> tuple[str, str]:
    """下载图片并编码为 base64

    Args:
        url: 图片 URL
        client: httpx 异步客户端
        timeout: 下载超时时间（秒）
        preprocess: 是否进行预处理（GIF 转 PNG 等）

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

    # 预处理（GIF → PNG 等）
    if preprocess:
        data, mime_type = preprocess_image(data)
    else:
        mime_type = detect_mime_type(data)

    b64 = encode_base64(data)
    return b64, mime_type


# ==================== 音频处理 ====================


AUDIO_NATIVE_MODELS = ["gpt-4o", "gemini"]


def model_supports_audio(model_name: str) -> bool:
    """检查模型是否原生支持音频输入"""
    name = model_name.lower()
    return any(k in name for k in AUDIO_NATIVE_MODELS)


def silk_to_wav(data: bytes, sample_rate: int = 24000) -> bytes | None:
    """SILK 音频转 WAV，失败返回 None"""
    try:
        import pysilk
    except ImportError:
        log.warning("pysilk 未安装，无法转码 SILK")
        return None
    try:
        return pysilk.decode(data, to_wav=True, sample_rate=sample_rate)
    except Exception as e:
        log.warning(f"SILK 转 WAV 失败: {e}")
        return None


def ffmpeg_to_wav(data: bytes) -> bytes | None:
    """用 ffmpeg 将任意音频转 WAV，失败返回 None"""
    import subprocess, tempfile, os
    tmp_in = tmp_out = None
    try:
        tmp_in = tempfile.NamedTemporaryFile(suffix=".audio", delete=False)
        tmp_in.write(data)
        tmp_in.close()
        tmp_out_path = tmp_in.name + ".wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in.name, "-ar", "24000", "-ac", "1", "-f", "wav", tmp_out_path],
            capture_output=True, timeout=15,
        )
        if result.returncode != 0:
            log.warning(f"ffmpeg 转码失败: {result.stderr[:200]}")
            return None
        wav = open(tmp_out_path, "rb").read()
        return wav
    except FileNotFoundError:
        log.warning("ffmpeg 未安装")
        return None
    except Exception as e:
        log.warning(f"ffmpeg 转码异常: {e}")
        return None
    finally:
        for p in [tmp_in and tmp_in.name, tmp_in and (tmp_in.name + ".wav")]:
            if p and os.path.exists(p):
                os.unlink(p)


def audio_to_wav(data: bytes) -> bytes | None:
    """任意音频转 WAV：SILK 头用 pysilk，其他用 ffmpeg"""
    if data[:6] in (b"#!SILK", b"\x02#!SIL"):
        wav = silk_to_wav(data)
        if wav:
            return wav
    return ffmpeg_to_wav(data)


async def download_audio(
    url: str,
    client: "httpx.AsyncClient | None" = None,
    timeout: float = 30.0,
) -> tuple[bytes, str]:
    """下载音频文件，返回 (原始字节, mime_type)"""
    import httpx

    if client is None:
        async with httpx.AsyncClient(timeout=timeout) as temp_client:
            resp = await temp_client.get(url)
            resp.raise_for_status()
            data = resp.content
    else:
        resp = await client.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.content

    mime = detect_mime_type(data) or "audio/amr"
    return data, mime


def read_local_audio(path: str) -> tuple[bytes, str]:
    """读取本地音频文件，返回 (原始字节, mime_type)"""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"音频文件不存在: {path}")

    data = p.read_bytes()
    # 先用魔数检测，再用扩展名
    mime = detect_mime_type(data)
    if not mime or mime.startswith("image/"):
        ext = p.suffix.lstrip(".").lower()
        mime = EXT_TO_MIME.get(ext, "audio/amr")
    return data, mime


# ==================== 音频时长与切分 ====================


def get_audio_duration(path: str) -> float | None:
    """用 ffprobe 获取音频时长（秒），失败返回 None"""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip()) if r.returncode == 0 else None
    except Exception:
        return None


def split_audio(path: str, max_seconds: int = 55) -> list[str]:
    """将音频按 max_seconds 切分，返回切片文件路径列表。

    失败时返回 [原路径]（不切分，尝试直接发）。
    """
    import subprocess
    from pathlib import Path

    p = Path(path)
    out_dir = p.parent
    stem, suffix = p.stem, p.suffix or ".mp3"
    pattern = str(out_dir / f"{stem}_part%03d{suffix}")

    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-f", "segment",
             "-segment_time", str(max_seconds), "-c", "copy", pattern],
            capture_output=True, timeout=120,
        )
        if r.returncode != 0:
            log.warning(f"音频切分失败: {r.stderr[:200]}")
            return [path]
    except Exception as e:
        log.warning(f"音频切分异常: {e}")
        return [path]

    parts = sorted(out_dir.glob(f"{stem}_part*{suffix}"))
    return [str(x) for x in parts] if parts else [path]
