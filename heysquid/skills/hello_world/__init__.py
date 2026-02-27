"""
Hello World example skill — reference for creating new skills.

Copy this file to heysquid/skills/{your_skill}/__init__.py and
the plugin loader will auto-discover it.

Usage:
    TUI: /skill hello_world
    Code: from heysquid.skills import run_skill; run_skill("hello_world")
"""

from datetime import datetime

SKILL_META = {
    "name": "hello_world",
    "description": "Example skill — reference for writing new skills",
    "trigger": "manual",
    "enabled": True,
}


def execute(**kwargs) -> dict:
    """Skill entry point.

    kwargs:
        triggered_by: "scheduler" | "manual" | "pm" | "webhook"
        chat_id: int (for Telegram delivery, 0 means no delivery)
        args: str (user input arguments)
        payload: dict (webhook JSON body)
        callback_url: str (URL to POST upon completion)
    """
    name = kwargs.get("args", "").strip() or "World"
    now = datetime.now().strftime("%H:%M")

    message = f"Hello, {name}! 🐙 Current time: {now}"

    # Send via Telegram (when chat_id is present)
    chat_id = kwargs.get("chat_id", 0)
    if chat_id:
        try:
            from ...channels.telegram import send_message_sync
            send_message_sync(int(chat_id), message, parse_mode=None)
        except Exception as e:
            print(f"[WARN] Telegram send failed: {e}")

    return {
        "ok": True,
        "message": message,
    }
