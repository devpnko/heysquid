"""Threads 예약 게시 — 스케줄러가 매분 호출하여 예정 시간이 된 글을 자동 게시."""

SKILL_META = {
    "name": "threads_post",
    "description": "Threads 예약 게시 자동 실행",
    "trigger": "interval",
    "enabled": True,
}


def execute(**kwargs):
    """Skill 진입점 — 예정 시간이 된 글을 찾아 게시."""
    from ._poster import check_and_post_due

    results = check_and_post_due()

    if not results:
        return None  # 게시할 글 없음

    # 텔레그램 알림
    from ...core.config import get_env_path
    from dotenv import load_dotenv
    import os

    load_dotenv(get_env_path())
    chat_id_str = os.getenv("TELEGRAM_ALLOWED_USERS", "0").split(",")[0].strip()
    if not chat_id_str:
        return results

    chat_id = int(chat_id_str)
    from ...channels.telegram import send_message_sync

    for r in results:
        if r["success"]:
            send_message_sync(chat_id, f"스레드 자동 게시 완료: {r['title']}")
        else:
            send_message_sync(chat_id, f"스레드 게시 실패: {r['title']}\n{r.get('error', '')}")

    return results
