#!/usr/bin/env python3
"""Channel ID lookup -- search for channel_post in recent getUpdates."""
import os, sys, asyncio
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "heysquid", ".env"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def main():
    request = HTTPXRequest(connect_timeout=10.0, read_timeout=15.0)
    bot = Bot(token=BOT_TOKEN, request=request)

    # Method 1: Find channel_post in getUpdates
    # Since listener only consumes messages, channel_posts may remain
    try:
        updates = await bot.get_updates(
            timeout=5,
            allowed_updates=["channel_post"]
        )
        for u in updates:
            if u.channel_post:
                ch = u.channel_post.chat
                print(f"[Found] Channel name: {ch.title}")
                print(f"[Found] Channel ID: {ch.id}")
                print(f"\nAdd to .env:")
                print(f"TELEGRAM_AGENTBOX_CHANNEL_ID={ch.id}")
                return
    except Exception as e:
        print(f"getUpdates failed: {e}")

    # Method 2: Try sending a test message to channel (requires channel username)
    print("Could not find channel_post.")
    print()
    print("Alternative: Provide the channel username or invite link.")
    print("Or add @userinfobot to the channel to get the channel ID.")
    print()
    print("Easiest method:")
    print("1. Add @RawDataBot to the channel on Telegram")
    print("2. Send a message in the channel and the bot will show the channel ID")
    print("3. Remove @RawDataBot after confirming")

asyncio.run(main())
