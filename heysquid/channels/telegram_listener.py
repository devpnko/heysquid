"""
Telegram message collector (Listener) — heysquid Mac port

Responsibilities:
- Receive new messages via Telegram Bot API
- Save messages to messages.json
- Process only allowed users
- Prevent duplicate messages

Usage:
    python telegram_listener.py
    (Ctrl+C to stop)
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest
import asyncio

# Path setup (Mac)
from ..config import DATA_DIR_STR as DATA_DIR, TASKS_DIR_STR as TASKS_DIR, PROJECT_ROOT_STR as PROJECT_ROOT, get_env_path

# Load .env file
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = [int(uid.strip()) for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if uid.strip()]
POLLING_INTERVAL = int(os.getenv("TELEGRAM_POLLING_INTERVAL", "3"))

from ..paths import MESSAGES_FILE, INTERRUPTED_FILE, WORKING_LOCK_FILE, EXECUTOR_LOCK_FILE
# Stop keywords — if any of these match the full message text, trigger stop
STOP_KEYWORDS = ["멈춰", "스탑", "중단", "/stop", "잠깐만", "스톱", "그만", "취소"]

from ._msg_store import load_telegram_messages as load_messages, save_telegram_messages as save_messages, load_and_modify, get_cursor, _migrate_cursors
from ._base import trigger_executor as _trigger_executor


def _is_stop_command(text):
    """Check if a message is a stop command"""
    return text.strip().lower() in [kw.lower() for kw in STOP_KEYWORDS]


def _kill_executor():
    """Kill the running executor Claude process — same logic as executor.sh kill_all_pm"""
    killed = False
    pidfile = os.path.join(PROJECT_ROOT, "data", "claude.pid")

    # Primary: PID file (most reliable — catches orphan claude too)
    if os.path.exists(pidfile):
        try:
            with open(pidfile, "r") as f:
                for line in f:
                    pid = line.strip()
                    if pid:
                        subprocess.run(["kill", pid], capture_output=True)
                        print(f"[STOP] Killed process from PID file: PID {pid}")
                        killed = True
        except Exception as e:
            print(f"[WARN] Failed to read PID file: {e}")

    # Secondary: caffeinate pattern → kill parent (claude)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for cafe_pid in result.stdout.strip().split("\n"):
                cafe_pid = cafe_pid.strip()
                if cafe_pid:
                    ppid_result = subprocess.run(
                        ["ps", "-p", cafe_pid, "-o", "ppid="],
                        capture_output=True, text=True
                    )
                    parent = ppid_result.stdout.strip()
                    if parent:
                        subprocess.run(["kill", parent], capture_output=True)
                        print(f"[STOP] Killed claude process: PID {parent} (parent of caffeinate={cafe_pid})")
                        killed = True
                    subprocess.run(["kill", cafe_pid], capture_output=True)
                    killed = True
    except Exception as e:
        print(f"[WARN] caffeinate pattern kill failed: {e}")

    # Tertiary: pkill fallback
    subprocess.run(["pkill", "-f", "append-system-prompt-file"], capture_output=True)

    # force kill — kill -9 survivors after 2 seconds
    if killed:
        import time
        time.sleep(2)
        if os.path.exists(pidfile):
            try:
                with open(pidfile, "r") as f:
                    for line in f:
                        pid = line.strip()
                        if pid:
                            subprocess.run(["kill", "-9", pid], capture_output=True)
            except Exception:
                pass
        subprocess.run(["pkill", "-9", "-f", "append-system-prompt-file"], capture_output=True)

    # Delete PID file
    try:
        if os.path.exists(pidfile):
            os.remove(pidfile)
    except OSError:
        pass

    # 2. Delete executor.lock
    if os.path.exists(EXECUTOR_LOCK_FILE):
        try:
            os.remove(EXECUTOR_LOCK_FILE)
            print("[STOP] executor.lock deleted")
        except OSError:
            pass

    # 3. Read and delete working.json
    working_info = None
    if os.path.exists(WORKING_LOCK_FILE):
        try:
            with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
                working_info = json.load(f)
            os.remove(WORKING_LOCK_FILE)
            print("[STOP] working.json deleted")
        except Exception:
            pass

    return killed, working_info


async def _handle_stop_command(msg_data):
    """
    Handle stop command (async — called within fetch_new_messages):
    0. Force-flush session memory (before kill!)
    1. Kill executor
    2. Save interrupted.json
    3. Notify user
    4. Mark stop command message as processed
    """
    chat_id = msg_data["chat_id"]
    message_id = msg_data["message_id"]

    print(f"[STOP] Stop command detected: '{msg_data['text']}' from {msg_data['first_name']}")

    # 0. Force-flush session memory (before kill!)
    try:
        from heysquid.memory.session import compact_session_memory, save_session_summary
        compact_session_memory()
        save_session_summary()
    except Exception:
        pass

    killed, working_info = _kill_executor()

    # Save interrupted.json
    interrupted_data = {
        "interrupted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": msg_data["text"],
        "by_user": msg_data["first_name"],
        "chat_id": chat_id,
        "previous_work": None
    }

    if working_info:
        interrupted_data["previous_work"] = {
            "instruction": working_info.get("instruction_summary", ""),
            "started_at": working_info.get("started_at", ""),
            "message_id": working_info.get("message_id")
        }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INTERRUPTED_FILE, "w", encoding="utf-8") as f:
        json.dump(interrupted_data, f, ensure_ascii=False, indent=2)
    print(f"[STOP] interrupted.json saved")

    # Mark all unprocessed messages as processed (prevent re-execution of previous messages)
    # Previous work context is preserved in interrupted.json — uses flock
    cleared = 0
    def _clear_unprocessed(data):
        nonlocal cleared
        for m in data.get("messages", []):
            if not m.get("processed", False):
                m["processed"] = True
                cleared += 1
        return data
    load_and_modify(_clear_unprocessed)
    if cleared:
        print(f"[STOP] Cleared {cleared} unprocessed messages")

    # Notify user (async — prevent event loop conflicts)
    from .telegram import send_message

    if working_info:
        task_name = working_info.get("instruction_summary", "unknown")
        reply = f"Task stopped.\n\nStopped task: {task_name}\n\nPlease send a new instruction."
    elif killed:
        reply = "Task stopped. Please send a new instruction."
    else:
        reply = "No task is currently running."

    await send_message(chat_id, reply)
    print(f"[STOP] Stop notification sent")


def setup_bot_token():
    """Prompt user to enter and save the token if not in .env"""
    global BOT_TOKEN

    if BOT_TOKEN and BOT_TOKEN not in ("", "YOUR_BOT_TOKEN", "your_bot_token_here"):
        return True

    print("\n" + "=" * 60)
    print("TELEGRAM_BOT_TOKEN is not set in .env.")
    print("=" * 60)
    print()
    print("Setup instructions:")
    print("   1. Search for @BotFather on Telegram and start it")
    print("   2. Create a new bot with the /newbot command")
    print("   3. Paste the token provided by @BotFather below")
    print()
    print("   Example: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ")
    print()

    if not sys.stdin.isatty():
        print("[ERROR] Not an interactive environment. Please set TELEGRAM_BOT_TOKEN directly in the .env file.")
        return False

    token = input("Enter bot token: ").strip()

    if not token:
        print("Token is empty. Exiting.")
        return False

    from dotenv import set_key

    env_path = get_env_path()
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("")

    set_key(env_path, "TELEGRAM_BOT_TOKEN", token)
    BOT_TOKEN = token
    os.environ["TELEGRAM_BOT_TOKEN"] = token

    print(f"[OK] TELEGRAM_BOT_TOKEN saved to .env!")
    print()
    return True


async def download_file(bot, file_id, message_id, file_type, file_name=None):
    """
    Download a Telegram file

    Args:
        bot: Telegram Bot instance
        file_id: Telegram file ID
        message_id: Message ID
        file_type: File type (photo, document, video, audio, voice)
        file_name: Filename (for documents)

    Returns:
        str: Downloaded file path (None on failure)
    """
    try:
        # Create tasks/msg_{message_id} directory
        task_dir = os.path.join(TASKS_DIR, f"msg_{message_id}")
        os.makedirs(task_dir, exist_ok=True)

        # Get file info
        file = await bot.get_file(file_id)

        # Determine file extension
        if file_name:
            filename = file_name
        else:
            file_path = file.file_path
            ext = os.path.splitext(file_path)[1] or '.jpg'

            type_prefix = {
                'photo': 'image',
                'video': 'video',
                'audio': 'audio',
                'voice': 'voice'
            }
            prefix = type_prefix.get(file_type, 'file')
            filename = f"{prefix}_{message_id}{ext}"

        # Download file
        local_path = os.path.join(task_dir, filename)
        await file.download_to_drive(local_path)

        print(f"[FILE] File downloaded: {filename} ({file.file_size} bytes)")
        return local_path

    except Exception as e:
        print(f"[ERROR] File download failed: {e}")
        return None


async def fetch_new_messages():
    """Fetch new messages (text + image + file support)"""
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN not set. Exiting.")
        return None

    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=15.0,   # long-polling 5s + 10s buffer
        write_timeout=10.0,
        pool_timeout=5.0
    )
    bot = Bot(token=BOT_TOKEN, get_updates_request=request)
    last_update_id = get_cursor("telegram", "last_update_id")

    try:
        updates = await bot.get_updates(
            offset=last_update_id + 1,
            timeout=5,
            allowed_updates=["message", "callback_query"]
        )

        new_messages = []
        max_update_id = last_update_id

        for update in updates:
            # Handle inline button callback (stop button)
            if update.callback_query:
                cq = update.callback_query
                if cq.data == "stop":
                    user = cq.from_user
                    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
                        continue
                    # Callback response (dismiss button loading)
                    try:
                        await bot.answer_callback_query(cq.id, text="Processing stop...")
                    except Exception:
                        pass
                    # Handle stop
                    stop_data = {
                        "chat_id": cq.message.chat_id,
                        "message_id": cq.message.message_id,
                        "text": "stop",
                        "first_name": user.first_name or "",
                    }
                    await _handle_stop_command(stop_data)
                    if update.update_id > max_update_id:
                        from ._msg_store import set_cursor
                        set_cursor("telegram", "last_update_id", update.update_id)
                    return 0
                continue

            if not update.message:
                continue

            msg = update.message
            user = msg.from_user

            # Allowed user check
            if ALLOWED_USERS and user.id not in ALLOWED_USERS:
                print(f"[WARN] Blocked: unauthorized user {user.id} ({user.first_name})")
                continue

            # Extract text (caption or text)
            text = msg.caption or msg.text or ""

            # Download files
            files = []

            # Photos
            if msg.photo:
                largest_photo = msg.photo[-1]
                file_path = await download_file(
                    bot, largest_photo.file_id, msg.message_id, 'photo'
                )
                if file_path:
                    files.append({
                        "type": "photo",
                        "path": file_path,
                        "size": largest_photo.file_size
                    })

            # Documents
            if msg.document:
                file_path = await download_file(
                    bot, msg.document.file_id, msg.message_id,
                    'document', msg.document.file_name
                )
                if file_path:
                    files.append({
                        "type": "document",
                        "path": file_path,
                        "name": msg.document.file_name,
                        "mime_type": msg.document.mime_type,
                        "size": msg.document.file_size
                    })

            # Video
            if msg.video:
                file_path = await download_file(
                    bot, msg.video.file_id, msg.message_id, 'video'
                )
                if file_path:
                    files.append({
                        "type": "video",
                        "path": file_path,
                        "duration": msg.video.duration,
                        "size": msg.video.file_size
                    })

            # Audio
            if msg.audio:
                file_path = await download_file(
                    bot, msg.audio.file_id, msg.message_id,
                    'audio', msg.audio.file_name
                )
                if file_path:
                    files.append({
                        "type": "audio",
                        "path": file_path,
                        "duration": msg.audio.duration,
                        "size": msg.audio.file_size
                    })

            # Voice messages
            if msg.voice:
                file_path = await download_file(
                    bot, msg.voice.file_id, msg.message_id, 'voice'
                )
                if file_path:
                    files.append({
                        "type": "voice",
                        "path": file_path,
                        "duration": msg.voice.duration,
                        "size": msg.voice.file_size
                    })

            # Location info
            location_info = None
            if msg.location:
                location_info = {
                    "latitude": msg.location.latitude,
                    "longitude": msg.location.longitude
                }
                if hasattr(msg.location, 'horizontal_accuracy') and msg.location.horizontal_accuracy:
                    location_info["accuracy"] = msg.location.horizontal_accuracy
                print(f"[LOC] Location received: lat {msg.location.latitude}, lng {msg.location.longitude}")

            # Must have at least one of: text, files, or location
            if not text and not files and not location_info:
                continue

            # Compose message data
            message_data = {
                "message_id": msg.message_id,
                "update_id": update.update_id,
                "type": "user",
                "channel": "telegram",
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "chat_id": msg.chat_id,
                "text": text,
                "files": files,
                "location": location_info,
                "timestamp": msg.date.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S"),
                "processed": False,
                "reply_to_message_id": msg.reply_to_message.message_id if msg.reply_to_message else None,
            }

            new_messages.append(message_data)

            if update.update_id > max_update_id:
                max_update_id = update.update_id

        if new_messages:
            # flock-based atomic merge (prevent lost updates)
            def _merge_new(data):
                data = _migrate_cursors(data)
                existing_ids = {m["message_id"] for m in data.get("messages", [])}
                for msg_data in new_messages:
                    if msg_data["message_id"] not in existing_ids:
                        data["messages"].append(msg_data)
                # Update cursor
                if "cursors" not in data:
                    data["cursors"] = {}
                if "telegram" not in data["cursors"]:
                    data["cursors"]["telegram"] = {}
                data["cursors"]["telegram"]["last_update_id"] = max_update_id
                data["last_update_id"] = max_update_id  # Backward compat
                return data
            load_and_modify(_merge_new)

            for msg in new_messages:
                text_preview = msg['text'][:50] if msg['text'] else "(files only)" if msg['files'] else "(location)" if msg.get('location') else ""
                file_info = f" + {len(msg['files'])} file(s)" if msg['files'] else ""
                location_info = f" + location" if msg.get('location') else ""
                print(f"[MSG] New message: [{msg['timestamp']}] {msg['first_name']}: {text_preview}...{file_info}{location_info}")

            # Detect stop commands — process before regular messages
            stop_messages = [m for m in new_messages if m['text'] and _is_stop_command(m['text'])]
            if stop_messages:
                await _handle_stop_command(stop_messages[0])
                # Stop commands do not trigger executor — return 0
                return 0

            # Acknowledgment reaction (not saved to messages.json — reduce noise)
            from telegram import ReactionTypeEmoji
            for msg in new_messages:
                try:
                    await bot.set_message_reaction(
                        chat_id=msg['chat_id'],
                        message_id=msg['message_id'],
                        reaction=[ReactionTypeEmoji(emoji="👀")]
                    )
                except Exception:
                    pass  # Ignore reaction failures

            # Relay to other channels (full sync — best-effort)
            try:
                from ._router import broadcast_user_message, broadcast_files
                for msg in new_messages:
                    if msg.get("text"):
                        broadcast_user_message(msg["text"], "telegram", msg.get("first_name", ""))
                    if msg.get("files"):
                        local_paths = [f["path"] for f in msg["files"] if f.get("path")]
                        if local_paths:
                            broadcast_files(local_paths, exclude_channels={"telegram"})
            except Exception as e:
                print(f"[WARN] Broadcast failed (does not affect TG processing): {e}")

            return len(new_messages)

        return 0

    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return None


RETRY_MAX = 3


def _cleanup_zombie_pm():
    """Detect + clean up zombie PM sessions — kill all if multiple PMs running simultaneously"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return  # No PM processes

        pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        if len(pids) <= 1:
            return  # Single session — normal

        # Multiple PM sessions detected — kill all
        print(f"[ZOMBIE] Multiple PM sessions detected: {len(pids)} (PIDs: {', '.join(pids)})")
        subprocess.run(
            ["pkill", "-f", "claude.*append-system-prompt-file"],
            capture_output=True
        )
        time.sleep(2)

        # Clean up lock files
        if os.path.exists(EXECUTOR_LOCK_FILE):
            try:
                os.remove(EXECUTOR_LOCK_FILE)
            except OSError:
                pass

        print(f"[ZOMBIE] {len(pids)} zombie PM sessions cleaned up. New session will start on next message.")

    except Exception as e:
        print(f"[WARN] Zombie PM scan failed: {e}")


