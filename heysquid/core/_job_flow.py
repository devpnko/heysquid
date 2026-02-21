"""
heysquid.core._job_flow — job lifecycle (reserve / report / mark_done).

Functions:
- reserve_memory_telegram
- report_telegram
- mark_done_telegram
- _format_file_size
"""

import os
from datetime import datetime

from ..channels._msg_store import load_telegram_messages, save_telegram_messages, load_and_modify, save_bot_response
from ._working_lock import _dashboard_log, load_new_instructions, clear_new_instructions
from ..memory.tasks import get_task_dir, update_index
from ..channels.telegram import send_files_sync


def _format_file_size(size_bytes):
    """파일 크기를 사람이 읽기 쉬운 형식으로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"


def reserve_memory_telegram(instruction, chat_id, timestamp, message_id):
    """작업 시작 시 즉시 메모리 예약"""
    if isinstance(message_id, list):
        message_ids = message_id
        main_message_id = message_ids[0]
        timestamps = timestamp if isinstance(timestamp, list) else [timestamp] * len(message_ids)
    else:
        message_ids = [message_id]
        main_message_id = message_id
        timestamps = [timestamp]

    task_dir = get_task_dir(main_message_id)
    filepath = os.path.join(task_dir, "task_info.txt")

    now = datetime.now()

    if len(message_ids) > 1:
        msg_id_info = f"{', '.join(map(str, message_ids))} (합산 {len(message_ids)}개)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id_info}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜]
{msg_date_info}
[지시] {instruction}
[결과] (작업 진행 중...)
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    update_index(
        message_id=main_message_id,
        instruction=instruction,
        result_summary="(작업 진행 중...)",
        files=[],
        chat_id=chat_id,
        timestamp=timestamps[0]
    )

    for i, (msg_id, ts) in enumerate(zip(message_ids[1:], timestamps[1:]), 2):
        ref_dir = get_task_dir(msg_id)
        ref_file = os.path.join(ref_dir, "task_info.txt")
        ref_content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜] {ts}
[지시] (메인 작업 msg_{main_message_id}에 합산됨)
[참조] tasks/msg_{main_message_id}/
[결과] (작업 진행 중...)
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(msg_{main_message_id}에 합산됨)",
            result_summary="(작업 진행 중...)",
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] 메모리 예약 완료: {task_dir}/task_info.txt")
    if len(message_ids) > 1:
        print(f"   합산 메시지: {len(message_ids)}개 ({', '.join(map(str, message_ids))})")


def report_telegram(instruction, result_text, chat_id, timestamp, message_id, files=None):
    """작업 결과를 텔레그램으로 전송하고 메모리에 저장"""
    if isinstance(message_id, list):
        message_ids = message_id
        main_message_id = message_ids[0]
        timestamps = timestamp if isinstance(timestamp, list) else [timestamp] * len(message_ids)
    else:
        message_ids = [message_id]
        main_message_id = message_id
        timestamps = [timestamp]

    message = result_text

    if files:
        file_names = [os.path.basename(f) for f in files]
        message += f"\n\n📎 {', '.join(file_names)}"

    if len(message_ids) > 1:
        message += f"\n\n_{len(message_ids)}개 메시지 합산 처리_"

    print(f"\n[SEND] 텔레그램으로 결과 전송 중... (chat_id: {chat_id})")
    _dashboard_log('pm', 'Mission complete — sending report')
    success = send_files_sync(chat_id, message, files or [])

    if success:
        print("[OK] 결과 전송 완료!")
        save_bot_response(
            chat_id=chat_id,
            text=message,
            reply_to_message_ids=message_ids,
            files=[os.path.basename(f) for f in (files or [])]
        )
    else:
        print("[ERROR] 결과 전송 실패!")
        result_text = f"[전송 실패] {result_text}"
        files = []

    task_dir = get_task_dir(main_message_id)
    filepath = os.path.join(task_dir, "task_info.txt")

    now = datetime.now()

    if len(message_ids) > 1:
        msg_id_info = f"{', '.join(map(str, message_ids))} (합산 {len(message_ids)}개)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id_info}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜]
{msg_date_info}
[지시] {instruction}
[결과] {result_text}
"""

    if files:
        file_names = [os.path.basename(f) for f in files]
        content += f"[보낸파일] {', '.join(file_names)}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    update_index(
        message_id=main_message_id,
        instruction=instruction,
        result_summary=result_text[:100],
        files=[os.path.basename(f) for f in (files or [])],
        chat_id=chat_id,
        timestamp=timestamps[0]
    )

    for i, (msg_id, ts) in enumerate(zip(message_ids[1:], timestamps[1:]), 2):
        ref_dir = get_task_dir(msg_id)
        ref_file = os.path.join(ref_dir, "task_info.txt")
        ref_content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜] {ts}
[지시] (메인 작업 msg_{main_message_id}에 합산됨)
[참조] tasks/msg_{main_message_id}/
[결과] {result_text[:100]}...
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(msg_{main_message_id}에 합산됨)",
            result_summary=result_text[:100],
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] 메모리 저장 완료: {task_dir}/task_info.txt")


def mark_done_telegram(message_id):
    """텔레그램 메시지 처리 완료 표시 — flock 사용"""
    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    new_instructions = load_new_instructions()
    if new_instructions:
        print(f"[LOG] 작업 중 추가된 지시사항 {len(new_instructions)}개 함께 처리")
        for inst in new_instructions:
            message_ids.append(inst["message_id"])

    ids_set = set(message_ids)

    def _mark_done(data):
        for msg in data.get("messages", []):
            if msg["message_id"] in ids_set:
                msg["processed"] = True
        return data

    load_and_modify(_mark_done)
    clear_new_instructions()

    if len(message_ids) > 1:
        print(f"[DONE] 메시지 {len(message_ids)}개 처리 완료 표시: {', '.join(map(str, message_ids))}")
    else:
        print(f"[DONE] 메시지 {message_ids[0]} 처리 완료 표시")
