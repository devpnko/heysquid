"""
heysquid.channels.slack_listener — Slack Socket Mode listener.

Responsibilities:
- Receive Slack messages/mentions (Socket Mode — WebSocket, no public IP required)
- Download files (Bearer auth)
- Save to messages.json in unified schema
- Broadcast to other channels (full sync)
- Call trigger_executor()

Usage:
    python -m heysquid.channels.slack_listener
"""

import os
import re
import signal
import sys
import time
import requests
from datetime import datetime

from dotenv import load_dotenv

from heysquid.core.config import get_env_path, DATA_DIR_STR
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
ALLOWED_USERS = [u.strip() for u in os.getenv("SLACK_ALLOWED_USERS", "").split(",") if u.strip()]

# Stop keywords (same as telegram_listener)
STOP_KEYWORDS = {"멈춰", "스탑", "중단", "/stop", "잠깐만", "그만", "취소", "stop"}

# File download path
DATA_DIR = DATA_DIR_STR
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")


def _download_slack_file(url_private, filename):
    """Download Slack file (Bearer token auth, S5)"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    ts = int(time.time())
    local_path = os.path.join(DOWNLOAD_DIR, f"slack_{ts}_{safe_name}")

    try:
        # H-8: Streaming download (protect memory for large files)
        resp = requests.get(
            url_private,
            headers={"Authorization": f"Bearer {BOT_TOKEN}"},
            timeout=30,
            stream=True,
        )
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path
    except Exception as e:
        print(f"[SLACK] File download failed: {e}")
        return None


def _strip_mention(text, bot_user_id):
    """Strip <@BOT_ID> mention (S3)"""
    if bot_user_id:
        text = text.replace(f"<@{bot_user_id}>", "").strip()
    return text


_user_name_cache = {}  # H-7: Actual cache implementation


def _get_user_name(client, user_id):
    """Look up Slack user name (H-7: cached)"""
    if user_id in _user_name_cache:
        return _user_name_cache[user_id]
    try:
        result = client.users_info(user=user_id)
        profile = result["user"]["profile"]
        name = profile.get("display_name") or profile.get("real_name") or user_id
        _user_name_cache[user_id] = name
        return name
    except Exception:
        return user_id


def _handle_message(event, client, bot_user_id):
    """Core message processing logic"""
    # 1. Ignore bot's own messages (S8 echo loop prevention)
    if event.get("bot_id"):
        return
    if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return

    user_id = event.get("user", "")

    # 2. Allowed user check
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        print(f"[SLACK] Unauthorized user: {user_id}")
        return

    raw_text = event.get("text", "")
    text = _strip_mention(raw_text, bot_user_id)

    if not text and not event.get("files"):
        # D3 style: empty message warning
        print("[SLACK] Empty message received — ignoring")
        return

    channel_id = event.get("channel", "")
    event_ts = event.get("ts", "")
    thread_ts = event.get("thread_ts")

    # message_id: Attach channel prefix (P1)
    message_id = f"slack_{event_ts.replace('.', '')}"

    # 3. Stop command check
    text_lower = text.lower().strip()
    if text_lower in STOP_KEYWORDS:
        _handle_stop(client, channel_id, event_ts, message_id, user_id, text)
        return

    # 4. File download (S5)
    files = []
    for file_info in event.get("files", []):
        url = file_info.get("url_private", "")
        name = file_info.get("name", "unknown")
        size = file_info.get("size", 0)
        mimetype = file_info.get("mimetype", "")
        if url:
            local_path = _download_slack_file(url, name)
            if local_path:
                file_type = "photo" if mimetype.startswith("image/") else "document"
                files.append({
                    "path": local_path,
                    "name": name,
                    "size": size,
                    "type": file_type,
                })

    # 5. User name
    user_name = _get_user_name(client, user_id)

    # 6. Convert to unified schema
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "message_id": message_id,
        "channel": "slack",
        "chat_id": channel_id,
        "text": text,
        "type": "user",
        "first_name": user_name,
        "timestamp": now,
        "processed": False,
        "files": files if files else [],
    }
    if thread_ts:
        message_data["thread_ts"] = thread_ts

    # 7. Save to messages.json (flock atomic)
    from ._msg_store import load_and_modify

    def _append_msg(data):
        existing_ids = {m["message_id"] for m in data.get("messages", [])}
        if message_data["message_id"] not in existing_ids:
            data["messages"].append(message_data)
        return data
    load_and_modify(_append_msg)

    print(f"[SLACK] Message saved: {user_name}: {text[:50]}...")

    # 8. Acknowledgment reaction (T1)
    try:
        client.reactions_add(
            channel=channel_id,
            name="white_check_mark",
            timestamp=event_ts,
        )
    except Exception:
        pass  # Ignore if reaction already exists or no permission

    # 9. Broadcast to other channels (full sync)
    try:
        from ._router import broadcast_user_message, broadcast_files
        if text:
            broadcast_user_message(text, source_channel="slack", sender_name=user_name)
        if files:
            local_paths = [f["path"] for f in files if f.get("path")]
            if local_paths:
                broadcast_files(local_paths, exclude_channels={"slack"})
    except Exception as e:
        print(f"[SLACK] Broadcast failed (does not affect Slack processing): {e}")

    # 10. trigger_executor()
    try:
        from ._base import trigger_executor
        trigger_executor()
    except Exception as e:
        print(f"[SLACK] trigger_executor failed: {e}")


def _handle_stop(client, channel_id, event_ts, message_id, user_id, text):
    """Handle stop command"""
    import subprocess

    print(f"[SLACK] Stop command received: {text}")

    # Save message
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "message_id": message_id,
        "channel": "slack",
        "chat_id": channel_id,
        "text": text,
        "type": "user",
        "first_name": _get_user_name(client, user_id),
        "timestamp": now,
        "processed": True,
    }
    from ._msg_store import load_and_modify

    def _append_msg(data):
        existing_ids = {m["message_id"] for m in data.get("messages", [])}
        if message_data["message_id"] not in existing_ids:
            data["messages"].append(message_data)
        return data
    load_and_modify(_append_msg)

    # Kill Claude process
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
            print(f"[SLACK] Claude process stopped: {pids}")

            # Create interrupted file
            from ..core._working_lock import check_working_lock
            lock_info = check_working_lock()
            if lock_info:
                from ..paths import INTERRUPTED_FILE
                import json
                import tempfile
                interrupted_data = {
                    "reason": "user_stop",
                    "stopped_at": now,
                    "channel": "slack",
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

            client.chat_postMessage(channel=channel_id, text="Task stopped.")
        else:
            client.chat_postMessage(channel=channel_id, text="No task is currently running.")
    except Exception as e:
        print(f"[SLACK] Stop handling failed: {e}")


def main():
    """Slack listener main — Socket Mode"""
    if not BOT_TOKEN or not APP_TOKEN:
        print("[SLACK] SLACK_BOT_TOKEN or SLACK_APP_TOKEN not set")
        print("   Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in .env.")
        sys.exit(1)

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=BOT_TOKEN)

    # Look up bot's own user_id
    bot_user_id = None
    try:
        auth = app.client.auth_test()
        bot_user_id = auth.get("user_id")
        print(f"[SLACK] Bot authenticated: {auth.get('user', 'unknown')} ({bot_user_id})")
    except Exception as e:
        print(f"[SLACK] Bot authentication failed: {e}")
        sys.exit(1)

    @app.event("message")
    def on_message(event, client):
        _handle_message(event, client, bot_user_id)

    @app.event("app_mention")
    def on_mention(event, client):
        # H-2: message events already include app_mentions, so
        # we don't process duplicates here (channel messages contain mentions)
        pass

    # SIGTERM handler
    def shutdown(signum, frame):
        print(f"\n[SLACK] Signal {signum} received — shutting down")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("[SLACK] Socket Mode listener starting...")
    print(f"[SLACK] Allowed users: {ALLOWED_USERS or 'all'}")

    handler = SocketModeHandler(app, APP_TOKEN)
    handler.start()  # Blocking


if __name__ == "__main__":
    main()
