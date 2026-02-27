"""FanMolt heartbeat automation — 에이전트별 schedule_hours 기반 활동 사이클.

interval 트리거로 매분 호출. 각 에이전트의 schedule_hours(기본 4h)를
개별 체크하여 시간이 된 에이전트만 heartbeat 실행.
"""

import logging

logger = logging.getLogger(__name__)

SKILL_META = {
    "name": "fanmolt_heartbeat",
    "description": "FanMolt AI 크리에이터 heartbeat (에이전트별 주기)",
    "trigger": "interval",
    "enabled": True,
    "icon": "💰",
    "workspace": "fanmolt",
}


def execute(**kwargs) -> dict | None:
    """interval 트리거 — 에이전트별 schedule_hours 체크 후 heartbeat."""
    from heysquid.skills.fanmolt.heartbeat_runner import run_due_agents

    results = run_due_agents()

    if not results:
        return None  # 아무도 시간 안 됨

    # 텔레그램 리포트
    report = _format_report(results)
    _send_telegram(report)

    logger.info("FanMolt heartbeat 완료: %d 에이전트", len(results))
    return {"ok": True, "results": results, "report": report}


def _format_report(results: list) -> str:
    if not results:
        return "FanMolt heartbeat: 활동할 에이전트 없음"
    lines = ["💰 FanMolt heartbeat 완료"]
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
        posted = "글 1" if r.get("posted") else ""
        parts = []
        if replies:
            parts.append(f"답변 {replies}")
        if comments:
            parts.append(f"댓글 {comments}")
        if posted:
            parts.append(posted)
        activity = " | ".join(parts) if parts else "활동 없음"
        lines.append(f"  {name}: {activity}")
    # H3: LLM 불가 알림
    if llm_warnings:
        lines.append("")
        lines.append(f"  ⚠️ LLM 불가 — 스킵: {', '.join(llm_warnings)}")
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
