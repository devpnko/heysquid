"""커맨드 실행 — 메시지 전송, squad 관리, executor 제어"""

import json
import os
import shlex
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
    "merge":    {"desc": "칸반 카드 병합 (/merge K1 K2)"},
    "done":     {"desc": "카드 Done 처리 (/done K1 또는 /done all)"},
    "clean":    {"desc": "활성 카드 전부 Done 처리"},
    "del":      {"desc": "카드 삭제 (/del K1)"},
    "move":     {"desc": "카드 컬럼 이동 (/move K1 waiting)"},
    "info":     {"desc": "카드 상세 보기 (/info K1)"},
    "squid":    {"desc": "Squid 토론 시작"},
    "kraken":   {"desc": "Kraken 토론 시작"},
    "endsquad": {"desc": "토론 종료"},
    "dashboard": {"desc": "대시보드 열기"},
}

EXECUTOR_SCRIPT = os.path.join(ROOT, "scripts", "executor.sh")
DASHBOARD_HTML = os.path.join(ROOT, "data", "dashboard.html")
INTERRUPTED_FILE = os.path.join(ROOT, "data", "interrupted.json")
WORKING_LOCK_FILE = os.path.join(ROOT, "data", "working.json")
CLAUDE_PIDFILE = os.path.join(ROOT, "data", "claude.pid")


def _is_pm_alive() -> bool:
    """PM(claude) 프로세스 생존 확인 — executor.sh is_pm_alive와 동일 로직"""
    # 1차: caffeinate 패턴
    if subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True,
    ).returncode == 0:
        return True
    # 2차: PID 파일
    if os.path.exists(CLAUDE_PIDFILE):
        try:
            with open(CLAUDE_PIDFILE, "r") as f:
                for line in f:
                    pid = line.strip()
                    if pid and subprocess.run(
                        ["kill", "-0", pid], capture_output=True
                    ).returncode == 0:
                        return True
        except Exception:
            pass
    return False

# .env에서 BOT_TOKEN 로드
try:
    from dotenv import load_dotenv
    from heysquid.core.config import get_env_path
    load_dotenv(get_env_path())
except ImportError:
    pass
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.tiff', '.svg'}


def _make_file_entry(path: str) -> dict:
    """이미지 파일 메타 dict 생성."""
    return {
        "type": "photo",
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "size": os.path.getsize(path),
    }


def _is_image_file(path: str) -> bool:
    """이미지 확장자 + 파일 존재 확인."""
    _, ext = os.path.splitext(path)
    return ext.lower() in IMAGE_EXTENSIONS and os.path.isfile(path)


def extract_image_paths(text: str) -> tuple[str, list[dict]]:
    """텍스트에서 이미지 파일 경로 추출. (정리된 텍스트, files 리스트) 반환.

    3단계 전략:
    1) shlex — 백슬래시 이스케이프, 따옴표 경로 (macOS 드래그-앤-드롭)
    2) 공백 포함 경로 재조합 — Textual TextArea 등에서 이스케이프 없이 붙는 경우
    3) 단순 split 폴백
    """
    # 1단계: shlex (이스케이프/따옴표 처리)
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    files = []
    clean_parts = []

    for token in tokens:
        expanded = os.path.expanduser(token)
        if _is_image_file(expanded):
            files.append(_make_file_entry(expanded))
        else:
            clean_parts.append(token)

    if files:
        return " ".join(clean_parts), files

    # 2단계: 공백 포함 경로 재조합
    # "이거 봐줘 /path/to/스크린샷 2026-02-23 오전 12.04.09.png"
    # → shlex가 쪼개버린 토큰들을 /로 시작하는 지점부터 .확장자까지 합쳐서 시도
    raw_tokens = text.split()
    used = set()

    for i, token in enumerate(raw_tokens):
        if i in used:
            continue
        expanded_start = os.path.expanduser(token)
        if not (expanded_start.startswith("/") or expanded_start.startswith("~")):
            continue
        # 이 토큰부터 뒤로 확장하며 이미지 파일인지 시도
        candidate = expanded_start
        for j in range(i + 1, len(raw_tokens) + 1):
            if _is_image_file(candidate):
                files.append(_make_file_entry(candidate))
                used.update(range(i, j))
                break
            if j < len(raw_tokens):
                candidate = candidate + " " + raw_tokens[j]

    if files:
        clean_parts = [t for idx, t in enumerate(raw_tokens) if idx not in used]
        return " ".join(clean_parts), files

    # 이미지 없음
    return text, []


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


