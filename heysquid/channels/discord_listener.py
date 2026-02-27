"""
heysquid.channels.discord_listener — Discord Gateway listener.

Responsibilities:
- Receive Discord messages (Gateway Bot — MESSAGE_CONTENT Intent required!)
- Download attachments
- Save to messages.json in unified schema
- Broadcast to other channels (full sync)
- Call trigger_executor()

Usage:
    python -m heysquid.channels.discord_listener
"""

import os
import re
import signal
import sys
import time
import asyncio
from datetime import datetime

from dotenv import load_dotenv

from heysquid.core.config import get_env_path, DATA_DIR_STR
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ALLOWED_USERS = [u.strip() for u in os.getenv("DISCORD_ALLOWED_USERS", "").split(",") if u.strip()]
ALLOWED_CHANNELS = [c.strip() for c in os.getenv("DISCORD_ALLOWED_CHANNELS", "").split(",") if c.strip()]

# Stop keywords
STOP_KEYWORDS = {"멈춰", "스탑", "중단", "/stop", "잠깐만", "그만", "취소", "stop"}

# File download path
DATA_DIR = DATA_DIR_STR
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")


def _download_discord_attachment_sync(url, filename):
    """Download Discord attachment (synchronous — runs in thread)"""
    import requests

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    ts = int(time.time())
    local_path = os.path.join(DOWNLOAD_DIR, f"discord_{ts}_{safe_name}")

    try:
        # H-8 style: Streaming download
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path
    except Exception as e:
        print(f"[DISCORD] File download failed: {e}")
        return None


async def _download_discord_attachment(attachment):
    """Download Discord attachment (H-3: async wrapper — prevent event loop blocking)"""
    return await asyncio.to_thread(
        _download_discord_attachment_sync, attachment.url, attachment.filename
    )


