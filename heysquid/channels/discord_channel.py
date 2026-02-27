"""
heysquid.channels.discord_channel — Discord sender (REST API-based).

Warning: Named discord_channel.py, not discord.py (D4 — avoid library name collision)

Responsibilities:
- Send PM responses and broadcast messages to Discord
- Auto-split at 2000 char limit (D1)
- File upload (25MB limit, D2)
- REST API only, no Gateway connection (HTTP is sufficient for sending)

Usage:
    from heysquid.channels.discord_channel import send_message_sync, send_files_sync
"""

import os
import time

import requests
from dotenv import load_dotenv

from ..config import get_env_path

load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
API_BASE = "https://discord.com/api/v10"

# Session reuse
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "Authorization": f"Bot {BOT_TOKEN}",
        })
    return _session


def _send_chunk(channel_id, text):
    """Send a single message (REST API)"""
    session = _get_session()
    resp = session.post(
        f"{API_BASE}/channels/{channel_id}/messages",
        json={"content": text},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    return True


def send_message_sync(channel_id, text, _save=True, **kwargs):
    """Discord message send (synchronous).

    Args:
        channel_id: Discord channel ID (snowflake string)
        text: Text to send
        _save: Whether to save to messages.json
    """
    if not BOT_TOKEN:
        print("[DISCORD] BOT_TOKEN not set — skipping send")
        return False

    try:
        # Auto-split at 2000 char limit (D1)
        if len(text) <= 1800:
            _send_chunk(channel_id, text)
        else:
            chunks = [text[i:i+1800] for i in range(0, len(text), 1800)]
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(0.3)
                _send_chunk(channel_id, chunk)

        if _save:
            try:
                from ._msg_store import save_bot_response
                msg_id = f"bot_progress_{int(time.time() * 1000)}"
                save_bot_response(channel_id, text, [msg_id], channel="discord")
            except Exception as e:
                print(f"[DISCORD] Failed to save bot response: {e}")

        return True

    except requests.exceptions.HTTPError as e:
        # Rate limiting
        if e.response is not None and e.response.status_code == 429:
            retry_after = e.response.json().get("retry_after", 1)
            print(f"[DISCORD] Rate limited — retrying in {retry_after}s")
            time.sleep(retry_after)
            try:
                # C-5: Resend full text (including splits)
                chunks = [text[i:i+1800] for i in range(0, len(text), 1800)]
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        time.sleep(0.3)
                    _send_chunk(channel_id, chunk)
                return True
            except Exception:
                pass
        print(f"[DISCORD] Message send failed: {e}")
        return False
    except Exception as e:
        print(f"[DISCORD] Message send failed: {e}")
        return False


def send_files_sync(channel_id, text, file_paths, **kwargs):
    """Discord file send (synchronous).

    Args:
        channel_id: Discord channel ID
        text: Message text
        file_paths: List of file paths
    """
    if not BOT_TOKEN:
        return False

    # Send text first
    if text:
        send_message_sync(channel_id, text, _save=False)

    session = _get_session()
    try:
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"[DISCORD] File not found: {file_path}")
                continue

            # 25MB limit check (D2)
            file_size = os.path.getsize(file_path)
            if file_size > 25_000_000:
                print(f"[DISCORD] File size exceeded (25MB): {os.path.basename(file_path)}")
                send_message_sync(
                    channel_id,
                    f"File exceeds 25MB: {os.path.basename(file_path)} ({file_size // 1024 // 1024}MB)",
                    _save=False,
                )
                continue

            with open(file_path, "rb") as f:
                resp = session.post(
                    f"{API_BASE}/channels/{channel_id}/messages",
                    data={"content": ""},
                    files={"file": (os.path.basename(file_path), f)},
                    timeout=30,
                )
                resp.raise_for_status()
            time.sleep(0.3)

        return True
    except Exception as e:
        print(f"[DISCORD] File send failed: {e}")
        return False
