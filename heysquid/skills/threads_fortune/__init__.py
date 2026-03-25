"""threads_fortune -- zodiac daily fortune skill for dkbsqd.

Generates deterministic zodiac fortune based on saju day-pillar analysis.
No AI calls -- pure calendar math + relation tables.

Usage:
    TUI: /skill threads_fortune
    Code: from heysquid.skills import run_skill; run_skill("threads_fortune")
"""

from datetime import date, datetime

from ._generator import generate_daily_fortune, generate_fortune_with_context

SKILL_META = {
    "name": "threads_fortune",
    "description": "dkbsqd zodiac daily fortune generator (saju day-pillar based)",
    "trigger": "manual",
    "enabled": True,
}


def execute(**kwargs) -> dict:
    """Skill entry point.

    kwargs:
        args: str -- optional date in YYYY-MM-DD format (defaults to today)
        chat_id: int -- Telegram chat to deliver result
        triggered_by: str
    """
    args = kwargs.get("args", "").strip()

    # Parse optional date argument
    target_date: date | None = None
    if args:
        try:
            target_date = datetime.strptime(args, "%Y-%m-%d").date()
        except ValueError:
            return {"ok": False, "error": f"Invalid date format: {args} (use YYYY-MM-DD)"}

    context = generate_fortune_with_context(target_date)
    text = context["formatted_text"]

    # Send via Telegram if chat_id present
    chat_id = kwargs.get("chat_id", 0)
    if chat_id:
        try:
            from ...channels.telegram import send_message_sync
            send_message_sync(int(chat_id), text, parse_mode=None)
        except Exception as e:
            print(f"[WARN] Telegram send failed: {e}")

    return {
        "ok": True,
        "message": text,
        "context": context,
    }
