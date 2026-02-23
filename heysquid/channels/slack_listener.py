"""
heysquid.channels.slack_listener — Slack Socket Mode listener.

역할:
- Slack 메시지/멘션 수신 (Socket Mode — WebSocket, 공개 IP 불필요)
- 파일 다운로드 (Bearer 인증)
- messages.json에 통합 스키마로 저장
- 다른 채널로 브로드캐스트 (전체 동기화)
- trigger_executor() 호출

사용법:
    python -m heysquid.channels.slack_listener
"""

import os
import re
import signal
import sys
import time
import requests
from datetime import datetime

from dotenv import load_dotenv

from heysquid.core.config import get_env_path, DATA_DIR_STR
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
ALLOWED_USERS = [u.strip() for u in os.getenv("SLACK_ALLOWED_USERS", "").split(",") if u.strip()]

# 중단 키워드 (telegram_listener와 동일)
STOP_KEYWORDS = {"멈춰", "스탑", "중단", "/stop", "잠깐만", "그만", "취소", "stop"}

# 파일 다운로드 경로
DATA_DIR = DATA_DIR_STR
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")


def _download_slack_file(url_private, filename):
    """Slack 파일 다운로드 (Bearer 토큰 인증, S5)"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    ts = int(time.time())
    local_path = os.path.join(DOWNLOAD_DIR, f"slack_{ts}_{safe_name}")

    try:
        # H-8: 스트리밍 다운로드 (대용량 파일 메모리 보호)
        resp = requests.get(
            url_private,
            headers={"Authorization": f"Bearer {BOT_TOKEN}"},
            timeout=30,
            stream=True,
        )
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path
    except Exception as e:
        print(f"[SLACK] 파일 다운로드 실패: {e}")
        return None


def _strip_mention(text, bot_user_id):
    """<@BOT_ID> 멘션 제거 (S3)"""
    if bot_user_id:
        text = text.replace(f"<@{bot_user_id}>", "").strip()
    return text


_user_name_cache = {}  # H-7: 실제 캐시 구현


def _get_user_name(client, user_id):
    """Slack 사용자 이름 조회 (H-7: 캐시 적용)"""
    if user_id in _user_name_cache:
        return _user_name_cache[user_id]
    try:
        result = client.users_info(user=user_id)
        profile = result["user"]["profile"]
        name = profile.get("display_name") or profile.get("real_name") or user_id
        _user_name_cache[user_id] = name
        return name
    except Exception:
        return user_id


def _handle_message(event, client, bot_user_id):
    """메시지 처리 핵심 로직"""
    # 1. 봇 자기 메시지 무시 (S8 에코 루프 방지)
    if event.get("bot_id"):
        return
    if event.get("subtype") in ("bot_message", "message_changed", "message_deleted"):
        return

    user_id = event.get("user", "")

    # 2. 허용 사용자 체크
    if ALLOWED_USERS and user_id not in ALLOWED_USERS:
        print(f"[SLACK] 비허용 사용자: {user_id}")
        return

    raw_text = event.get("text", "")
    text = _strip_mention(raw_text, bot_user_id)

    if not text and not event.get("files"):
        # D3 스타일: 빈 메시지 경고
        print("[SLACK] 빈 메시지 수신 — 무시")
        return

    channel_id = event.get("channel", "")
    event_ts = event.get("ts", "")
    thread_ts = event.get("thread_ts")

    # message_id: 채널 prefix 부착 (P1)
    message_id = f"slack_{event_ts.replace('.', '')}"

    # 3. 중단 명령어 체크
    text_lower = text.lower().strip()
    if text_lower in STOP_KEYWORDS:
        _handle_stop(client, channel_id, event_ts, message_id, user_id, text)
        return

    # 4. 파일 다운로드 (S5)
    files = []
    for file_info in event.get("files", []):
        url = file_info.get("url_private", "")
        name = file_info.get("name", "unknown")
        size = file_info.get("size", 0)
        mimetype = file_info.get("mimetype", "")
        if url:
            local_path = _download_slack_file(url, name)
            if local_path:
                file_type = "photo" if mimetype.startswith("image/") else "document"
                files.append({
                    "path": local_path,
                    "name": name,
                    "size": size,
                    "type": file_type,
                })

    # 5. 사용자 이름
    user_name = _get_user_name(client, user_id)

    # 6. 통합 스키마 변환
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "message_id": message_id,
        "channel": "slack",
        "chat_id": channel_id,
        "text": text,
        "type": "user",
        "first_name": user_name,
        "timestamp": now,
        "processed": False,
        "files": files if files else [],
    }
    if thread_ts:
        message_data["thread_ts"] = thread_ts

    # 7. messages.json에 저장 (flock atomic)
    from ._msg_store import load_and_modify

    def _append_msg(data):
        existing_ids = {m["message_id"] for m in data.get("messages", [])}
        if message_data["message_id"] not in existing_ids:
            data["messages"].append(message_data)
        return data
    load_and_modify(_append_msg)

    print(f"[SLACK] 메시지 저장: {user_name}: {text[:50]}...")

    # 8. ✅ 리액션 수신 확인 (T1)
    try:
        client.reactions_add(
            channel=channel_id,
            name="white_check_mark",
            timestamp=event_ts,
        )
    except Exception:
        pass  # 이미 리액션이 있거나 권한 없으면 무시

    # 9. 다른 채널에 브로드캐스트 (전체 동기화)
    try:
        from ._router import broadcast_user_message, broadcast_files
        if text:
            broadcast_user_message(text, source_channel="slack", sender_name=user_name)
        if files:
            local_paths = [f["path"] for f in files if f.get("path")]
            if local_paths:
                broadcast_files(local_paths, exclude_channels={"slack"})
    except Exception as e:
        print(f"[SLACK] 브로드캐스트 실패 (Slack 처리에는 영향 없음): {e}")

    # 10. trigger_executor()
    try:
        from ._base import trigger_executor
        trigger_executor()
    except Exception as e:
        print(f"[SLACK] trigger_executor 실패: {e}")


def _handle_stop(client, channel_id, event_ts, message_id, user_id, text):
    """중단 명령어 처리"""
    import subprocess

    print(f"[SLACK] 중단 명령 수신: {text}")

    # 메시지 저장
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_data = {
        "message_id": message_id,
        "channel": "slack",
        "chat_id": channel_id,
        "text": text,
        "type": "user",
        "first_name": _get_user_name(client, user_id),
        "timestamp": now,
        "processed": True,
    }
    from ._msg_store import load_and_modify

    def _append_msg(data):
        existing_ids = {m["message_id"] for m in data.get("messages", [])}
        if message_data["message_id"] not in existing_ids:
            data["messages"].append(message_data)
        return data
    load_and_modify(_append_msg)

    # Claude 프로세스 kill
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            for pid in pids:
                if pid.strip():
                    subprocess.run(["kill", "-TERM", pid.strip()])
            print(f"[SLACK] Claude 프로세스 중단: {pids}")

            # interrupted 파일 생성
            from ..core._working_lock import check_working_lock
            lock_info = check_working_lock()
            if lock_info:
                from ..paths import INTERRUPTED_FILE
                import json
                import tempfile
                interrupted_data = {
                    "reason": "user_stop",
                    "stopped_at": now,
                    "channel": "slack",
                    "previous_work": lock_info,
                }
                # C-6: 원자적 쓰기 (tmp + fsync + rename)
                fd, tmp = tempfile.mkstemp(
                    dir=os.path.dirname(INTERRUPTED_FILE), suffix=".tmp"
                )
                with os.fdopen(fd, "w") as f:
                    json.dump(interrupted_data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.rename(tmp, INTERRUPTED_FILE)

            client.chat_postMessage(channel=channel_id, text="작업을 중단했습니다.")
        else:
            client.chat_postMessage(channel=channel_id, text="진행 중인 작업이 없습니다.")
    except Exception as e:
        print(f"[SLACK] 중단 처리 실패: {e}")


def main():
    """Slack listener 메인 — Socket Mode"""
    if not BOT_TOKEN or not APP_TOKEN:
        print("[SLACK] SLACK_BOT_TOKEN 또는 SLACK_APP_TOKEN 미설정")
        print("   .env에 SLACK_BOT_TOKEN과 SLACK_APP_TOKEN을 설정하세요.")
        sys.exit(1)

    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=BOT_TOKEN)

    # 봇 자기 user_id 조회
    bot_user_id = None
    try:
        auth = app.client.auth_test()
        bot_user_id = auth.get("user_id")
        print(f"[SLACK] 봇 인증 완료: {auth.get('user', 'unknown')} ({bot_user_id})")
    except Exception as e:
        print(f"[SLACK] 봇 인증 실패: {e}")
        sys.exit(1)

    @app.event("message")
    def on_message(event, client):
        _handle_message(event, client, bot_user_id)

    @app.event("app_mention")
    def on_mention(event, client):
        # H-2: message 이벤트가 이미 app_mention을 포함하므로
        # 여기서는 중복 처리하지 않는다 (채널 message에 멘션이 포함됨)
        pass

    # SIGTERM 핸들러
    def shutdown(signum, frame):
        print(f"\n[SLACK] 시그널 {signum} 수신 — 종료")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("[SLACK] Socket Mode listener 시작...")
    print(f"[SLACK] 허용 사용자: {ALLOWED_USERS or '전체'}")

    handler = SocketModeHandler(app, APP_TOKEN)
    handler.start()  # 블로킹


if __name__ == "__main__":
    main()