def inject_local_message(text: str, files: list[dict] | None = None) -> int:
    """messages.json에 TUI 메시지 주입 (flock atomic)."""
    from heysquid.channels._msg_store import load_and_modify, load_telegram_messages

    # user_info를 먼저 조회 (read-only)
    data = load_telegram_messages()
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

    new_id = None

    def _inject(data):
        nonlocal new_id
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
            "files": files or [],
            "location": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "processed": False,
            "source": "tui",
            "mentions": parse_mentions(text),
        }
        data["messages"].append(message)
        return data

    load_and_modify(_inject)

    # 모든 활성 채널에 브로드캐스트 (전체 동기화)
    _broadcast_to_channels(text)

    invalidate_chat_cache()
    return new_id


def _broadcast_to_channels(text: str):
    """TUI 메시지를 모든 활성 채널에 브로드캐스트"""
    try:
        from heysquid.channels._router import broadcast_user_message
        broadcast_user_message(text, source_channel="tui", sender_name="COMMANDER")
    except Exception as e:
        # 브로드캐스트 실패해도 TUI 메시지 자체는 정상 동작
        print(f"[WARN] TUI broadcast failed: {e}")


def _kill_executor() -> bool:
    """executor Claude 프로세스 종료 — executor.sh kill_all_pm과 동일 로직"""
    killed = False
    pidfile = os.path.join(ROOT, "data", "claude.pid")

    # 1차: PID 파일 (가장 확실 — orphan claude도 잡음)
    if os.path.exists(pidfile):
        try:
            with open(pidfile, "r") as f:
                for line in f:
                    pid = line.strip()
                    if pid:
                        subprocess.run(["kill", pid], capture_output=True)
                        killed = True
        except Exception:
            pass

    # 2차: caffeinate 패턴 → 부모(claude) kill
    try:
        result = subprocess.run(
            ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            for cafe_pid in result.stdout.strip().split("\n"):
                cafe_pid = cafe_pid.strip()
                if cafe_pid:
                    # caffeinate의 부모 = claude
                    ppid_result = subprocess.run(
                        ["ps", "-p", cafe_pid, "-o", "ppid="],
                        capture_output=True, text=True,
                    )
                    parent = ppid_result.stdout.strip()
                    if parent:
                        subprocess.run(["kill", parent], capture_output=True)
                        killed = True
                    subprocess.run(["kill", cafe_pid], capture_output=True)
                    killed = True
    except Exception:
        pass

    # 3차: pkill fallback
    subprocess.run(["pkill", "-f", "append-system-prompt-file"], capture_output=True)

    # force kill — 2초 후 생존자 kill -9
    if killed:
        import time
        time.sleep(2)
        if os.path.exists(pidfile):
            try:
                with open(pidfile, "r") as f:
                    for line in f:
                        pid = line.strip()
                        if pid:
                            subprocess.run(["kill", "-0", pid], capture_output=True)
                            subprocess.run(["kill", "-9", pid], capture_output=True)
            except Exception:
                pass
        subprocess.run(["pkill", "-9", "-f", "append-system-prompt-file"], capture_output=True)

    # PID 파일 삭제
    try:
        if os.path.exists(pidfile):
            os.remove(pidfile)
    except OSError:
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

    # 미처리 메시지 processed 처리 (listener의 _handle_stop_command과 동일)
    try:
        from heysquid.channels._msg_store import load_and_modify

        cleared = 0
        def _clear_unprocessed(data):
            nonlocal cleared
            for m in data.get("messages", []):
                if not m.get("processed", False):
                    m["processed"] = True
                    cleared += 1
            return data
        load_and_modify(_clear_unprocessed)
    except Exception:
        pass

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
        if not _is_pm_alive():
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

    # 1. Listeners 확인 (멀티채널)
    listener_configs = [
        ("TG", "telegram_listener", "com.heysquid.watcher.plist", None),
        ("SL", "slack_listener", "com.heysquid.slack.plist", "SLACK_BOT_TOKEN"),
        ("DC", "discord_listener", "com.heysquid.discord.plist", "DISCORD_BOT_TOKEN"),
    ]
    for tag, proc_name, plist_name, env_key in listener_configs:
        # 토큰 미설정이면 스킵
        if env_key and not os.getenv(env_key):
            continue

        has_proc = subprocess.run(
            ["pgrep", "-f", proc_name],
            capture_output=True,
        ).returncode == 0
        if has_proc:
            result = subprocess.run(
                ["pgrep", "-f", proc_name],
                capture_output=True, text=True,
            )
            pid = result.stdout.strip().split("\n")[0].strip()
            lines.append(f"✅ Listener [{tag}]: running (PID {pid})")
        else:
            plist = os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}")
            if os.path.exists(plist):
                subprocess.run(["launchctl", "unload", plist], capture_output=True)
                time.sleep(1)
                subprocess.run(["launchctl", "load", plist], capture_output=True)
                time.sleep(2)
                alive = subprocess.run(
                    ["pgrep", "-f", proc_name],
                    capture_output=True,
                ).returncode == 0
                if alive:
                    lines.append(f"🔧 Listener [{tag}]: restarted")
                    fixed += 1
                else:
                    lines.append(f"❌ Listener [{tag}]: restart failed")
            else:
                lines.append(f"❌ Listener [{tag}]: not running (no plist)")

    # 2. Executor lock 확인
    if os.path.exists(EXECUTOR_LOCK):
        if _is_pm_alive():
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


