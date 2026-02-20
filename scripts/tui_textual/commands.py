"""커맨드 실행 — 메시지 전송, squad 관리, executor 제어"""

import json
import os
import re
import subprocess
from collections import deque
from datetime import datetime

from heysquid.core.agents import AGENTS, KRAKEN_CREW_NAMES

from .utils import AGENT_ORDER, parse_mentions
from .data_poller import (
    ROOT, STATUS_FILE, MESSAGES_FILE, EXECUTOR_LOCK,
    invalidate_chat_cache,
)

EXECUTOR_SCRIPT = os.path.join(ROOT, "scripts", "executor.sh")
INTERRUPTED_FILE = os.path.join(ROOT, "data", "interrupted.json")
WORKING_LOCK_FILE = os.path.join(ROOT, "data", "working.json")

# .env에서 BOT_TOKEN 로드
try:
    from dotenv import load_dotenv
    from heysquid.core.config import get_env_path
    load_dotenv(get_env_path())
except ImportError:
    pass
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


def _get_real_user_info(messages: list[dict]) -> dict | None:
    """기존 텔레그램 메시지에서 실제 사용자 정보 조회"""
    for msg in reversed(messages):
        cid = msg.get("chat_id", 0)
        if isinstance(cid, int) and cid > 0 and msg.get("source") != "tui":
            return {
                "chat_id": cid,
                "user_id": msg.get("user_id", 0),
                "username": msg.get("username", "tui"),
                "first_name": msg.get("first_name", "TUI"),
            }
    return None


def inject_local_message(text: str) -> int:
    """messages.json에 TUI 메시지 주입."""
    os.makedirs(os.path.dirname(MESSAGES_FILE), exist_ok=True)

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"messages": [], "last_update_id": 0}

    user_info = _get_real_user_info(data.get("messages", []))

    tui_ids = [
        m["message_id"] for m in data.get("messages", [])
        if isinstance(m.get("message_id"), int) and m["message_id"] < 0
    ]
    new_id = min(tui_ids) - 1 if tui_ids else -1

    message = {
        "message_id": new_id,
        "type": "user",
        "channel": "tui",
        "user_id": user_info["user_id"] if user_info else 0,
        "username": user_info["username"] if user_info else "tui",
        "first_name": user_info["first_name"] if user_info else "TUI",
        "last_name": "",
        "chat_id": user_info["chat_id"] if user_info else 0,
        "text": text,
        "files": [],
        "location": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processed": False,
        "source": "tui",
        "mentions": parse_mentions(text),
    }

    data["messages"].append(message)
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 텔레그램에 포워딩
    chat_id = user_info["chat_id"] if user_info else 0
    if chat_id:
        _forward_to_telegram(chat_id, text)

    invalidate_chat_cache()
    return new_id


