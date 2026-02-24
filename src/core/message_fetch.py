"""消息获取辅助函数

从 bot.py 提取的顶层函数：获取引用消息、合并转发、下载图片。
"""

import asyncio
import time

from src.adapters.onebot import OneBotAdapter
from src.core.onebot import parse_segments, make_text_description, get_file_descriptions
from src.core.media import download_and_encode
from src.core.exceptions import DownloadError, MediaError, OneBotError
from src.utils.logger import log


async def fetch_reply_context(adapter: OneBotAdapter, reply_id: int) -> str | None:
    """获取引用消息的上下文描述"""
    try:
        result = await adapter.get_msg(reply_id)
        if result.get("status") != "ok":
            log.debug(f"获取引用消息失败: {result.get('msg', 'unknown')}")
            return None

        data = result.get("data", {})
        segments = data.get("message", [])
        parsed = parse_segments(segments)
        sender = data.get("sender", {}).get("nickname", "某人")

        if parsed.has_files():
            file_descs = get_file_descriptions(parsed)
            context = f"{sender}: {' '.join(file_descs)}"
            if parsed.text:
                context += f" {parsed.text}"
        else:
            context = f"{sender}: {make_text_description(parsed)}"

        log.debug(f"Reply context: {context}")
        return context

    except asyncio.TimeoutError:
        log.warning("获取引用消息超时")
        return None
    except OneBotError as e:
        log.warning(f"获取引用消息失败: {e}")
        return None
    except Exception as e:
        log.warning(f"获取引用消息异常: {type(e).__name__}: {e}")
        return None


async def fetch_forward_content(adapter: OneBotAdapter, forward_id: str, max_nodes: int = 50) -> tuple[str | None, list[str]]:
    """获取合并转发消息的内容和图片"""
    log.debug(f"Fetching forward message, id={forward_id}")
    try:
        result = await adapter.get_forward_msg(forward_id)
        log.debug(f"Forward API result status: {result.get('status')}, retcode: {result.get('retcode')}")

        if result.get("status") != "ok":
            log.warning(f"获取转发消息失败: {result.get('msg', result.get('message', 'Unknown'))}")
            return None, []

        data = result.get("data", {})
        nodes = data.get("message", data.get("messages", []))
        log.debug(f"Forward message has {len(nodes)} nodes")

        if not nodes:
            log.warning("转发消息为空")
            return None, []

        summaries = []
        all_image_urls = []

        for i, node in enumerate(nodes[:max_nodes]):
            node_type = node.get("type", "unknown")

            if node_type == "node":
                node_data = node.get("data", {})
            else:
                node_data = node

            nickname = node_data.get("nickname", node_data.get("sender", {}).get("nickname", "某人"))
            content = node_data.get("content", node_data.get("message", ""))

            if isinstance(content, list):
                node_parsed = parse_segments(content)
                if node_parsed.image_urls:
                    all_image_urls.extend(node_parsed.image_urls)
                content = make_text_description(node_parsed)
            elif isinstance(content, str):
                content = content.strip()
            else:
                content = str(content)[:200] if content else ""

            if nickname or content:
                summaries.append(f"{nickname}: {content[:200]}")

        if len(nodes) > max_nodes:
            summaries.append(f"...还有 {len(nodes) - max_nodes} 条消息")

        summary = "\n".join(summaries)
        log.info(f"转发消息: {len(nodes)} 条, {len(all_image_urls)} 张图片")
        return summary, all_image_urls

    except asyncio.TimeoutError:
        log.warning("获取转发消息超时")
        return None, []
    except OneBotError as e:
        log.warning(f"获取转发消息失败: {e}")
        return None, []
    except Exception as e:
        log.warning(f"获取转发消息异常: {type(e).__name__}: {e}")
        return None, []


async def download_message_images(image_urls: list[str], max_count: int = 3) -> tuple[list[tuple[str, str]], list[str]]:
    """下载消息中的图片"""
    import base64 as b64_module
    from pathlib import Path

    images = []
    image_paths = []
    failed_count = 0

    save_dir = Path("workspace/images")
    save_dir.mkdir(parents=True, exist_ok=True)

    for url in image_urls[:max_count]:
        try:
            b64, mime = await download_and_encode(url)
            images.append((b64, mime))

            ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}
            ext = ext_map.get(mime, ".png")
            timestamp = int(time.time() * 1000)
            filename = f"img_{timestamp}{ext}"
            filepath = save_dir / filename

            img_bytes = b64_module.b64decode(b64)
            filepath.write_bytes(img_bytes)
            image_paths.append(str(filepath.absolute()))

            log.debug(f"下载图片成功: {mime}, 保存到 {filepath}")
        except asyncio.TimeoutError:
            failed_count += 1
            log.warning(f"下载图片超时: {url[:50]}...")
        except DownloadError as e:
            failed_count += 1
            log.warning(f"下载图片失败: {e}")
        except MediaError as e:
            failed_count += 1
            log.warning(f"图片处理失败: {e}")
        except Exception as e:
            failed_count += 1
            log.warning(f"下载图片异常: {type(e).__name__}: {e}")

    if failed_count > 0:
        log.info(f"图片下载: {len(images)} 成功, {failed_count} 失败")

    return images, image_paths
