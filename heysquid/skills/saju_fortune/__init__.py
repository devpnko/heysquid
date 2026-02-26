"""
띠별 일일 운세 생성 스킬 — heysquid

일진(天干地支) 기반 12띠 운세를 생성하여
Threads/X에 게시할 수 있는 포맷으로 출력합니다.

사용법:
    텔레그램: "오늘 운세 만들어줘"
    수동: python -c "from heysquid.skills.saju_fortune import execute; print(execute())"
"""

from datetime import date

SKILL_META = {
    "name": "saju_fortune",
    "description": "띠별 일일 운세 생성 (일진 기반)",
    "trigger": "manual",
    "enabled": True,
}


def execute(**kwargs) -> dict:
    """스킬 진입점 — 오늘의 띠별 운세 생성 + 텔레그램 전송.

    kwargs:
        triggered_by: "scheduler" | "manual" | "pm"
        chat_id: int (텔레그램 전송용)
        args: str (날짜 지정, 예: "2026-02-27")
    """
    from .zodiac_fortune import (
        generate_daily_zodiac_fortune,
        format_thread_post,
    )

    # args에서 날짜 파싱 (없으면 오늘)
    args_str = kwargs.get("args", "").strip()
    target = date.today()
    if args_str:
        try:
            target = date.fromisoformat(args_str)
        except ValueError:
            pass

    # 운세 생성
    fortune_data = generate_daily_zodiac_fortune(target)
    thread_text = format_thread_post(fortune_data)

    # 텔레그램 전송 (chat_id가 있을 때)
    chat_id = kwargs.get("chat_id", 0)
    if chat_id:
        try:
            from ...channels.telegram import send_message_sync
            send_message_sync(int(chat_id), thread_text, parse_mode=None)
        except Exception as e:
            print(f"[WARN] 텔레그램 전송 실패: {e}")

    return {
        "ok": True,
        "date": fortune_data["date"],
        "day_pillar": fortune_data["day_pillar"],
        "text": thread_text,
        "text_length": len(thread_text),
    }
