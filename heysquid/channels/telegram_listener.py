"""
텔레그램 메시지 수집기 (Listener) — heysquid Mac 포팅

역할:
- 텔레그램 봇 API를 통해 새로운 메시지 수신
- messages.json에 메시지 저장
- 허용된 사용자만 처리
- 중복 메시지 방지

사용법:
    python telegram_listener.py
    (Ctrl+C로 종료)
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest
import asyncio

# 경로 설정 (Mac)
from ..config import DATA_DIR_STR as DATA_DIR, TASKS_DIR_STR as TASKS_DIR, PROJECT_ROOT_STR as PROJECT_ROOT, get_env_path

# .env 파일 로드
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = [int(uid.strip()) for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if uid.strip()]
POLLING_INTERVAL = int(os.getenv("TELEGRAM_POLLING_INTERVAL", "3"))

from ..paths import MESSAGES_FILE, INTERRUPTED_FILE, WORKING_LOCK_FILE, EXECUTOR_LOCK_FILE
# 중단 명령어 — 이 중 하나가 메시지 전체와 일치하면 중단
STOP_KEYWORDS = ["멈춰", "스탑", "중단", "/stop", "잠깐만", "스톱", "그만", "취소"]

from ._msg_store import load_telegram_messages as load_messages, save_telegram_messages as save_messages, load_and_modify, get_cursor, _migrate_cursors
from ._base import trigger_executor as _trigger_executor


def _is_stop_command(text):
    """메시지가 중단 명령어인지 확인"""
    return text.strip().lower() in [kw.lower() for kw in STOP_KEYWORDS]


def _kill_executor():
    """실행 중인 executor Claude 프로세스를 종료"""
    killed = False

    # 1. Claude executor 프로세스 kill
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid.strip():
                    subprocess.run(["kill", pid.strip()], capture_output=True)
                    print(f"[STOP] Claude executor 프로세스 종료: PID {pid.strip()}")
                    killed = True
    except Exception as e:
        print(f"[WARN] 프로세스 kill 실패: {e}")

    # 2. executor.lock 삭제
    if os.path.exists(EXECUTOR_LOCK_FILE):
        try:
            os.remove(EXECUTOR_LOCK_FILE)
            print("[STOP] executor.lock 삭제")
        except OSError:
            pass

    # 3. working.json 읽고 삭제
    working_info = None
    if os.path.exists(WORKING_LOCK_FILE):
        try:
            with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
                working_info = json.load(f)
            os.remove(WORKING_LOCK_FILE)
            print("[STOP] working.json 삭제")
        except Exception:
            pass

    return killed, working_info


async def _handle_stop_command(msg_data):
    """
    중단 명령어 처리 (async — fetch_new_messages 안에서 호출):
    1. executor kill
    2. interrupted.json 저장
    3. 사용자에게 알림
    4. 중단 명령 메시지를 processed로 표시
    """
    chat_id = msg_data["chat_id"]
    message_id = msg_data["message_id"]

    print(f"[STOP] 중단 명령 감지: '{msg_data['text']}' from {msg_data['first_name']}")

    killed, working_info = _kill_executor()

    # interrupted.json 저장
    interrupted_data = {
        "interrupted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": msg_data["text"],
        "by_user": msg_data["first_name"],
        "chat_id": chat_id,
        "previous_work": None
    }

    if working_info:
        interrupted_data["previous_work"] = {
            "instruction": working_info.get("instruction_summary", ""),
            "started_at": working_info.get("started_at", ""),
            "message_id": working_info.get("message_id")
        }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INTERRUPTED_FILE, "w", encoding="utf-8") as f:
        json.dump(interrupted_data, f, ensure_ascii=False, indent=2)
    print(f"[STOP] interrupted.json 저장")

    # 모든 미처리 메시지 processed 처리 (이전 메시지가 다시 실행되지 않도록)
    # 이전 작업 맥락은 interrupted.json에 보존됨 — flock 사용
    cleared = 0
    def _clear_unprocessed(data):
        nonlocal cleared
        for m in data.get("messages", []):
            if not m.get("processed", False):
                m["processed"] = True
                cleared += 1
        return data
    load_and_modify(_clear_unprocessed)
    if cleared:
        print(f"[STOP] 미처리 메시지 {cleared}개 정리 완료")

    # 사용자에게 알림 (async — event loop 충돌 방지)
    from .telegram import send_message

    if working_info:
        task_name = working_info.get("instruction_summary", "알 수 없음")
        reply = f"작업 중단했어요.\n\n중단된 작업: {task_name}\n\n새로운 지시를 보내주세요."
    elif killed:
        reply = "작업 중단했어요. 새로운 지시를 보내주세요."
    else:
        reply = "현재 실행 중인 작업이 없어요."

    await send_message(chat_id, reply)
    print(f"[STOP] 중단 알림 전송 완료")


def setup_bot_token():
    """토큰이 .env에 없으면 사용자에게 입력받아 저장"""
    global BOT_TOKEN

    if BOT_TOKEN and BOT_TOKEN not in ("", "YOUR_BOT_TOKEN", "your_bot_token_here"):
        return True

    print("\n" + "=" * 60)
    print("TELEGRAM_BOT_TOKEN이 .env에 설정되지 않았습니다.")
    print("=" * 60)
    print()
    print("설정 방법:")
    print("   1. 텔레그램에서 @BotFather를 검색하여 시작")
    print("   2. /newbot 명령으로 새 봇 생성")
    print("   3. @BotFather가 주어준 토큰을 아래에 붙여넣기")
    print()
    print("   예시: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ")
    print()

    if not sys.stdin.isatty():
        print("[ERROR] 대화형 환경이 아닙니다. .env 파일에 TELEGRAM_BOT_TOKEN을 직접 설정해주세요.")
        return False

    token = input("봇 토큰 입력: ").strip()

    if not token:
        print("토큰이 비어있습니다. 프로그램을 종료합니다.")
        return False

    from dotenv import set_key

    env_path = get_env_path()
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("")

    set_key(env_path, "TELEGRAM_BOT_TOKEN", token)
    BOT_TOKEN = token
    os.environ["TELEGRAM_BOT_TOKEN"] = token

    print(f"[OK] .env에 TELEGRAM_BOT_TOKEN 저장 완료!")
    print()
    return True


async def download_file(bot, file_id, message_id, file_type, file_name=None):
    """
    텔레그램 파일 다운로드

    Args:
        bot: Telegram Bot 인스턴스
        file_id: 텔레그램 파일 ID
        message_id: 메시지 ID
        file_type: 파일 타입 (photo, document, video, audio, voice)
        file_name: 파일명 (document의 경우)

    Returns:
        str: 다운로드된 파일 경로 (실패 시 None)
    """
    try:
        # tasks/msg_{message_id} 폴더 생성
        task_dir = os.path.join(TASKS_DIR, f"msg_{message_id}")
        os.makedirs(task_dir, exist_ok=True)

        # 파일 정보 가져오기
        file = await bot.get_file(file_id)

        # 파일 확장자 결정
        if file_name:
            filename = file_name
        else:
            file_path = file.file_path
            ext = os.path.splitext(file_path)[1] or '.jpg'

            type_prefix = {
                'photo': 'image',
                'video': 'video',
                'audio': 'audio',
                'voice': 'voice'
            }
            prefix = type_prefix.get(file_type, 'file')
            filename = f"{prefix}_{message_id}{ext}"

        # 파일 다운로드
        local_path = os.path.join(task_dir, filename)
        await file.download_to_drive(local_path)

        print(f"[FILE] 파일 다운로드: {filename} ({file.file_size} bytes)")
        return local_path

    except Exception as e:
        print(f"[ERROR] 파일 다운로드 실패: {e}")
        return None


async def fetch_new_messages():
    """새로운 메시지 가져오기 (텍스트 + 이미지 + 파일 지원)"""
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN 미설정. 프로그램을 종료합니다.")
        return None

    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=15.0,   # long-polling 5초 + 여유 10초
        write_timeout=10.0,
        pool_timeout=5.0
    )
    bot = Bot(token=BOT_TOKEN, get_updates_request=request)
    last_update_id = get_cursor("telegram", "last_update_id")

    try:
        updates = await bot.get_updates(
            offset=last_update_id + 1,
            timeout=5,
            allowed_updates=["message", "callback_query"]
        )

        new_messages = []
        max_update_id = last_update_id

        for update in updates:
            # 인라인 버튼 콜백 처리 (중단 버튼)
            if update.callback_query:
                cq = update.callback_query
                if cq.data == "stop":
                    user = cq.from_user
                    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
                        continue
                    # 콜백 응답 (버튼 로딩 해제)
                    try:
                        await bot.answer_callback_query(cq.id, text="중단 처리 중...")
                    except Exception:
                        pass
                    # 중단 처리
                    stop_data = {
                        "chat_id": cq.message.chat_id,
                        "message_id": cq.message.message_id,
                        "text": "중단",
                        "first_name": user.first_name or "",
                    }
                    await _handle_stop_command(stop_data)
                    if update.update_id > max_update_id:
                        from ._msg_store import set_cursor
                        set_cursor("telegram", "last_update_id", update.update_id)
                    return 0
                continue

            if not update.message:
                continue

            msg = update.message
            user = msg.from_user

            # 허용된 사용자 체크
            if ALLOWED_USERS and user.id not in ALLOWED_USERS:
                print(f"[WARN] 차단: 허용되지 않은 사용자 {user.id} ({user.first_name})")
                continue

            # 텍스트 추출 (caption 또는 text)
            text = msg.caption or msg.text or ""

            # 파일 다운로드
            files = []

            # 사진
            if msg.photo:
                largest_photo = msg.photo[-1]
                file_path = await download_file(
                    bot, largest_photo.file_id, msg.message_id, 'photo'
                )
                if file_path:
                    files.append({
                        "type": "photo",
                        "path": file_path,
                        "size": largest_photo.file_size
                    })

            # 문서
            if msg.document:
                file_path = await download_file(
                    bot, msg.document.file_id, msg.message_id,
                    'document', msg.document.file_name
                )
                if file_path:
                    files.append({
                        "type": "document",
                        "path": file_path,
                        "name": msg.document.file_name,
                        "mime_type": msg.document.mime_type,
                        "size": msg.document.file_size
                    })

            # 비디오
            if msg.video:
                file_path = await download_file(
                    bot, msg.video.file_id, msg.message_id, 'video'
                )
                if file_path:
                    files.append({
                        "type": "video",
                        "path": file_path,
                        "duration": msg.video.duration,
                        "size": msg.video.file_size
                    })

            # 오디오
            if msg.audio:
                file_path = await download_file(
                    bot, msg.audio.file_id, msg.message_id,
                    'audio', msg.audio.file_name
                )
                if file_path:
                    files.append({
                        "type": "audio",
                        "path": file_path,
                        "duration": msg.audio.duration,
                        "size": msg.audio.file_size
                    })

            # 음성 메시지
            if msg.voice:
                file_path = await download_file(
                    bot, msg.voice.file_id, msg.message_id, 'voice'
                )
                if file_path:
                    files.append({
                        "type": "voice",
                        "path": file_path,
                        "duration": msg.voice.duration,
                        "size": msg.voice.file_size
                    })

            # 위치 정보
            location_info = None
            if msg.location:
                location_info = {
                    "latitude": msg.location.latitude,
                    "longitude": msg.location.longitude
                }
                if hasattr(msg.location, 'horizontal_accuracy') and msg.location.horizontal_accuracy:
                    location_info["accuracy"] = msg.location.horizontal_accuracy
                print(f"[LOC] 위치 수신: 위도 {msg.location.latitude}, 경도 {msg.location.longitude}")

            # 텍스트나 파일이나 위치가 하나라도 있어야 처리
            if not text and not files and not location_info:
                continue

            # 메시지 데이터 구성
            message_data = {
                "message_id": msg.message_id,
                "update_id": update.update_id,
                "type": "user",
                "channel": "telegram",
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "chat_id": msg.chat_id,
                "text": text,
                "files": files,
                "location": location_info,
                "timestamp": msg.date.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S"),
                "processed": False
            }

            new_messages.append(message_data)

            if update.update_id > max_update_id:
                max_update_id = update.update_id

        if new_messages:
            # flock 기반 원자적 병합 (lost update 방지)
            def _merge_new(data):
                data = _migrate_cursors(data)
                existing_ids = {m["message_id"] for m in data.get("messages", [])}
                for msg_data in new_messages:
                    if msg_data["message_id"] not in existing_ids:
                        data["messages"].append(msg_data)
                # cursor 업데이트
                if "cursors" not in data:
                    data["cursors"] = {}
                if "telegram" not in data["cursors"]:
                    data["cursors"]["telegram"] = {}
                data["cursors"]["telegram"]["last_update_id"] = max_update_id
                data["last_update_id"] = max_update_id  # 하위 호환
                return data
            load_and_modify(_merge_new)

            for msg in new_messages:
                text_preview = msg['text'][:50] if msg['text'] else "(파일만)" if msg['files'] else "(위치)" if msg.get('location') else ""
                file_info = f" + {len(msg['files'])}개 파일" if msg['files'] else ""
                location_info = f" + 위치 정보" if msg.get('location') else ""
                print(f"[MSG] 새 메시지: [{msg['timestamp']}] {msg['first_name']}: {text_preview}...{file_info}{location_info}")

            # 중단 명령어 감지 — 일반 메시지보다 먼저 처리
            stop_messages = [m for m in new_messages if m['text'] and _is_stop_command(m['text'])]
            if stop_messages:
                await _handle_stop_command(stop_messages[0])
                # 중단 명령은 executor 트리거 안 함 — 0 반환
                return 0

            # 수신 확인 리액션 (messages.json에는 저장하지 않음 — 노이즈 방지)
            from telegram import ReactionTypeEmoji
            for msg in new_messages:
                try:
                    await bot.set_message_reaction(
                        chat_id=msg['chat_id'],
                        message_id=msg['message_id'],
                        reaction=[ReactionTypeEmoji(emoji="👀")]
                    )
                except Exception:
                    pass  # 리액션 실패해도 무시

            # 다른 채널에 릴레이 (전체 동기화 — best-effort)
            try:
                from ._router import broadcast_user_message, broadcast_files
                for msg in new_messages:
                    if msg.get("text"):
                        broadcast_user_message(msg["text"], "telegram", msg.get("first_name", ""))
                    if msg.get("files"):
                        local_paths = [f["path"] for f in msg["files"] if f.get("path")]
                        if local_paths:
                            broadcast_files(local_paths, exclude_channels={"telegram"})
            except Exception as e:
                print(f"[WARN] 브로드캐스트 실패 (TG 처리에는 영향 없음): {e}")

            return len(new_messages)

        return 0

    except Exception as e:
        print(f"[ERROR] 오류: {e}")
        return None


RETRY_MAX = 3


def _cleanup_zombie_pm():
    """좀비 PM 세션 감지 + 정리 — 다중 PM이 동시 실행되면 전부 kill"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return  # PM 프로세스 없음

        pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
        if len(pids) <= 1:
            return  # 단일 세션 — 정상

        # 다중 PM 세션 감지 → 전부 kill
        print(f"[ZOMBIE] 다중 PM 세션 감지: {len(pids)}개 (PIDs: {', '.join(pids)})")
        subprocess.run(
            ["pkill", "-f", "claude.*append-system-prompt-file"],
            capture_output=True
        )
        time.sleep(2)

        # lock 파일 정리
        if os.path.exists(EXECUTOR_LOCK_FILE):
            try:
                os.remove(EXECUTOR_LOCK_FILE)
            except OSError:
                pass

        print(f"[ZOMBIE] {len(pids)}개 좀비 PM 세션 정리 완료. 다음 메시지에서 새 세션 시작됨.")

    except Exception as e:
        print(f"[WARN] 좀비 PM 스캔 실패: {e}")


