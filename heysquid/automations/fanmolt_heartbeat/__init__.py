"""FanMolt heartbeat automation — 4시간 간격 에이전트 활동 사이클.

interval 트리거로 매분 호출되지만, 내부적으로 4시간 쿨다운 체크.
실제 heartbeat 로직은 skills/fanmolt/heartbeat_runner.py에 위임.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_META = {
    "name": "fanmolt_heartbeat",
    "description": "FanMolt AI 크리에이터 heartbeat (4h 간격)",
    "trigger": "interval",
    "enabled": True,
    "icon": "💰",
    "workspace": "fanmolt",
}

HEARTBEAT_INTERVAL_HOURS = 4
_STATE_FILE = Path(__file__).parent / "_state.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def execute(**kwargs) -> dict | None:
    """interval 트리거 — 4시간 경과 시에만 heartbeat 실행."""
    state = _load_state()
    last_run = state.get("last_heartbeat_ts", 0)
    now = time.time()

    elapsed_hours = (now - last_run) / 3600
    if elapsed_hours < HEARTBEAT_INTERVAL_HOURS:
        return None  # 아직 때가 안 됨

    # heartbeat 실행
    from heysquid.skills.fanmolt.heartbeat_runner import run_all

    logger.info("FanMolt heartbeat 시작 (%.1fh 경과)", elapsed_hours)
    results = run_all()

    # 상태 저장
    state["last_heartbeat_ts"] = now
    _save_state(state)

    # 텔레그램 리포트
    report = _format_report(results)
    _send_telegram(report)

    logger.info("FanMolt heartbeat 완료: %d 에이전트", len(results))
    return {"ok": True, "results": results, "report": report}


def _format_report(results: list) -> str:
    if not results:
        return "FanMolt heartbeat: 활동할 에이전트 없음"
    lines = ["💰 FanMolt heartbeat 완료"]
    for r in results:
        name = r.get("handle", "?")
        if r.get("error"):
            lines.append(f"  {name}: ❌ {r['error'][:50]}")
            continue
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
