"""
heysquid.channels._msg_store — messages.json I/O.

Functions:
- load_telegram_messages / save_telegram_messages
- save_bot_response
- get_cursor / set_cursor  (multi-channel cursor management)
- _safe_parse_timestamp, _cleanup_old_messages
- _poll_telegram_once
"""

import os
import json
import fcntl
import tempfile
from datetime import datetime, timedelta

from ..paths import MESSAGES_FILE, DATA_DIR

_LOCK_PATH = MESSAGES_FILE + '.lock'


def _default_data():
    return {"messages": [], "last_update_id": 0, "cursors": {}}


def _migrate_cursors(data):
    """Migrate last_update_id → cursors.telegram (backward compatibility)"""
    if "cursors" not in data:
        data["cursors"] = {}
    # Move existing last_update_id if cursors.telegram is absent
    old_id = data.get("last_update_id", 0)
    if old_id and "telegram" not in data["cursors"]:
        data["cursors"]["telegram"] = {"last_update_id": old_id}
    return data


def load_telegram_messages():
    """Load messages.json (includes cursors migration)"""
    if not os.path.exists(MESSAGES_FILE):
        return _default_data()

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate_cursors(data)
    except Exception as e:
        print(f"[WARN] messages.json read error: {e}")
        return _default_data()


def save_telegram_messages(data):
    """Atomic save of messages.json (tmp + fsync + rename)"""
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix='.json.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, MESSAGES_FILE)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_and_modify(modifier_fn):
    """Read-modify-write messages.json under lock (fcntl.flock)

    Args:
        modifier_fn: Function that takes a data dict and returns the modified data dict
    Returns:
        Return value of modifier_fn
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_LOCK_PATH, 'w') as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = load_telegram_messages()
            result = modifier_fn(data)
            # C-7: Use original data when modifier_fn returns None (defensive)
            if result is None:
                result = data
            save_telegram_messages(result)
            return result
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def save_bot_response(chat_id, text, reply_to_message_ids, files=None,
                      channel="system", sent_message_id=None):
    """Save bot response to messages.json (preserve conversation context) — uses flock

    Safety net: If channel is a single channel ("tui", "telegram", "dashboard"),
    auto-relay to other active channels (prevent missed responses).
    Responses via broadcast_all() arrive with channel="broadcast", so no relay.
    """
    bot_message = {
        "message_id": f"bot_{reply_to_message_ids[0]}",
        "type": "bot",
        "channel": channel,
        "chat_id": chat_id,
        "text": text,
        "files": files or [],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reply_to": reply_to_message_ids,
        "processed": True,
    }
    if sent_message_id is not None:
        bot_message["sent_message_id"] = sent_message_id

    def _append_bot_msg(data):
        data["messages"].append(bot_message)
        return data

    load_and_modify(_append_bot_msg)
    print(f"[LOG] Bot response saved (reply_to: {reply_to_message_ids})")

    # Safety net: Relay single-channel responses to other channels
    _SINGLE_CHANNELS = {"tui", "telegram", "dashboard"}
    if channel in _SINGLE_CHANNELS:
        try:
            from ._router import broadcast_all
            broadcast_all(text, exclude_channels={channel})
        except Exception as e:
            print(f"[WARN] Relay failed: {e}")


def get_cursor(channel, key=None):
    """Get cursor value for a channel.

    Args:
        channel: "telegram", "slack", "discord"
        key: Specific key within the cursor (e.g., "last_update_id"). None returns the full channel cursor dict.
    """
    data = load_telegram_messages()
    ch_cursor = data.get("cursors", {}).get(channel, {})
    # Backward compat: also check top-level last_update_id for telegram
    if channel == "telegram" and not ch_cursor:
        ch_cursor = {"last_update_id": data.get("last_update_id", 0)}
    if key:
        return ch_cursor.get(key, 0)
    return ch_cursor


def set_cursor(channel, key, value):
    """Set cursor value for a channel (flock atomic).

    Args:
        channel: "telegram", "slack", "discord"
        key: Key within the cursor (e.g., "last_update_id")
        value: Value to set
    """
    def _update_cursor(data):
        data = _migrate_cursors(data)
        if channel not in data["cursors"]:
            data["cursors"][channel] = {}
        data["cursors"][channel][key] = value
        # Backward compat: sync telegram to top-level as well
        if channel == "telegram" and key == "last_update_id":
            data["last_update_id"] = value
        return data
    load_and_modify(_update_cursor)


def _safe_parse_timestamp(ts):
    """Parse timestamp. Returns None on failure."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _cleanup_old_messages():
    """Clean up processed messages older than 30 days (C-1: unified via load_and_modify — flock atomic)"""
    cutoff = datetime.now() - timedelta(days=30)

    def _do_cleanup(data):
        messages = data.get("messages", [])
        cleaned = [
            msg for msg in messages
            if not msg.get("processed", False)
            or (_safe_parse_timestamp(msg.get("timestamp", "")) or datetime.now()) > cutoff
        ]
        removed = len(messages) - len(cleaned)
        if removed > 0:
            data["messages"] = cleaned
            print(f"[CLEAN] Cleaned up {removed} messages older than 30 days")
        return data

    load_and_modify(_do_cleanup)


def _poll_telegram_once():
    """Fetch new messages from Telegram API once and update json"""
    from .telegram_listener import fetch_new_messages
    from .telegram import run_async_safe
    try:
        run_async_safe(fetch_new_messages())
    except Exception as e:
        print(f"[WARN] Error during polling: {e}")
