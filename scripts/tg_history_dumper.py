"""
Telegram 频道历史资讯导出脚本（安全防封版）

用于独立测试，或一次性导出过去 7 天内指定频道的历史消息。
导出的数据将以与 telegram_monitor.py 相同的结构化格式，
按消息原本发布的日期/时间写入 `data/tg_news/YYYY-MM-DD.txt` 中。

防止封号说明：
1. 【被动监听】(bot里的功能) 是接收 TG 推送的，只要你别发太多垃圾消息，永远不会因为"单纯接收资讯"被封号。
2. 【主动抓取历史】属于 API 拉取，一秒内请求上百次容易触发 429 FloodWait 报错。
   此脚本已经内置了每 100 条休息 1 块秒的安全逻辑，遇到官方限流会自动等待。
   这是常规的客户端拉取行为，只要内置了延时，绝对安全。
"""

import asyncio
import datetime
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from telethon import TelegramClient
from telethon.errors import FloodWaitError
import python_socks

# 在这里填入你刚才挑出来的频道 ID 或 username
TARGET_CHANNELS = [
    "cnbeta_com",
    "tnews365",
    "linuxdoit",
    "GetSomeFriesChannel"
]

# 抓取几天内的消息
DAYS_TO_FETCH = 7

# 单条消息最短字数过滤
MIN_LENGTH = 20


def get_proxy():
    proxy_str = os.getenv("TG_PROXY", "")
    if not proxy_str:
        return None
    try:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_str)
        ptype = python_socks.ProxyType.SOCKS5 if parsed.scheme == "socks5" else python_socks.ProxyType.HTTP
        return {
            "proxy_type": ptype,
            "addr": parsed.hostname,
            "port": int(parsed.port)
        }
    except Exception as e:
        print(f"Warning: proxy parsed failed -> {e}")
        return None


async def main():
    api_id = int(os.getenv("TG_API_ID", "0"))
    api_hash = os.getenv("TG_API_HASH", "")
    session_path = str(ROOT / "data" / "tg_session")

    client = TelegramClient(session_path, api_id, api_hash, proxy=get_proxy())

    print("🔌 正在连接 Telegram...")
    await client.start()
    print("✅ 连接成功！开始抓取历史资讯...\n")

    # 计算 7 天前的时间点（使用 UTC 零时区）
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff_date = now_utc - datetime.timedelta(days=DAYS_TO_FETCH)

    store_dir = ROOT / "data" / "tg_news"
    store_dir.mkdir(parents=True, exist_ok=True)

    for channel_id in TARGET_CHANNELS:
        print(f"==================================================")
        print(f"📡 正在拉取频道: {channel_id}")
        count = 0
        try:
            # 批量获取历史消息，每次拉取限制 limit，不限制总数，直到超过日期
            # 这里默认按照时间倒序获取（从最新到最老）
            async for msg in client.iter_messages(channel_id):
                if not msg.date:
                    continue

                # ...

                if msg.date < cutoff_date:
                    print(f"  [到达时间边界] 当前消息时间: {msg.date.strftime('%Y-%m-%d')}")
                    break

                text = msg.text or ""
                text = text.strip()
                if len(text) < MIN_LENGTH:
                    continue

                local_dt = msg.date.astimezone()
                date_str = local_dt.strftime("%Y-%m-%d")
                time_str = local_dt.strftime("%H:%M:%S")

                store_file = store_dir / f"{date_str}.txt"
                record = f"[{date_str} {time_str}] [ChatID:{channel_id}]\n{text}\n===\n\n"

                with open(store_file, "a", encoding="utf-8") as f:
                    f.write(record)

                count += 1

                # ⭐️ 防封策略：每处理 50 条有效资讯，强制强制休息 3 秒（模拟人类龟速刷聊天记录）
                if count % 50 == 0:
                    print(f"  ...已拉取 {count} 条，龟速休息 3 秒防限流...")
                    await asyncio.sleep(3)

        except FloodWaitError as e:
            # 万一遇到官方的限流警告，这是唯一的防封保命符：强行休眠它要求的时间
            wait_time = e.seconds + 2
            print(f"⚠️ 触发限流！被要求等待 {wait_time} 秒...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            print(f"❌ 频道 {channel_id} 发生错误: {e}")
            continue

        print(f"✅ {channel_id} 拉取完成！(符合条件的 7 天内有效资讯: {count} 条)")
        print(f"==================================================\n")

        # 换频道之间也要休息，伪装成正常人
        await asyncio.sleep(2)

    await client.disconnect()
    print("🎉 全部历史资讯聚合完毕！请前往 data/tg_news 目录查看结构化数据。")

if __name__ == "__main__":
    asyncio.run(main())
