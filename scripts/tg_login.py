"""
Telegram 首次登录授权脚本

仅需运行一次，完成后会在 data/ 目录生成 session 文件，
之后主程序可自动免密登录。

用法:
    python scripts/tg_login.py

需要在 .env 中配置：
    TG_API_ID=xxxxx
    TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TG_PHONE=+8613800138000
"""

import asyncio
import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

try:
    from telethon import TelegramClient
except ImportError:
    print("[X] 未安装 telethon，请先运行: pip install telethon")
    sys.exit(1)


async def main():
    api_id_str = os.getenv("TG_API_ID", "")
    api_hash = os.getenv("TG_API_HASH", "")
    phone = os.getenv("TG_PHONE", "")

    if not api_id_str or not api_hash:
        print("[X] 请在 .env 中配置 TG_API_ID 和 TG_API_HASH")
        sys.exit(1)

    api_id = int(api_id_str)
    session_path = str(ROOT / "data" / "tg_session")
    Path(session_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] 账号: {phone or '（将在授权时输入）'}")
    print(f"[*] Session 文件: {session_path}.session")
    print()

    client = TelegramClient(session_path, api_id, api_hash)

    await client.start(phone=phone or None)

    me = await client.get_me()
    print()
    print(f"[OK] 登录成功!")
    print(f"     用户名: @{me.username or '(无用户名)'}")
    print(f"     ID:     {me.id}")
    print(f"     姓名:   {me.first_name} {me.last_name or ''}")
    print()
    print(f"Session 文件已保存，之后主程序将自动免密登录。")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
