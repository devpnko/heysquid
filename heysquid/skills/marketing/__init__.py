"""
HYPERS 마케팅 콘텐츠 생성 스킬 — heysquid

스레드/X에 게시할 HYPERS 홍보 콘텐츠를 생성합니다.
리서치 기반 훅 패턴 + 사전 작성된 40개 콘텐츠에서 선택.

카테고리:
- ai_tip (20개): AI 활용 팁으로 팔로워 확보
- host_recruit (5개): 은둔 고수 호스트 섭외
- participant (10개): 참여자 유입 유도
- fomo (5개): 기대감 증폭

사용법:
    텔레그램: "HYPERS 마케팅 콘텐츠 만들어줘"
    수동: python -c "from heysquid.skills.marketing import execute; execute()"
"""

SKILL_META = {
    "name": "marketing",
    "description": "HYPERS 마케팅 콘텐츠 생성 (스레드/X)",
    "trigger": "manual",
    "enabled": True,
}


def execute(**kwargs) -> dict:
    """스킬 진입점 — 콘텐츠 생성 + 텔레그램 전송 + 파일 저장.

    kwargs:
        triggered_by: "scheduler" | "manual" | "pm"
        chat_id: int (텔레그램 전송용)
        args: str (카테고리 지정 등)
            예: "ai_tip 5" → ai_tip 카테고리에서 5개
    """
    from ._content_generator import generate_drafts, format_drafts_for_telegram, save_drafts

    # args 파싱
    args_str = kwargs.get("args", "")
    category = None
    count = 3

    if args_str:
        parts = args_str.strip().split()
        for part in parts:
            if part in ("ai_tip", "host_recruit", "participant", "fomo"):
                category = part
            elif part.isdigit():
                count = min(int(part), 10)

    # 콘텐츠 생성
    drafts = generate_drafts(n=count, category=category)

    if not drafts:
        return {"ok": False, "message": "콘텐츠 생성 실패"}

    # 파일 저장
    file_path = save_drafts(drafts)

    # 텔레그램 전송 (chat_id가 있을 때)
    chat_id = kwargs.get("chat_id", 0)
    if chat_id:
        try:
            from ...channels.telegram import send_message_sync
            telegram_text = format_drafts_for_telegram(drafts)
            send_message_sync(int(chat_id), telegram_text, parse_mode=None)
        except Exception as e:
            print(f"[WARN] 텔레그램 전송 실패: {e}")

    return {
        "ok": True,
        "count": len(drafts),
        "file": file_path,
        "drafts": [
            {"id": d["id"], "category": d["category"]}
            for d in drafts
        ],
    }