def _retry_unprocessed():
    """미처리 메시지 확인 + retry_count < 3이면 executor 재트리거 — flock 사용"""
    # PM/executor 실행 중이면 retry 불필요
    if os.path.exists(EXECUTOR_LOCK_FILE):
        return
    if os.path.exists(WORKING_LOCK_FILE):
        return
    if not os.path.exists(MESSAGES_FILE):
        return

    should_trigger = False
    retry_info = ""

    def _bump_retry(data):
        nonlocal should_trigger, retry_info
        retryable = [
            msg for msg in data.get("messages", [])
            if msg.get("type") == "user"
            and not msg.get("processed", False)
            and not msg.get("seen", False)  # seen 메시지는 PM이 처리 중
            and msg.get("retry_count", 0) < RETRY_MAX
        ]
        if not retryable:
            return data
        for msg in retryable:
            msg["retry_count"] = msg.get("retry_count", 0) + 1
        retry_counts = [msg["retry_count"] for msg in retryable]
        retry_info = f"미처리 메시지 {len(retryable)}개 재시도 (retry #{max(retry_counts)})"
        should_trigger = True
        return data

    load_and_modify(_bump_retry)

    if should_trigger:
        print(f"[RETRY] {retry_info}")
        _trigger_executor()


# _trigger_executor는 _base.trigger_executor에서 import됨 (상단 참조)