def _forward_to_telegram(chat_id: int, text: str):
    """TUI 메시지를 텔레그램 채팅에 포워딩 (curl subprocess)"""
    if not BOT_TOKEN or not chat_id:
        return
    tg_text = f"[TUI] COMMANDER: {text}"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": tg_text})
    try:
        subprocess.Popen(
            ["curl", "-s", "-X", "POST", url,
             "-H", "Content-Type: application/json",
             "-d", payload],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _kill_executor() -> bool:
    """executor Claude 프로세스 종료"""
    killed = False
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            for pid in result.stdout.strip().split("\n"):
                pid = pid.strip()
                if pid:
                    subprocess.run(["kill", pid], capture_output=True)
                    killed = True
    except Exception:
        pass

    try:
        if os.path.exists(EXECUTOR_LOCK):
            os.remove(EXECUTOR_LOCK)
    except OSError:
        pass

    working_info = None
    try:
        if os.path.exists(WORKING_LOCK_FILE):
            with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
                working_info = json.load(f)
            os.remove(WORKING_LOCK_FILE)
    except Exception:
        pass

    interrupted_data = {
        "interrupted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": "TUI /stop",
        "by_user": "TUI",
        "chat_id": 0,
        "previous_work": None,
    }
    if working_info:
        interrupted_data["previous_work"] = {
            "instruction": working_info.get("instruction_summary", ""),
            "started_at": working_info.get("started_at", ""),
            "message_id": working_info.get("message_id"),
        }

    os.makedirs(os.path.dirname(INTERRUPTED_FILE), exist_ok=True)
    with open(INTERRUPTED_FILE, "w", encoding="utf-8") as f:
        json.dump(interrupted_data, f, ensure_ascii=False, indent=2)

    return killed


def _resume_executor() -> tuple[bool, str]:
    """executor.sh 백그라운드 실행"""
    if os.path.exists(EXECUTOR_LOCK):
        return False, "executor 이미 실행 중"
    if not os.path.exists(EXECUTOR_SCRIPT):
        return False, "executor.sh 없음"

    log_dir = os.path.join(ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "executor.log")

    with open(log_file, "a") as lf:
        subprocess.Popen(
            ["bash", EXECUTOR_SCRIPT],
            stdout=lf, stderr=lf,
            cwd=ROOT,
            start_new_session=True,
        )
    return True, "executor 시작됨"


def log_commander_message(text: str, stream_buffer: deque):
    """TUI 커맨더 메시지를 로그에 기록 (Stream + Dashboard)"""
    now = datetime.now().strftime("%H:%M")
    stream_buffer.append((now, "🎖️", "commander", text))

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = json.load(f)
        if "mission_log" not in status:
            status["mission_log"] = []
        status["mission_log"].append({
            "time": now,
            "agent": "commander",
            "message": text,
        })
        status["mission_log"] = status["mission_log"][-50:]
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _start_squid_squad(args_str: str, stream_buffer: deque) -> str:
    """Squid 모드 토론 시작"""
    from heysquid.dashboard import init_squad
    parts = args_str.strip().split()
    participants = []
    topic_parts = []
    for p in parts:
        if p.startswith("@") and p[1:] in [a for a in AGENT_ORDER if a != "pm"]:
            participants.append(p[1:])
        else:
            topic_parts.append(p)
    topic = " ".join(topic_parts) or "자유 토론"
    if not participants:
        return "참가 에이전트를 지정하세요: /squid @agent1 @agent2 주제"
    init_squad(topic, participants, mode="squid")
    names = " ".join(f"@{p}" for p in participants)
    log_commander_message(f"[Squad] Squid 모드: {names} — {topic}", stream_buffer)
    return f"Squid Squad 시작: {names}"


def _start_kraken_squad(args_str: str, stream_buffer: deque) -> str:
    """Kraken 모드 시작"""
    from heysquid.dashboard import init_squad
    topic = args_str.strip() or "프로젝트 종합 평가"
    participants = [a for a in AGENT_ORDER if a != "pm"]
    init_squad(topic, participants, mode="kraken", virtual_experts=KRAKEN_CREW_NAMES)
    log_commander_message(f"[Squad] Kraken 모드: 전원+Crew — {topic}", stream_buffer)
    return "Kraken Squad 시작: 전원+Kraken Crew"


def send_chat_message(text: str, stream_buffer: deque) -> str:
    """Chat 모드에서 메시지 전송 처리. flash 메시지 반환."""
    text = text.strip()
    if not text:
        return ""

    if text == "/stop":
        killed = _kill_executor()
        return "작업 중단됨" if killed else "실행 중인 작업 없음"

    if text == "/resume":
        ok, msg = _resume_executor()
        return msg

    if text.startswith("/squid "):
        return _start_squid_squad(text[7:], stream_buffer)

    if text.startswith("/kraken"):
        return _start_kraken_squad(text[7:].strip(), stream_buffer)

    if text == "/endsquad":
        from heysquid.dashboard import clear_squad
        clear_squad()
        return "Squad 종료"

    # 일반 메시지
    mid = inject_local_message(text)
    mentions = parse_mentions(text)
    log_commander_message(text, stream_buffer)

    if not os.path.exists(EXECUTOR_LOCK):
        _resume_executor()

    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)}"
    return ""


def execute_command(cmd: str, stream_buffer: deque) -> str:
    """커맨드 파싱 및 실행 (: 접두사 모드)"""
    cmd = cmd.strip()
    if not cmd:
        return ""

    if cmd == "stop":
        killed = _kill_executor()
        return "작업 중단됨" if killed else "실행 중인 작업 없음"

    if cmd == "resume":
        ok, msg = _resume_executor()
        return msg

    if cmd.startswith("squid "):
        return _start_squid_squad(cmd[6:], stream_buffer)

    if cmd.startswith("kraken"):
        return _start_kraken_squad(cmd[6:].strip(), stream_buffer)

    if cmd == "endsquad":
        from heysquid.dashboard import clear_squad
        clear_squad()
        return "Squad 종료"

    # 기본: 메시지 전송
    mid = inject_local_message(cmd)
    mentions = parse_mentions(cmd)
    log_commander_message(cmd, stream_buffer)
    if not os.path.exists(EXECUTOR_LOCK):
        _resume_executor()
    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)} (id={mid})"
    return f"메시지 전송 (id={mid})"
