"""
TTS MCP Server (with RVC voice conversion)

流程: 文本 → OpenAI TTS → RVC变声(manbo) → 保存文件 → 返回路径
如果 RVC 失败，回退到原始 TTS 音频。

环境变量:
- TTS_API_KEY: API 密钥
- TTS_API_BASE: API 基础地址 (默认 https://yunwu.ai/v1)
- TTS_MODEL: 模型 (默认 tts-1)
- TTS_VOICE: 声音 (默认 alloy)
- TTS_OUTPUT_DIR: 输出目录 (默认 workspace/tts)
- RVC_ENDPOINT: RVC 服务地址 (默认 http://localhost:6243/convert)
- RVC_MODEL: RVC 模型名 (默认 manbo.pth)
- RVC_INDEX: RVC 索引路径 (默认 logs/manbo/manbo.index)
- RVC_PITCH: 变调 (默认 0)
"""

import asyncio
import os
import time

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ============ 配置 ============
API_KEY = os.getenv("TTS_API_KEY", "")
API_BASE = os.getenv("TTS_API_BASE", "https://yunwu.ai/v1")
MODEL = os.getenv("TTS_MODEL", "tts-1")
VOICE = os.getenv("TTS_VOICE", "alloy")
TIMEOUT = int(os.getenv("TTS_TIMEOUT", "60"))
OUTPUT_DIR = os.getenv("TTS_OUTPUT_DIR", "workspace/tts")

RVC_ENDPOINT = "http://localhost:6243/convert"
RVC_MODEL = "manbo.pth"
RVC_INDEX = "logs/manbo/manbo.index"
RVC_PITCH = 0


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


async def do_tts(text: str) -> bytes | None:
    """调用 /v1/audio/speech，返回音频字节或 None"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{API_BASE}/audio/speech",
                json={"model": MODEL, "input": text, "voice": VOICE},
                headers={"Authorization": f"Bearer {API_KEY}"}
            )
            resp.raise_for_status()
            return resp.content
    except Exception as e:
        raise RuntimeError(f"TTS 失败: {e}")


def _log(msg: str):
    """写日志到文件，方便调试 MCP 子进程"""
    import datetime
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rvc_debug.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
    except Exception:
        pass


async def _rvc_request(audio_bytes: bytes, filename: str) -> bytes | None:
    """单次 RVC 请求"""
    async with httpx.AsyncClient(timeout=120, headers={"Connection": "close"}) as client:
        resp = await client.post(
            RVC_ENDPOINT,
            files={"audio": (filename, audio_bytes, "audio/mpeg")},
            data={
                "model_name": RVC_MODEL,
                "index_path": RVC_INDEX,
                "f0_up_key": RVC_PITCH,
                "f0_method": "rmvpe",
                "index_rate": 0.75,
            }
        )
        _log(f"RVC response: HTTP {resp.status_code}, {len(resp.content)} bytes")
        if resp.status_code == 200:
            return resp.content
        _log(f"RVC failed body: {resp.text[:200]}")
        return None


async def do_rvc(audio_bytes: bytes, filename: str = "input.mp3") -> bytes | None:
    """调用 RVC 服务变声，失败自动重试一次"""
    _log(f"do_rvc called: endpoint={RVC_ENDPOINT} model={RVC_MODEL} audio={len(audio_bytes)} bytes")
    for attempt in range(2):
        try:
            result = await _rvc_request(audio_bytes, filename)
            return result
        except Exception as e:
            _log(f"RVC attempt {attempt+1} exception: {type(e).__name__}: {e}")
            if attempt == 0:
                await asyncio.sleep(0.5)  # 等一下再重试
    return None


# ============ MCP Server ============

server = Server("tts")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="text_to_speech",
            description="将文本转换为语音文件（使用 manbo 音色）。返回生成的音频文件路径，可通过 send_message(record=路径) 发送。",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "要转换为语音的文本内容"
                    }
                },
                "required": ["text"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "text_to_speech":
        return [TextContent(type="text", text=f"未知工具: {name}")]

    text = arguments.get("text", "").strip()
    if not text:
        return [TextContent(type="text", text="错误: 文本不能为空")]

    # Step 1: TTS
    try:
        tts_audio = await do_tts(text)
    except RuntimeError as e:
        return [TextContent(type="text", text=f"语音生成失败: {e}")]

    # Step 2: RVC（失败则回退）
    rvc_audio = await do_rvc(tts_audio)

    if rvc_audio:
        audio_data = rvc_audio
        ext = "wav"
    else:
        audio_data = tts_audio
        ext = "mp3"

    # 保存文件
    ensure_output_dir()
    filepath = os.path.join(OUTPUT_DIR, f"tts_{int(time.time())}.{ext}")
    with open(filepath, "wb") as f:
        f.write(audio_data)

    abs_path = os.path.abspath(filepath)
    return [TextContent(type="text", text=f"语音已生成: {abs_path}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
