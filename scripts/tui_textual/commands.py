"""커맨드 실행 — 메시지 전송, squad 관리, executor 제어"""

import json
import os
import subprocess
import time
from collections import deque
from datetime import datetime

from heysquid.core.agents import AGENTS, KRAKEN_CREW_NAMES

from .utils import AGENT_ORDER, parse_mentions
from .data_poller import (
    ROOT, STATUS_FILE, MESSAGES_FILE, EXECUTOR_LOCK,
    invalidate_chat_cache,
)

# ── 커맨드 레지스트리 ──────────────────────────────────────────
COMMAND_REGISTRY = {
    "stop":     {"desc": "작업 중단"},
    "resume":   {"desc": "executor 재시작"},
    "doctor":   {"desc": "시스템 진단"},
    "skill":    {"desc": "스킬 목록/실행"},
    "squid":    {"desc": "Squid 토론 시작"},
    "kraken":   {"desc": "Kraken 토론 시작"},
    "endsquad": {"desc": "토론 종료"},
}

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
    if user_info is None:
        allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        fallback_id = allowed.split(",")[0].strip() if allowed else ""
        if fallback_id.isdigit():
            user_info = {
                "chat_id": int(fallback_id),
                "user_id": int(fallback_id),
                "username": "tui",
                "first_name": "Commander",
            }

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


def _clean_stale_lock_and_resume():
    """executor.lock이 있으면 실제 프로세스 확인, stale이면 제거 후 재시작"""
    if os.path.exists(EXECUTOR_LOCK):
        has_claude = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True,
        ).returncode == 0
        if not has_claude:
            try:
                os.remove(EXECUTOR_LOCK)
            except OSError:
                pass
            _resume_executor()
    else:
        _resume_executor()


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


def _run_doctor() -> str:
    """시스템 진단 + 자동 수리"""
    lines = ["🩺 Doctor Report"]
    fixed = 0

    # 1. Listener 확인
    has_listener = subprocess.run(
        ["pgrep", "-f", "telegram_listener"],
        capture_output=True,
    ).returncode == 0
    if has_listener:
        result = subprocess.run(
            ["pgrep", "-f", "telegram_listener"],
            capture_output=True, text=True,
        )
        pid = result.stdout.strip().split("\n")[0].strip()
        lines.append(f"✅ Listener: running (PID {pid})")
    else:
        plist = os.path.expanduser("~/Library/LaunchAgents/com.heysquid.watcher.plist")
        if os.path.exists(plist):
            subprocess.run(["launchctl", "unload", plist], capture_output=True)
            time.sleep(1)
            subprocess.run(["launchctl", "load", plist], capture_output=True)
            time.sleep(2)
            alive = subprocess.run(
                ["pgrep", "-f", "telegram_listener"],
                capture_output=True,
            ).returncode == 0
            if alive:
                lines.append("🔧 Listener: restarted")
                fixed += 1
            else:
                lines.append("❌ Listener: restart failed")
        else:
            lines.append("❌ Listener: not running (no plist found)")

    # 2. Executor lock 확인
    if os.path.exists(EXECUTOR_LOCK):
        has_claude = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True,
        ).returncode == 0
        if has_claude:
            lines.append("✅ Lock: active (executor running)")
        else:
            try:
                os.remove(EXECUTOR_LOCK)
            except OSError:
                pass
            lines.append("🔧 Lock: stale lock removed")
            fixed += 1
    else:
        lines.append("✅ Lock: clean")

    # 3. 좀비 프로세스 (executor.sh 2개 이상 = 이상)
    result = subprocess.run(
        ["pgrep", "-f", "bash.*executor.sh"],
        capture_output=True, text=True,
    )
    executor_pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    if len(executor_pids) > 1:
        for pid in executor_pids[:-1]:
            subprocess.run(["kill", pid], capture_output=True)
        lines.append(f"🔧 Zombies: killed {len(executor_pids) - 1} duplicate executor(s)")
        fixed += 1
    else:
        lines.append("✅ Zombies: clean")

    # 4. Orphan poll 프로세스
    result = subprocess.run(
        ["pgrep", "-f", "poll_new_messages"],
        capture_output=True, text=True,
    )
    orphan_pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    if orphan_pids:
        for pid in orphan_pids:
            subprocess.run(["kill", pid], capture_output=True)
        lines.append(f"🔧 Orphans: killed {len(orphan_pids)} poll process(es)")
        fixed += 1
    else:
        lines.append("✅ Orphans: clean")

    # 5. 메시지 큐
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        unprocessed = [m for m in msgs if not m.get("processed")]
        stuck = [m for m in msgs if m.get("retry_count", 0) >= 3]
        if unprocessed or stuck:
            parts = []
            if unprocessed:
                parts.append(f"{len(unprocessed)} pending")
            if stuck:
                parts.append(f"{len(stuck)} stuck")
            lines.append(f"⚠️ Queue: {', '.join(parts)}")
        else:
            lines.append("✅ Queue: clean")
    except Exception:
        lines.append("✅ Queue: clean")

    # 6. Dashboard 서버
    dash_ok = subprocess.run(
        ["lsof", "-i", ":8420"],
        capture_output=True,
    ).returncode == 0
    lines.append(f"{'✅' if dash_ok else '⚠️'} Dashboard: {'running' if dash_ok else 'stopped'}")

    if fixed:
        lines.append(f"\nFixed {fixed} issue(s).")
    else:
        lines.append("\nAll systems healthy.")

    return "\n".join(lines)


