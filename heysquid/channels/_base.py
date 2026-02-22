"""heysquid.channels._base — abstract channel adapter + listener."""

import os
import subprocess
from abc import ABC, abstractmethod

from ._msg_store import load_and_modify


class ChannelAdapter(ABC):
    """Base class for messaging channel integrations."""

    @abstractmethod
    def send_message(self, chat_id, text, **kwargs):
        ...

    @abstractmethod
    def send_file(self, chat_id, file_path, **kwargs):
        ...


class ChannelListener(ABC):
    """Base class for channel message listeners."""

    channel_name: str  # "telegram", "slack", "discord"

    @abstractmethod
    async def fetch_new_messages(self):
        """새 메시지 폴링/수신. 반환: 수신 수, None=에러"""
        ...

    @abstractmethod
    async def handle_stop_command(self, msg_data: dict):
        """중단 명령어 처리"""
        ...

    @abstractmethod
    async def listen_loop(self):
        """메인 루프"""
        ...

    def save_message(self, message_data: dict):
        """공통: messages.json에 메시지 저장 (flock atomic)"""
        def _append(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        load_and_modify(_append)


def trigger_executor():
    """executor.sh를 백그라운드 프로세스로 실행 (stale lock 자동 정리 + 원자적 선점)

    공통 함수: 모든 채널 listener가 사용.
    """
    from ..paths import EXECUTOR_LOCK_FILE
    from ..config import PROJECT_ROOT_STR as PROJECT_ROOT

    lockfile = EXECUTOR_LOCK_FILE
    if os.path.exists(lockfile):
        has_claude = subprocess.run(
            ["pgrep", "-f", "append-system-prompt-file"],
            capture_output=True,
        ).returncode == 0
        if has_claude:
            print("[TRIGGER] executor 이미 실행 중 — 스킵")
            return
        try:
            os.remove(lockfile)
            print("[TRIGGER] stale executor.lock 제거됨")
        except OSError:
            pass

    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pre-lock by listener PID {os.getpid()}\n".encode())
        os.close(fd)
    except FileExistsError:
        print("[TRIGGER] 다른 트리거가 이미 lock 선점 — 스킵")
        return

    executor = os.path.join(PROJECT_ROOT, "scripts", "executor.sh")
    if not os.path.exists(executor):
        print(f"[ERROR] executor.sh not found: {executor}")
        try:
            os.remove(lockfile)
        except OSError:
            pass
        return

    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "executor.log")

    print("[TRIGGER] executor.sh 백그라운드 실행!")
    try:
        with open(log_file, "a") as lf:
            subprocess.Popen(
                ["bash", executor],
                stdout=lf,
                stderr=lf,
                cwd=PROJECT_ROOT,
                start_new_session=True,
            )
    except Exception as e:
        # H-9: Popen 실패 시 lock 파일 정리
        print(f"[ERROR] executor.sh 실행 실패: {e}")
        try:
            os.remove(lockfile)
        except OSError:
            pass
