"""
Gemini Image Generation MCP Server

使用 Gemini 2.5 Flash Image 进行图片生成和编辑的 MCP 服务器。
支持:
- 纯文本生成图片
- 编辑已有图片（支持 base64 或 URL）
"""

import asyncio
import base64
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent

# 配置
API_ENDPOINT = os.getenv("GEMINI_API_ENDPOINT", "http://yunwu.ai/v1/chat/completions")
API_KEY = os.getenv("GEMINI_API_KEY", "sk-WhXRtQ6llImK1NPP0KwXWZpbfDAjJzFkp2ZGawcf3MX9NhG6")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3-pro-image")
TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "120"))

# 图片输出目录
OUTPUT_DIR = Path(os.getenv("GEMINI_OUTPUT_DIR", "E:/dev/my/qqagent/workspace/gemini-image"))


def save_image_to_file(b64_data: str, mime_type: str) -> str:
    """保存 base64 图片到文件，返回文件路径"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 根据 mime 类型确定扩展名
    ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
    ext = ext_map.get(mime_type, ".png")

    # 生成文件名
    timestamp = int(time.time() * 1000)
    filename = f"gemini_{timestamp}{ext}"
    filepath = OUTPUT_DIR / filename

    # 保存文件
    img_bytes = base64.b64decode(b64_data)
    filepath.write_bytes(img_bytes)

    return str(filepath)

# System Prompts
GENERATE_SYSTEM_PROMPT = """You are an expert image generation assistant. Your task is to AUTOMATICALLY ENHANCE any simple user request into a professional, detailed image.

**Your Process:**
1. Take the user's simple request (e.g., "a cat")
2. Internally expand it into a rich, detailed visual description
3. Generate a high-quality, visually stunning image

**Auto-Enhancement Rules:**
- Add appropriate lighting (golden hour, soft studio light, dramatic shadows, etc.)
- Choose the best composition and camera angle for the subject
- Apply a suitable art style if not specified (photorealistic, illustration, anime, etc.)
- Include environmental details and atmospheric elements
- Ensure professional color harmony and visual balance

**Quality Standards:**
- Sharp, high-resolution output
- Professional composition with proper rule of thirds
- Anatomically correct for living subjects

**CRITICAL RESTRICTIONS:**
- DO NOT generate any Chinese text or characters in the image
- DO NOT add text bubbles, speech bubbles, or dialogue boxes
- DO NOT include any watermarks or signatures

**Important:** Just generate the image directly. Do not ask for clarification."""

EDIT_SYSTEM_PROMPT = """You are an expert image editing assistant. The user will provide an image along with editing instructions.

**Your Task:**
- Carefully analyze the provided image
- Apply the user's requested modifications precisely
- Maintain the original image's quality and style unless asked to change it
- Preserve elements not mentioned in the edit request

**Editing Capabilities:**
- Style transfer (e.g., "make it look like an oil painting")
- Add/remove elements (e.g., "add wings", "remove the background")
- Color adjustments (e.g., "make it warmer", "convert to black and white")
- Enhance quality (e.g., "make it sharper", "increase details")
- Transform subjects (e.g., "make them smile", "change hair color")

**CRITICAL RESTRICTIONS:**
- DO NOT generate any Chinese text or characters in the image
- DO NOT add text bubbles, speech bubbles, or dialogue boxes
- DO NOT include any watermarks or signatures

