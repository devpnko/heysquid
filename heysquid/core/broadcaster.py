"""
heysquid.core.broadcaster — PM 응답 브로드캐스트.

orchestrator.py의 reply_telegram/report_telegram이 위임하는 채널 전송 레이어.
전체 동기화 모델: PM 응답은 항상 모든 채널에 전송.
"""

from ..channels._msg_store import load_and_modify, save_bot_response
from ..channels._router import broadcast_all, broadcast_files


def reply_broadcast(chat_id, message_id, text):
    """PM 응답 — 전체 채널 브로드캐스트.

    기존 reply_telegram()의 broadcast 버전.
    하나라도 채널 전송 성공이면 processed 마킹.

    Args:
        chat_id: 원본 채팅 ID
        message_id: 응답 대상 메시지 ID (int 또는 list)
        text: 응답 텍스트
    Returns:
        bool: 하나라도 전송 성공이면 True
    """
    ids = message_id if isinstance(message_id, list) else [message_id]
    ids_set = set(ids)

    # C-2: 계획서 순서 — "전송 → 성공 시 마킹"
    # 1. 전체 채널에 전송
    results = broadcast_all(text)
    success = any(results.values()) if results else False

    # 채널이 하나도 등록 안 되어있으면 (테스트 등) 텔레그램 직접 전송 시도
    if not results:
        try:
            from ..channels.telegram import send_message_sync
            success = send_message_sync(chat_id, text, _save=False)
        except Exception:
            success = False

    # 2. 전송 성공 시에만 processed 마킹 + 봇 응답 기록
    if success:
        def _mark_processed(data):
            for msg in data.get("messages", []):
                if msg["message_id"] in ids_set:
                    msg["processed"] = True
            return data
        load_and_modify(_mark_processed)

        save_bot_response(chat_id, text, ids, channel="broadcast")

    return success


def report_broadcast(instruction, result_text, chat_id, timestamp, message_id, files=None):
    """작업 완료 리포트 — 전체 채널에 브로드캐스트.

    기존 report_telegram()에서 전송 부분만 broadcast로 교체.
    메모리 저장 로직은 _job_flow.report_telegram()에 그대로 유지.
    """
    import os
    from ._working_lock import _dashboard_log

    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    message = result_text
    if files:
        file_names = [os.path.basename(f) for f in files]
        message += f"\n\n[FILE] {', '.join(file_names)}"

    if len(message_ids) > 1:
        message += f"\n\n_{len(message_ids)}개 메시지 합산 처리_"

    print(f"\n[SEND] 전체 채널로 결과 전송 중...")
    _dashboard_log('pm', 'Mission complete — broadcasting report')

    # 텍스트 리포트 → 전체 채널
    results = broadcast_all(message)
    success = any(results.values()) if results else False

    # 채널 미등록 시 텔레그램 직접 전송
    if not results:
        try:
            from ..channels.telegram import send_files_sync
            success = send_files_sync(chat_id, message, files or [])
        except Exception:
            success = False
    else:
        # 파일 있으면 → 전체 채널
        if files and success:
            broadcast_files(files)

    if success:
        print("[OK] 결과 전송 완료!")
        save_bot_response(
            chat_id=chat_id,
            text=message,
            reply_to_message_ids=message_ids,
            files=[os.path.basename(f) for f in (files or [])],
            channel="broadcast"
        )
    else:
        print("[ERROR] 결과 전송 실패!")

    return success