def _open_dashboard() -> str:
    """macOS 기본 브라우저로 대시보드 열기 (localhost 서버)"""
    subprocess.Popen(["open", "http://localhost:8420/dashboard.html"])
    return "대시보드 열림"


def _get_numbered_cards() -> list[dict]:
    """칸반에서 번호가 붙는 카드 목록 반환 (non-done, non-automation, 순서 보존)."""
    from .data_poller import load_agent_status
    status = load_agent_status()
    tasks = status.get("kanban", {}).get("tasks", [])
    return [t for t in tasks if t.get("column") not in ("done", "automation")]


def _list_cards_display() -> str:
    """활성 카드 K-ID 목록 문자열."""
    cards = _get_numbered_cards()
    if not cards:
        return "활성 카드 없음"
    lines = ["칸반 카드 목록:"]
    for c in cards:
        sid = c.get("short_id", "?")
        col = c.get("column", "?")[:4].upper()
        title = c.get("title", "")[:40]
        lines.append(f"  {sid} [{col}] {title}")
    return "\n".join(lines)


def _resolve_args(args_str: str) -> list[dict] | str:
    """공백 구분 K-ID들을 파싱하여 카드 리스트 반환. 실패 시 에러 문자열."""
    from heysquid.dashboard.kanban import resolve_card
    parts = args_str.strip().split()
    cards = []
    for p in parts:
        card = resolve_card(p)
        if not card:
            return f"카드를 찾을 수 없음: {p}"
        cards.append(card)
    return cards


def _merge_kanban_cards(args_str: str) -> str:
    """칸반 카드 병합. /merge K1 K2 → K1을 K2에 병합."""
    from heysquid.dashboard.kanban import resolve_card
    parts = args_str.strip().split()
    if len(parts) != 2:
        return _list_cards_display() + "\n\n사용법: /merge <source> <target> (K-ID 또는 번호)"

    # K-ID 또는 숫자 지원
    def _find_card(token):
        card = resolve_card(token)
        if card:
            return card
        try:
            num = int(token)
            cards = _get_numbered_cards()
            if 1 <= num <= len(cards):
                return cards[num - 1]
        except ValueError:
            pass
        return None

    src = _find_card(parts[0])
    tgt = _find_card(parts[1])
    if not src:
        return f"카드를 찾을 수 없음: {parts[0]}"
    if not tgt:
        return f"카드를 찾을 수 없음: {parts[1]}"
    if src["id"] == tgt["id"]:
        return "같은 카드끼리는 병합 불가"

    from heysquid.dashboard.kanban import merge_kanban_tasks
    ok = merge_kanban_tasks(src["id"], tgt["id"])
    if ok:
        src_sid = src.get("short_id", "?")
        tgt_sid = tgt.get("short_id", "?")
        return f"✓ {src_sid} → {tgt_sid} 병합 완료"
    return "병합 실패 (카드를 찾을 수 없음)"


def _done_kanban_card(args_str: str) -> str:
    """카드 Done 처리. /done K1 또는 /done all"""
    arg = args_str.strip().lower()
    if not arg:
        return _list_cards_display() + "\n\n사용법: /done <K-ID> 또는 /done all"
    if arg == "all":
        return _clean_kanban_cards()
    resolved = _resolve_args(args_str)
    if isinstance(resolved, str):
        return resolved
    from heysquid.dashboard.kanban import move_kanban_task
    done_ids = []
    for card in resolved:
        if move_kanban_task(card["id"], "done"):
            done_ids.append(card.get("short_id", card["id"]))
    if done_ids:
        return f"✓ {', '.join(done_ids)} Done 처리 완료"
    return "처리 실패"


def _clean_kanban_cards() -> str:
    """활성 카드 전부 Done 처리."""
    from heysquid.dashboard.kanban import move_kanban_task
    cards = _get_numbered_cards()
    if not cards:
        return "활성 카드 없음 — 이미 깨끗!"
    count = 0
    for c in cards:
        if move_kanban_task(c["id"], "done"):
            count += 1
    return f"✓ {count}개 카드 전부 Done 처리 완료"