**Important:** Apply the edit directly and output the modified image."""


def extract_base64_image(content: str) -> str | None:
    """从 Markdown 图片语法或纯 data URL 中提取 base64 数据"""
    # 匹配 ![...](data:image/xxx;base64,...) 格式
    match = re.search(r'!\[.*?\]\((data:image/[^;]+;base64,[^)]+)\)', content)
    if match:
        return match.group(1)
    # 也尝试匹配纯 data URL
    data_url_match = re.search(r'(data:image/[^;]+;base64,[^\s"\']+)', content)
    if data_url_match:
        return data_url_match.group(1)
    return None


async def download_image_as_base64(url: str) -> str | None:
    """下载图片并转换为 base64 data URL

    支持:
    - data:image/xxx;base64,... 格式
    - 本地文件路径 (如 E:/xxx/xxx.png 或 /path/to/image.png)
    - HTTP/HTTPS URL
    """
    # 已经是 data URL
    if url.startswith('data:image/'):
        return url

    # 本地文件路径
    local_path = Path(url)
    if local_path.exists() and local_path.is_file():
        try:
            img_bytes = local_path.read_bytes()
            # 根据扩展名猜测 MIME 类型
            ext = local_path.suffix.lower()
            mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
            mime_type = mime_map.get(ext, 'image/png')
            b64 = base64.b64encode(img_bytes).decode('utf-8')
            return f"data:{mime_type};base64,{b64}"
        except Exception as e:
            print(f"Failed to read local image: {e}")
            return None

    # HTTP URL
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get('content-type', 'image/png')
            if 'jpeg' in content_type or 'jpg' in content_type:
                mime_type = 'image/jpeg'
            elif 'gif' in content_type:
                mime_type = 'image/gif'
            elif 'webp' in content_type:
                mime_type = 'image/webp'
            else:
                mime_type = 'image/png'

            b64 = base64.b64encode(response.content).decode('utf-8')
            return f"data:{mime_type};base64,{b64}"
    except Exception as e:
        print(f"Failed to download image: {e}")
        return None


async def generate_image(prompt: str, image_url: str | None = None) -> dict[str, Any]:
    """
    调用 Gemini API 生成或编辑图片
    
    Args:
        prompt: 图片描述或编辑指令
        image_url: 可选，要编辑的图片 URL 或 base64
    
    Returns:
        包含结果的字典 {"success": bool, "image": str | None, "text": str | None, "error": str | None}
    """
    try:
        if image_url:
            # 编辑模式
            system_prompt = EDIT_SYSTEM_PROMPT
            
            # 确保是 base64 格式
            base64_image = await download_image_as_base64(image_url)
            if not base64_image:
                return {"success": False, "error": "无法获取或转换图片"}
            
            user_content = [
                {"type": "image_url", "image_url": {"url": base64_image}},
                {"type": "text", "text": f"Please edit this image: {prompt}"}
            ]
        else:
            # 生成模式
            system_prompt = GENERATE_SYSTEM_PROMPT
            user_content = f"Please draw: {prompt}"
        
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                API_ENDPOINT,
                json=payload,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            data = response.json()
        
        if data.get("choices") and data["choices"][0].get("message", {}).get("content"):
            content = data["choices"][0]["message"]["content"]
            
            # 尝试提取 base64 图片
            base64_img = extract_base64_image(content)
            if base64_img:
                return {"success": True, "image": base64_img, "text": None}
            else:
                return {"success": True, "image": None, "text": content}
        else:
            return {"success": False, "error": "API 返回了无法识别的数据结构"}
    
    except httpx.HTTPStatusError as e:
        return {"success": False, "error": f"HTTP 错误: {e.response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============ MCP Server ============

server = Server("gemini-image")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="generate_image",
            description="""使用 Gemini 2.5 Flash 生成或编辑图片。

功能:
- 纯文本生成: 输入描述，AI 自动增强并生成高质量图片
- 图片编辑: 提供图片路径/URL + 编辑指令，对已有图片进行修改

支持的编辑操作:
- 风格转换 (油画、动漫、写实等)
- 添加/移除元素
- 调整颜色、光影
- 局部修改 (表情、背景等)

可同时接收最多 3 张图片进行编辑/融合。
生成的图片会保存到本地并返回路径。""",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "图片描述或编辑指令。生成: 'a cyberpunk city at night'; 编辑: 'add sunglasses to the person'"
                    },
                    "images": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选。图片本地路径或 URL 列表 (最多3张)。提供图片时进入编辑模式。",
                        "maxItems": 3
                    }
                },
                "required": ["prompt"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent]:
    """处理工具调用"""

    if name == "generate_image":
        prompt = arguments.get("prompt", "")
        images = arguments.get("images", [])

        # 如果有图片，取第一张作为主要编辑对象
        image_url = images[0] if images else None

        result = await generate_image(prompt, image_url)

        if result["success"]:
            if result["image"]:
                img_data = result["image"]
                if img_data.startswith("data:"):
                    match = re.match(r'data:([^;]+);base64,(.+)', img_data)
                    if match:
                        mime_type, b64_data = match.groups()
                        # 保存到文件并返回路径
                        try:
                            filepath = save_image_to_file(b64_data, mime_type)
                            return [TextContent(type="text", text=f"图片已生成，路径: {filepath}")]
                        except Exception as e:
                            return [TextContent(type="text", text=f"保存图片失败: {e}")]

                return [TextContent(type="text", text=f"生成的图片格式无法解析")]
            else:
                return [TextContent(type="text", text=result["text"] or "生成完成，但未返回图片")]
        else:
            return [TextContent(type="text", text=f"生成失败: {result['error']}")]

    else:
        return [TextContent(type="text", text=f"未知工具: {name}")]


async def main():
    """运行 MCP 服务器"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