def main():
    """Discord listener main — Gateway Bot"""
    if not BOT_TOKEN:
        print("[DISCORD] DISCORD_BOT_TOKEN not set")
        print("   Set DISCORD_BOT_TOKEN in .env.")
        sys.exit(1)

    # Import discord.py as discord_lib (D4 — avoid name collision)
    import discord as discord_lib

    intents = discord_lib.Intents.default()
    intents.message_content = True  # Required! (D3)
    client = discord_lib.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[DISCORD] {client.user} connected (Gateway)")
        print(f"[DISCORD] Allowed users: {ALLOWED_USERS or 'all'}")
        if ALLOWED_CHANNELS:
            print(f"[DISCORD] Allowed channels: {ALLOWED_CHANNELS}")

    @client.event
    async def on_message(message):
        # 1. Ignore bot's own messages (echo loop prevention)
        if message.author.bot:
            return

        user_id = str(message.author.id)
        channel_id = str(message.channel.id)

        # 2. Allowed user check
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            return

        # 3. Allowed channel check (if configured)
        if ALLOWED_CHANNELS and channel_id not in ALLOWED_CHANNELS:
            return

        text = message.content or ""

        # D3: MESSAGE_CONTENT Intent warning
        if not text and not message.attachments:
            print("[DISCORD] Empty message — MESSAGE_CONTENT Intent may be disabled!")
            return

        # message_id: Attach channel prefix (P1)
        msg_id = f"discord_{message.id}"

        # 4. Stop command check
        text_lower = text.lower().strip()
        if text_lower in STOP_KEYWORDS:
            await _handle_stop(message, msg_id)
            return

        # 5. Download attachments (H-3: await for non-blocking event loop)
        files = []
        for attachment in message.attachments:
            local_path = await _download_discord_attachment(attachment)
            if local_path:
                file_type = "photo" if attachment.content_type and attachment.content_type.startswith("image/") else "document"
                files.append({
                    "path": local_path,
                    "name": attachment.filename,
                    "size": attachment.size,
                    "type": file_type,
                })

        # 6. User name
        user_name = message.author.display_name or str(message.author)

        # 7. Convert to unified schema
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {
            "message_id": msg_id,
            "channel": "discord",
            "chat_id": channel_id,
            "text": text,
            "type": "user",
            "first_name": user_name,
            "timestamp": now,
            "processed": False,
            "files": files if files else [],
        }

        # 8. Save to messages.json (flock atomic, H-3: to_thread for non-blocking)
        from heysquid.channels._msg_store import load_and_modify

        def _append_msg(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        await asyncio.to_thread(load_and_modify, _append_msg)

        print(f"[DISCORD] Message saved: {user_name}: {text[:50]}...")

        # 9. Acknowledgment reaction (T1)
        try:
            await message.add_reaction("✅")
        except Exception:
            pass

        # 10. Broadcast to other channels (full sync, H-3: to_thread)
        try:
            from heysquid.channels._router import broadcast_user_message, broadcast_files
            if text:
                await asyncio.to_thread(
                    broadcast_user_message, text,
                    source_channel="discord", sender_name=user_name,
                )
            if files:
                local_paths = [f["path"] for f in files if f.get("path")]
                if local_paths:
                    await asyncio.to_thread(
                        broadcast_files, local_paths,
                        exclude_channels={"discord"},
                    )
        except Exception as e:
            print(f"[DISCORD] Broadcast failed (does not affect Discord processing): {e}")

        # 11. trigger_executor() (H-3: to_thread)
        try:
            from heysquid.channels._base import trigger_executor
            await asyncio.to_thread(trigger_executor)
        except Exception as e:
            print(f"[DISCORD] trigger_executor failed: {e}")

    async def _handle_stop(message, msg_id):
        """Handle stop command"""
        import subprocess

        print(f"[DISCORD] Stop command received: {message.content}")

        # Save message
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {
            "message_id": msg_id,
            "channel": "discord",
            "chat_id": str(message.channel.id),
            "text": message.content,
            "type": "user",
            "first_name": message.author.display_name,
            "timestamp": now,
            "processed": True,
        }
        from heysquid.channels._msg_store import load_and_modify

        def _append_msg(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        await asyncio.to_thread(load_and_modify, _append_msg)

        # Kill Claude process (H-3: subprocess doesn't need to_thread — fast enough)
        try:
            result = subprocess.run(
                ["pgrep", "-f", "claude.*append-system-prompt-file"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    if pid.strip():
                        subprocess.run(["kill", "-TERM", pid.strip()])
                print(f"[DISCORD] Claude process stopped: {pids}")

                # Create interrupted file
                from heysquid.core._working_lock import check_working_lock
                lock_info = check_working_lock()
                if lock_info:
                    from heysquid.paths import INTERRUPTED_FILE
                    import json
                    import tempfile
                    interrupted_data = {
                        "reason": "user_stop",
                        "stopped_at": now,
                        "channel": "discord",
                        "previous_work": lock_info,
                    }
                    # C-6: Atomic write (tmp + fsync + rename)
                    fd, tmp = tempfile.mkstemp(
                        dir=os.path.dirname(INTERRUPTED_FILE), suffix=".tmp"
                    )
                    with os.fdopen(fd, "w") as f:
                        json.dump(interrupted_data, f, ensure_ascii=False, indent=2)
                        f.flush()
                        os.fsync(f.fileno())
                    os.rename(tmp, INTERRUPTED_FILE)

                await message.channel.send("Task stopped.")
            else:
                await message.channel.send("No task is currently running.")
        except Exception as e:
            print(f"[DISCORD] Stop handling failed: {e}")

    # M-8: SIGTERM handler — graceful shutdown via discord.py close()
    def shutdown(signum, frame):
        print(f"\n[DISCORD] Signal {signum} received — initiating graceful shutdown")
        asyncio.ensure_future(client.close())

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("[DISCORD] Gateway listener starting...")
    client.run(BOT_TOKEN)  # Blocking


if __name__ == "__main__":
    main()
