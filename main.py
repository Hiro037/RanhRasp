"""
Entry point: run both Telegram and VK bots concurrently.
"""

import asyncio
import threading
from adapters.telegram_bot import start_telegram_bot
#from adapters.vk_bot import start_vk_bot

def run_vk_in_thread():
    """Run VK bot in a separate thread with its own event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    #loop.run_until_complete(start_vk_bot())

async def main():
    # Uncomment to create tables (run once)
    # from core.database import engine
    # from core.models import Base
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    print("Starting bots...")

    #vk_thread = threading.Thread(target=run_vk_in_thread, daemon=True)
    #vk_thread.start()

    # Telegram бот в основном event loop
    await start_telegram_bot()

if __name__ == "__main__":
    asyncio.run(main())