"""FanMolt heartbeat automation — per-agent schedule_hours-based activity cycle.

Called every minute via interval trigger. Checks each agent's
schedule_hours (default 4h) individually and runs heartbeat
only for agents whose time has come.
"""

import logging

logger = logging.getLogger(__name__)

SKILL_META = {
    "name": "fanmolt_heartbeat",
    "description": "FanMolt AI creator heartbeat (per-agent schedule)",
    "trigger": "interval",
    "enabled": True,
    "icon": "💰",
    "workspace": "fanmolt",
}


def execute(**kwargs) -> dict | None:
    """Interval trigger — check per-agent schedule_hours and run heartbeat."""
    from heysquid.skills.fanmolt.heartbeat_runner import run_due_agents

    results = run_due_agents()

    if not results:
        return None  # no agents are due

    # Telegram report
    report = _format_report(results)
    _send_telegram(report)

    logger.info("FanMolt heartbeat complete: %d agent(s)", len(results))
    return {"ok": True, "results": results, "report": report}


def _format_report(results: list) -> str:
    if not results:
        return "FanMolt heartbeat: no agents to run"
    lines = ["💰 FanMolt heartbeat complete"]
    llm_warnings = []
    for r in results:
        name = r.get("handle", "?")
        if r.get("error"):
            lines.append(f"  {name}: ❌ {r['error'][:50]}")
            continue
        if r.get("llm_unavailable"):
            llm_warnings.append(name)
        replies = r.get("replies", 0)
        comments = r.get("comments", 0)
        posted = "1 post" if r.get("posted") else ""
        parts = []
        if replies:
            parts.append(f"{replies} reply(ies)")
        if comments:
            parts.append(f"{comments} comment(s)")
        if posted:
            parts.append(posted)
        activity = " | ".join(parts) if parts else "no activity"
        lines.append(f"  {name}: {activity}")
    # LLM unavailable notice
    if llm_warnings:
        lines.append("")
        lines.append(f"  ⚠️ LLM unavailable — skipped: {', '.join(llm_warnings)}")
    return "\n".join(lines)


def _send_telegram(msg: str) -> None:
    try:
        import os
        from dotenv import load_dotenv
        from heysquid.core.config import get_env_path
        load_dotenv(get_env_path())
        chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
        if not chat_id:
            return
        from heysquid.channels.telegram import send_message_sync
        send_message_sync(int(chat_id), msg, parse_mode=None)
    except Exception:
        pass
