"""
heysquid.channels.discord_listener — Discord Gateway listener.

역할:
- Discord 메시지 수신 (Gateway Bot — MESSAGE_CONTENT Intent 필수!)
- 첨부파일 다운로드
- messages.json에 통합 스키마로 저장
- 다른 채널로 브로드캐스트 (전체 동기화)
- trigger_executor() 호출

사용법:
    python -m heysquid.channels.discord_listener
"""

import os
import re
import signal
import sys
import time
import asyncio
from datetime import datetime

from dotenv import load_dotenv

# 프로젝트 루트에서 .env 로드
_this_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(os.path.dirname(_this_dir))
sys.path.insert(0, _project_root)

from heysquid.config import get_env_path
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ALLOWED_USERS = [u.strip() for u in os.getenv("DISCORD_ALLOWED_USERS", "").split(",") if u.strip()]
ALLOWED_CHANNELS = [c.strip() for c in os.getenv("DISCORD_ALLOWED_CHANNELS", "").split(",") if c.strip()]

# 중단 키워드
STOP_KEYWORDS = {"멈춰", "스탑", "중단", "/stop", "잠깐만", "그만", "취소", "stop"}

# 파일 다운로드 경로
DATA_DIR = os.path.join(_project_root, "data")
DOWNLOAD_DIR = os.path.join(DATA_DIR, "downloads")


def _download_discord_attachment_sync(url, filename):
    """Discord 첨부파일 다운로드 (동기 — thread에서 실행)"""
    import requests

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    ts = int(time.time())
    local_path = os.path.join(DOWNLOAD_DIR, f"discord_{ts}_{safe_name}")

    try:
        # H-8 스타일: 스트리밍 다운로드
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return local_path
    except Exception as e:
        print(f"[DISCORD] 파일 다운로드 실패: {e}")
        return None


async def _download_discord_attachment(attachment):
    """Discord 첨부파일 다운로드 (H-3: 비동기 래퍼 — 이벤트 루프 블로킹 방지)"""
    return await asyncio.to_thread(
        _download_discord_attachment_sync, attachment.url, attachment.filename
    )


