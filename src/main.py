"""
LangGraph QQ Agent - 主程序入口
"""

import asyncio

from src.bot import BotApp


async def main():
    app = BotApp()
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
