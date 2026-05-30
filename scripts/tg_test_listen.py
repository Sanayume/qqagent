"""
TG 监听诊断脚本 — 独立测试 Telethon 能否收到频道消息

使用方法: 先 Ctrl+C 停掉主程序，然后运行:
    python scripts/tg_test_listen.py

会监听 30 秒钟并打印所有收到的消息。Ctrl+C 退出。
"""
import asyncio
import os
import sys

# 加载 .env
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from telethon import TelegramClient, events

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
PHONE = os.getenv("TG_PHONE", "")

# 代理
PROXY = None
proxy_str = os.getenv("TG_PROXY", "")
if proxy_str:
    from urllib.parse import urlparse
    import python_socks
    parsed = urlparse(proxy_str)
    PROXY = {
        "proxy_type": python_socks.ProxyType.SOCKS5 if parsed.scheme == "socks5" else python_socks.ProxyType.HTTP,
        "addr": parsed.hostname,
        "port": int(parsed.port),
    }
    print(f"🔌 使用代理: {proxy_str}")

# 要监听的频道列表（和 config.yaml 保持一致）
WATCH = ["cnbeta_com", "tnews365", "linuxdoit", "GetSomeFriesChannel", "CE_Observe"]

async def main():
    print(f"🔧 API_ID={API_ID}, PHONE={PHONE}")
    client = TelegramClient("data/tg_session_test", API_ID, API_HASH, proxy=PROXY)

    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"✅ 已登录: @{me.username or me.id}")

    # 解析频道
    watch_ids = {}
    for g in WATCH:
        try:
            entity = await client.get_entity(g)
            watch_ids[entity.id] = g
            print(f"  📡 解析成功: {g} → id={entity.id}")
        except Exception as e:
            print(f"  ❌ 解析失败: {g}: {e}")

    print(f"\n🎯 正在监听 {len(watch_ids)} 个频道，等待消息... (Ctrl+C 退出)\n")

    msg_count = 0

    @client.on(events.NewMessage())
    async def handler(event):
        nonlocal msg_count
        chat_id = event.chat_id
        text = getattr(event.message, "text", "") or ""
        chat_name = watch_ids.get(chat_id, None)

        if chat_name:
            msg_count += 1
            preview = text[:80].replace("\n", " ")
            print(f"  ✅ [{chat_name}] (id={chat_id}): {preview}...")
        else:
            # 不在监听列表中的消息也打印一下，看看有没有消息流经过
            preview = text[:50].replace("\n", " ") if text else "[非文本]"
            print(f"  ⚪ [未监听 id={chat_id}]: {preview}")

    print("--- 开始接收 ---")

    # 运行直到断开
    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print(f"\n\n📊 总计收到 {msg_count} 条来自监听频道的消息")
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