def main():
    """Discord listener 메인 — Gateway Bot"""
    if not BOT_TOKEN:
        print("[DISCORD] DISCORD_BOT_TOKEN 미설정")
        print("   .env에 DISCORD_BOT_TOKEN을 설정하세요.")
        sys.exit(1)

    # discord.py를 discord_lib로 import (D4 — 이름 충돌 방지)
    import discord as discord_lib

    intents = discord_lib.Intents.default()
    intents.message_content = True  # 필수! (D3)
    client = discord_lib.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"[DISCORD] {client.user} 연결됨 (Gateway)")
        print(f"[DISCORD] 허용 사용자: {ALLOWED_USERS or '전체'}")
        if ALLOWED_CHANNELS:
            print(f"[DISCORD] 허용 채널: {ALLOWED_CHANNELS}")

    @client.event
    async def on_message(message):
        # 1. 봇 자기 메시지 무시 (에코 루프 방지)
        if message.author.bot:
            return

        user_id = str(message.author.id)
        channel_id = str(message.channel.id)

        # 2. 허용 사용자 체크
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            return

        # 3. 허용 채널 체크 (설정된 경우)
        if ALLOWED_CHANNELS and channel_id not in ALLOWED_CHANNELS:
            return

        text = message.content or ""

        # D3: MESSAGE_CONTENT Intent 경고
        if not text and not message.attachments:
            print("[DISCORD] 빈 메시지 — MESSAGE_CONTENT Intent 비활성화 의심!")
            return

        # message_id: 채널 prefix 부착 (P1)
        msg_id = f"discord_{message.id}"

        # 4. 중단 명령어 체크
        text_lower = text.lower().strip()
        if text_lower in STOP_KEYWORDS:
            await _handle_stop(message, msg_id)
            return

        # 5. 첨부파일 다운로드 (H-3: await로 이벤트 루프 비블로킹)
        files = []
        for attachment in message.attachments:
            local_path = await _download_discord_attachment(attachment)
            if local_path:
                file_type = "photo" if attachment.content_type and attachment.content_type.startswith("image/") else "document"
                files.append({
                    "path": local_path,
                    "name": attachment.filename,
                    "size": attachment.size,
                    "type": file_type,
                })

        # 6. 사용자 이름
        user_name = message.author.display_name or str(message.author)

        # 7. 통합 스키마 변환
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {
            "message_id": msg_id,
            "channel": "discord",
            "chat_id": channel_id,
            "text": text,
            "type": "user",
            "first_name": user_name,
            "timestamp": now,
            "processed": False,
            "files": files if files else [],
        }

        # 8. messages.json에 저장 (flock atomic, H-3: to_thread로 비블로킹)
        from heysquid.channels._msg_store import load_and_modify

        def _append_msg(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        await asyncio.to_thread(load_and_modify, _append_msg)

        print(f"[DISCORD] 메시지 저장: {user_name}: {text[:50]}...")

        # 9. ✅ 리액션 수신 확인 (T1)
        try:
            await message.add_reaction("✅")
        except Exception:
            pass

        # 10. 다른 채널에 브로드캐스트 (전체 동기화, H-3: to_thread)
        try:
            from heysquid.channels._router import broadcast_user_message, broadcast_files
            if text:
                await asyncio.to_thread(
                    broadcast_user_message, text,
                    source_channel="discord", sender_name=user_name,
                )
            if files:
                local_paths = [f["path"] for f in files if f.get("path")]
                if local_paths:
                    await asyncio.to_thread(
                        broadcast_files, local_paths,
                        exclude_channels={"discord"},
                    )
        except Exception as e:
            print(f"[DISCORD] 브로드캐스트 실패 (Discord 처리에는 영향 없음): {e}")

        # 11. trigger_executor() (H-3: to_thread)
        try:
            from heysquid.channels._base import trigger_executor
            await asyncio.to_thread(trigger_executor)
        except Exception as e:
            print(f"[DISCORD] trigger_executor 실패: {e}")

    async def _handle_stop(message, msg_id):
        """중단 명령어 처리"""
        import subprocess

        print(f"[DISCORD] 중단 명령 수신: {message.content}")

        # 메시지 저장
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message_data = {
            "message_id": msg_id,
            "channel": "discord",
            "chat_id": str(message.channel.id),
            "text": message.content,
            "type": "user",
            "first_name": message.author.display_name,
            "timestamp": now,
            "processed": True,
        }
        from heysquid.channels._msg_store import load_and_modify

        def _append_msg(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        await asyncio.to_thread(load_and_modify, _append_msg)

        # Claude 프로세스 kill (H-3: subprocess는 to_thread 불필요 — 빠름)
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
                print(f"[DISCORD] Claude 프로세스 중단: {pids}")

                # interrupted 파일 생성
                from heysquid.core._working_lock import check_working_lock
                lock_info = check_working_lock()
                if lock_info:
                    from heysquid.paths import INTERRUPTED_FILE
                    import json
                    import tempfile
                    interrupted_data = {
                        "reason": "user_stop",
                        "stopped_at": now,
                        "channel": "discord",
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

                await message.channel.send("작업을 중단했습니다.")
            else:
                await message.channel.send("진행 중인 작업이 없습니다.")
        except Exception as e:
            print(f"[DISCORD] 중단 처리 실패: {e}")

    # M-8: SIGTERM 핸들러 — discord.py의 close()를 통해 정상 종료
    def shutdown(signum, frame):
        print(f"\n[DISCORD] 시그널 {signum} 수신 — 정상 종료 시작")
        asyncio.ensure_future(client.close())

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    print("[DISCORD] Gateway listener 시작...")
    client.run(BOT_TOKEN)  # 블로킹


if __name__ == "__main__":
    main()
