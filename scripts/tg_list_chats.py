"""
列出当前 TG 账号加入的所有群组和频道
用法: python scripts/tg_list_chats.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User


async def main():
    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    session_path = str(ROOT / "data" / "tg_session")

    proxy_str = os.getenv("TG_PROXY", "")
    proxy = None
    if proxy_str:
        from urllib.parse import urlparse
        import python_socks
        parsed = urlparse(proxy_str)
        ptype = python_socks.ProxyType.SOCKS5 if parsed.scheme == "socks5" else python_socks.ProxyType.HTTP
        proxy = {
            "proxy_type": ptype,
            "addr": parsed.hostname,
            "port": parsed.port
        }

    client = TelegramClient(session_path, api_id, api_hash, proxy=proxy)
    await client.start()

    print("=" * 70)
    print("  你的 TG 账号加入的群组和频道")
    print("=" * 70)
    print()

    channels = []
    groups = []
    users = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, Channel):
            if entity.broadcast:
                channels.append(dialog)
            else:
                groups.append(dialog)
        elif isinstance(entity, Chat):
            groups.append(dialog)
        elif isinstance(entity, User):
            users.append(dialog)

    # 频道（适合监听资讯）
    if channels:
        print(f"[频道] 共 {len(channels)} 个 (最适合监听资讯)")
        print("-" * 70)
        for d in channels:
            e = d.entity
            username = f"@{e.username}" if e.username else "(无 username)"
            print(f"  ID: {d.entity.id:>15}  |  {username:<25}  |  {d.name}")
        print()

    # 群组
    if groups:
        print(f"[群组] 共 {len(groups)} 个")
        print("-" * 70)
        for d in groups:
            e = d.entity
            username = f"@{e.username}" if hasattr(e, 'username') and e.username else "(无 username)"
            print(f"  ID: {d.entity.id:>15}  |  {username:<25}  |  {d.name}")
        print()

    print(f"[私聊] 共 {len(users)} 个 (不列出)")
    print()
    print("=" * 70)
    print("提示: 把频道/群组的 username 或 ID 填入 config.yaml 的")
    print("      telegram.monitor.groups 即可开始监听")
    print("=" * 70)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