def _run_skill_command(args_str: str) -> str:
    """스킬 목록 조회 또는 수동 실행"""
    from heysquid.skills import get_skill_registry, run_skill, SkillContext

    name = args_str.strip()
    registry = get_skill_registry()

    if not name:
        # 스킬 목록
        if not registry:
            return "등록된 스킬 없음"
        lines = ["등록된 스킬:"]
        for sname, meta in registry.items():
            enabled = meta.get("enabled", True)
            trigger = meta.get("trigger", "manual")
            schedule = meta.get("schedule", "")
            desc = meta.get("description", "")
            status = "off" if not enabled else "on"
            sched_info = f" ({schedule})" if schedule else ""
            lines.append(f"  {sname:<16} [{status}] {trigger}{sched_info}  {desc}")
        return "\n".join(lines)

    # 스킬 실행
    if name not in registry:
        return f"스킬 '{name}' 없음. /skill 로 목록 확인"

    ctx = SkillContext(triggered_by="manual")
    result = run_skill(name, ctx)
    if result["ok"]:
        return f"스킬 '{name}' 실행 완료"
    else:
        return f"스킬 '{name}' 실패: {result['error']}"


def dispatch_command(raw: str, stream_buffer: deque) -> str | None:
    """통합 커맨드 디스패치. '/cmd args' → handler 호출. 커맨드 아니면 None."""
    cmd = raw.strip()
    if not cmd.startswith("/"):
        return None
    cmd = cmd[1:]
    parts = cmd.split(None, 1)
    name = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    if name == "stop":
        killed = _kill_executor()
        return "작업 중단됨" if killed else "실행 중인 작업 없음"

    if name == "resume":
        ok, msg = _resume_executor()
        return msg

    if name == "doctor":
        return _run_doctor()

    if name == "skill":
        return _run_skill_command(args)

    if name == "squid":
        return _start_squid_squad(args, stream_buffer)

    if name == "kraken":
        return _start_kraken_squad(args, stream_buffer)

    if name == "endsquad":
        from heysquid.dashboard import clear_squad
        clear_squad()
        return "Squad 종료"

    return None  # 알 수 없는 커맨드


def send_chat_message(text: str, stream_buffer: deque) -> str:
    """Chat 모드에서 메시지 전송 처리. flash 메시지 반환."""
    text = text.strip()
    if not text:
        return ""

    result = dispatch_command(text, stream_buffer)
    if result is not None:
        return result

    # 일반 메시지
    mid = inject_local_message(text)
    mentions = parse_mentions(text)
    log_commander_message(text, stream_buffer)

    _clean_stale_lock_and_resume()

    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)}"
    return ""


def execute_command(cmd: str, stream_buffer: deque) -> str:
    """커맨드 파싱 및 실행 (/ 접두사 모드)"""
    cmd = cmd.strip()
    if not cmd:
        return ""

    # dispatch_command expects /prefix
    result = dispatch_command("/" + cmd, stream_buffer)
    if result is not None:
        return result

    # 기본: 메시지 전송
    mid = inject_local_message(cmd)
    mentions = parse_mentions(cmd)
    log_commander_message(cmd, stream_buffer)
    _clean_stale_lock_and_resume()
    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)} (id={mid})"
    return f"메시지 전송 (id={mid})"