async def listen_loop():
    """메시지 수신 루프 — 새 메시지 감지 시 executor.sh 즉시 트리거"""
    print("=" * 60)
    print("heysquid - 텔레그램 메시지 수집기 시작")
    print("=" * 60)

    if not setup_bot_token():
        return

    # 봇 커맨드 메뉴 등록 (/stop)
    from .telegram import register_bot_commands_sync
    register_bot_commands_sync()

    print(f"폴링 간격: {POLLING_INTERVAL}초")
    print(f"허용된 사용자: {ALLOWED_USERS}")
    print(f"메시지 저장 파일: {MESSAGES_FILE}")
    print("\n대기 중... (Ctrl+C로 종료)\n")

    cycle_count = 0

    try:
        while True:
            cycle_count += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            result = await fetch_new_messages()

            if result is None:
                print(f"[{now}] #{cycle_count} - 오류 발생, 재시도 대기...")
            elif result > 0:
                print(f"[{now}] #{cycle_count} - {result}개 메시지 수집")
                _trigger_executor()
            else:
                if cycle_count % 30 == 0:
                    print(f"[{now}] #{cycle_count} - 대기 중...")

            # 60사이클(~10분)마다 미처리 메시지 재트리거 + 좀비 PM 스캔
            if cycle_count % 60 == 0:
                _cleanup_zombie_pm()
                _retry_unprocessed()

            await asyncio.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n종료 신호 감지. 프로그램을 종료합니다.")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(listen_loop())
