"""
Hello World 예시 스킬 — 새 스킬 만들 때 참고용.

이 파일을 복사해서 heysquid/skills/{your_skill}/__init__.py 로 만들면
플러그인 로더가 자동으로 인식합니다.

사용법:
    TUI: /skill hello_world
    코드: from heysquid.skills import run_skill; run_skill("hello_world")
"""

from datetime import datetime

SKILL_META = {
    "name": "hello_world",
    "description": "예시 스킬 — 새 스킬 작성 참고용",
    "trigger": "manual",
    "enabled": True,
}


def execute(**kwargs) -> dict:
    """스킬 진입점.

    kwargs:
        triggered_by: "scheduler" | "manual" | "pm" | "webhook"
        chat_id: int (텔레그램 전송용, 0이면 전송 안 함)
        args: str (사용자 입력 인자)
        payload: dict (webhook JSON body)
        callback_url: str (완료 후 POST할 URL)
    """
    name = kwargs.get("args", "").strip() or "World"
    now = datetime.now().strftime("%H:%M")

    message = f"Hello, {name}! 🐙 현재 시각: {now}"

    # 텔레그램 전송 (chat_id가 있을 때)
    chat_id = kwargs.get("chat_id", 0)
    if chat_id:
        try:
            from ...channels.telegram import send_message_sync
            send_message_sync(int(chat_id), message, parse_mode=None)
        except Exception as e:
            print(f"[WARN] 텔레그램 전송 실패: {e}")

    return {
        "ok": True,
        "message": message,
    }