def _retry_unprocessed():
    """Check unprocessed messages + re-trigger executor if retry_count < 3 — uses flock

    Key fix: if executor is NOT running but messages have seen=True,
    they are stale (PM exited without processing). Reset seen flag
    so they become retryable.
    """
    # No retry needed if PM/executor is running
    if os.path.exists(EXECUTOR_LOCK_FILE):
        return
    if os.path.exists(WORKING_LOCK_FILE):
        return
    if not os.path.exists(MESSAGES_FILE):
        return

    should_trigger = False
    retry_info = ""

    def _bump_retry(data):
        nonlocal should_trigger, retry_info
        # Reset stale seen flags — executor is not running so no PM is processing these
        stale_count = 0
        for msg in data.get("messages", []):
            if (msg.get("type") == "user"
                    and not msg.get("processed", False)
                    and msg.get("seen", False)):
                msg["seen"] = False
                stale_count += 1
        if stale_count:
            print(f"[RETRY] Reset {stale_count} stale seen flag(s)")

        retryable = [
            msg for msg in data.get("messages", [])
            if msg.get("type") == "user"
            and not msg.get("processed", False)
            and msg.get("retry_count", 0) < RETRY_MAX
        ]
        if not retryable:
            return data
        for msg in retryable:
            msg["retry_count"] = msg.get("retry_count", 0) + 1
        retry_counts = [msg["retry_count"] for msg in retryable]
        retry_info = f"Retrying {len(retryable)} unprocessed message(s) (retry #{max(retry_counts)})"
        should_trigger = True
        return data

    load_and_modify(_bump_retry)

    if should_trigger:
        print(f"[RETRY] {retry_info}")
        _trigger_executor()