def _del_kanban_card(args_str: str) -> str:
    """카드 삭제. /del K1"""
    if not args_str.strip():
        return _list_cards_display() + "\n\n사용법: /del <K-ID>"
    resolved = _resolve_args(args_str)
    if isinstance(resolved, str):
        return resolved
    from heysquid.dashboard.kanban import delete_kanban_task
    deleted = []
    for card in resolved:
        if delete_kanban_task(card["id"]):
            deleted.append(card.get("short_id", card["id"]))
    if deleted:
        return f"✓ {', '.join(deleted)} 삭제 완료"
    return "삭제 실패"


def _move_kanban_card(args_str: str) -> str:
    """카드 컬럼 이동. /move K1 waiting"""
    parts = args_str.strip().split()
    if len(parts) != 2:
        return "사용법: /move <K-ID> <컬럼>\n컬럼: todo, in_progress(ip), waiting(wait), done"
    from heysquid.dashboard.kanban import resolve_card, move_kanban_task
    card = resolve_card(parts[0])
    if not card:
        return f"카드를 찾을 수 없음: {parts[0]}"
    col = parts[1].lower()
    col_aliases = {"prog": "in_progress", "ip": "in_progress", "wait": "waiting", "tw": "todo"}
    col = col_aliases.get(col, col)
    if col not in ("todo", "in_progress", "waiting", "done"):
        return f"잘못된 컬럼: {parts[1]}\n사용 가능: todo, in_progress(ip), waiting(wait), done"
    sid = card.get("short_id", card["id"])
    ok = move_kanban_task(card["id"], col)
    if ok:
        return f"✓ {sid} → {col}"
    return "이동 실패"


def _info_kanban_card(args_str: str) -> str:
    """카드 상세 보기. /info K1"""
    if not args_str.strip():
        return _list_cards_display() + "\n\n사용법: /info <K-ID>"
    from heysquid.dashboard.kanban import resolve_card
    card = resolve_card(args_str.strip())
    if not card:
        return f"카드를 찾을 수 없음: {args_str.strip()}"
    sid = card.get("short_id", "?")
    lines = [
        f"── {sid} ──",
        f"제목: {card.get('title', '')}",
        f"컬럼: {card.get('column', '?')}",
        f"생성: {card.get('created_at', '?')}",
        f"수정: {card.get('updated_at', '?')}",
    ]
    tags = card.get("tags", [])
    if tags:
        lines.append(f"태그: {', '.join(tags)}")
    logs = card.get("activity_log", [])
    if logs:
        lines.append(f"로그: {len(logs)}개")
        for entry in logs[-5:]:
            lines.append(f"  [{entry.get('time','')}] {entry.get('agent','')}: {entry.get('message','')}")
    result = card.get("result")
    if result:
        lines.append(f"결과: {str(result)[:100]}")
    return "\n".join(lines)


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
        # kill 전에 세션 메모리 강제 갱신 (컨텍스트 보존)
        try:
            from heysquid.memory.session import compact_session_memory, save_session_summary
            compact_session_memory()
            save_session_summary()
        except Exception:
            pass
        killed = _kill_executor()
        return "작업 중단됨 (세션 메모리 저장 완료)" if killed else "실행 중인 작업 없음"

    if name == "resume":
        ok, msg = _resume_executor()
        return msg

    if name == "doctor":
        return _run_doctor()

    if name == "skill":
        return _run_skill_command(args)

    if name == "merge":
        return _merge_kanban_cards(args)

    if name == "done":
        return _done_kanban_card(args)

    if name == "clean":
        return _clean_kanban_cards()

    if name == "del":
        return _del_kanban_card(args)

    if name == "move":
        return _move_kanban_card(args)

    if name == "info":
        return _info_kanban_card(args)

    if name == "squid":
        return _start_squid_squad(args, stream_buffer)

    if name == "kraken":
        return _start_kraken_squad(args, stream_buffer)

    if name == "dashboard":
        return _open_dashboard()

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

    # 이미지 경로 감지
    clean_text, files = extract_image_paths(text)
    display_text = clean_text or "(이미지)"

    mid = inject_local_message(display_text, files=files)
    mentions = parse_mentions(display_text)
    log_commander_message(display_text, stream_buffer)

    _clean_stale_lock_and_resume()

    if files:
        names = ", ".join(f["name"] for f in files)
        suffix = f" (🖼️ {names})"
        if mentions:
            return f"✓ 전달됨 → {' '.join('@' + m for m in mentions)}{suffix}"
        return f"✓ 전달됨{suffix}"

    if mentions:
        return f"✓ 전달됨 → {' '.join('@' + m for m in mentions)}"
    return "✓ 전달됨"


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
