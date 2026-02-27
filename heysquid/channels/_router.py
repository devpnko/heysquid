"""
heysquid.channels._router — Channel routing + broadcast.

Full sync model: all channels share a single conversation room.
- broadcast_all(): PM response → all channels
- broadcast_user_message(): Relay user messages → other channels
- broadcast_files(): Files → all channels (fallback notification if size exceeded)
"""

import os
import threading

_SENDERS = {}  # {"telegram": module, "slack": module, "discord": module}
_SENDERS_LOCK = threading.Lock()  # H-10: thread-safe registration

# Per-channel tags (2 characters)
CHANNEL_TAGS = {
    "telegram": "TG",
    "slack": "SL",
    "discord": "DC",
    "tui": "TUI",
}

# Per-channel file size limits (bytes)
CHANNEL_LIMITS = {
    "discord": 25_000_000,
    "telegram": 50_000_000,
    "slack": 1_000_000_000,
}

# per-channel broadcast timeout (seconds)
BROADCAST_TIMEOUT = 5


def register_sender(channel_name, sender_module):
    """Register a channel sender (H-10: thread-safe)"""
    with _SENDERS_LOCK:
        _SENDERS[channel_name] = sender_module


def get_sender(channel_name):
    """Look up a registered sender"""
    return _SENDERS.get(channel_name)


def get_active_channels():
    """List of currently registered active channels"""
    return list(_SENDERS.keys())


def _run_with_timeout(fn, timeout, channel_name):
    """H-1: Apply per-channel timeout (spec: broadcast requires per-channel 5s timeout)"""
    result = [False]
    exc = [None]

    def _target():
        try:
            result[0] = fn()
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        print(f"[WARN] {channel_name} send timed out ({timeout}s)")
        return False
    if exc[0]:
        raise exc[0]
    return result[0]


def send_to_channel(channel, chat_id, text, **kwargs):
    """Send a message to a single channel (internal util, per-channel timeout applied)"""
    sender = get_sender(channel)
    if sender:
        try:
            return _run_with_timeout(
                lambda: sender.send_message_sync(chat_id, text, _save=False, **kwargs),
                BROADCAST_TIMEOUT, channel,
            )
        except Exception as e:
            print(f"[WARN] {channel} send failed: {e}")
            return False
    return False


def broadcast_all(text, exclude_channels=None):
    """Broadcast to all active channels — default delivery method for PM responses.

    messages.json persistence is the caller's (hub) responsibility.
    Each sender is called with _save=False to prevent duplicate saves.
    H-1: per-channel 5s timeout applied.

    Returns:
        dict: {channel_name: success_bool}
    """
    exclude = set(exclude_channels or [])
    results = {}
    for name, sender in list(_SENDERS.items()):
        if name in exclude:
            continue
        try:
            default_id = _get_default_chat_id(name)
            if default_id:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id: s.send_message_sync(d, text, _save=False),
                    BROADCAST_TIMEOUT, name,
                )
            else:
                results[name] = False
        except Exception as e:
            print(f"[WARN] broadcast to {name} failed: {e}")
            results[name] = False
    return results


def broadcast_user_message(text, source_channel, sender_name=""):
    """Relay a user message to other channels — called by each listener.

    Args:
        text: Original message text
        source_channel: Source channel name ("telegram", "slack", "discord", "tui")
        sender_name: Name of the sender

    Returns:
        dict: {channel_name: success_bool}
    """
    tag = CHANNEL_TAGS.get(source_channel, source_channel.upper()[:2])
    prefix = f"[{tag}] {sender_name}: " if sender_name else f"[{tag}] "
    relay_text = prefix + text

    results = {}
    for name, sender in list(_SENDERS.items()):
        if name == source_channel:
            continue  # Skip source channel
        try:
            default_id = _get_default_chat_id(name)
            if default_id:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id: s.send_message_sync(d, relay_text, _save=False),
                    BROADCAST_TIMEOUT, name,
                )
            else:
                results[name] = False
        except Exception as e:
            print(f"[WARN] relay to {name} failed: {e}")
            results[name] = False
    return results


def broadcast_files(file_paths, text="", exclude_channels=None):
    """Broadcast files to all active channels (notification fallback if size exceeded).

    Returns:
        dict: {channel_name: success_bool}
    """
    exclude = set(exclude_channels or [])
    results = {}
    for name, sender in list(_SENDERS.items()):
        if name in exclude:
            continue
        try:
            default_id = _get_default_chat_id(name)
            if not default_id:
                continue
            limit = CHANNEL_LIMITS.get(name, 50_000_000)
            sendable = [f for f in file_paths if os.path.exists(f) and os.path.getsize(f) <= limit]
            oversized = [f for f in file_paths if os.path.exists(f) and os.path.getsize(f) > limit]
            if sendable:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id, sp=sendable: s.send_files_sync(d, text, sp),
                    BROADCAST_TIMEOUT * 6, name,  # File transfer uses 6x timeout (30s)
                )
            if oversized:
                names_str = ", ".join(os.path.basename(f) for f in oversized)
                sender.send_message_sync(default_id, f"[FILE] Size exceeded (channel limit): {names_str}", _save=False)
        except Exception as e:
            print(f"[WARN] file broadcast to {name} failed: {e}")
            results[name] = False
    return results


def _get_default_chat_id(channel):
    """Default response target ID per channel (loaded from env)"""
    mapping = {
        "telegram": "TELEGRAM_ALLOWED_USERS",  # First user
        "slack": "SLACK_DEFAULT_CHANNEL",
        "discord": "DISCORD_DEFAULT_CHANNEL",
    }
    key = mapping.get(channel)
    if not key:
        return None
    val = os.getenv(key, "")
    if channel == "telegram":
        val = val.split(",")[0].strip()
    return val or None


def _auto_register():
    """Auto-register available senders (based on env tokens)"""
    # Telegram — always attempt
    try:
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            from . import telegram
            register_sender("telegram", telegram)
    except ImportError:
        pass

    # Slack — only when token is present
    try:
        if os.getenv("SLACK_BOT_TOKEN"):
            from . import slack  # noqa: F401
            register_sender("slack", slack)
    except ImportError:
        pass

    # Discord — only when token is present
    try:
        if os.getenv("DISCORD_BOT_TOKEN"):
            from . import discord_channel  # noqa: F401
            register_sender("discord", discord_channel)
    except ImportError:
        pass


# Auto-register on module import
_auto_register()