# _trigger_executor is imported from _base.trigger_executor (see top)


async def listen_loop():
    """Message receive loop — immediately trigger executor.sh when new messages detected"""
    print("=" * 60)
    print("heysquid - Telegram message collector started")
    print("=" * 60)

    if not setup_bot_token():
        return

    # Register bot command menu (/stop)
    from .telegram import register_bot_commands_sync
    register_bot_commands_sync()

    print(f"Polling interval: {POLLING_INTERVAL}s")
    print(f"Allowed users: {ALLOWED_USERS}")
    print(f"Message storage file: {MESSAGES_FILE}")
    print("\nWaiting... (Ctrl+C to stop)\n")

    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            result = await fetch_new_messages()

            if result is None:
                print(f"[{now}] #{cycle_count} - Error occurred, waiting to retry...")
            elif result > 0:
                print(f"[{now}] #{cycle_count} - {result} message(s) collected")
                _trigger_executor()
            else:
                if cycle_count % 30 == 0:
                    print(f"[{now}] #{cycle_count} - Waiting...")

            # Reap zombie child processes (executor.sh) to prevent <defunct> accumulation
            try:
                while True:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
            except ChildProcessError:
                pass  # No child processes

            # Every 60 cycles (~10 min): re-trigger unprocessed messages + zombie PM scan
            if cycle_count % 60 == 0:
                _cleanup_zombie_pm()
                _retry_unprocessed()

            await asyncio.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n\nShutdown signal received. Exiting.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(listen_loop())
