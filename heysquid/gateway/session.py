"""gateway.session — claude PM subprocess 오케스트레이션 (asyncio).

executor.sh 의 _run_claude_iteration (387-402줄) 을 asyncio.create_subprocess_exec 로 이식.
macOS 전용 caffeinate/watchdog/pgrep (이 N100 에선 죽은 코드) 제거 → os.setsid + os.killpg 로 대체.

claude 호출 (executor.sh 원본과 동일):
  claude -p [-c] --dangerously-skip-permissions --model sonnet \
    --output-format stream-json --verbose --append-system-prompt-file CLAUDE.md  <PROMPT>
  env: CLAUDECODE 제거 + DISABLE_AUTOUPDATER=1
stdout → STREAM_LOG append (기존 stream_viewer.py 가 tail -F 로 소비).
"""

import asyncio
import os
import shutil
import signal
import time

from ..config import PROJECT_ROOT_STR as PROJECT_ROOT

LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "executor.log")
STREAM_LOG = os.path.join(LOG_DIR, "executor.stream.jsonl")
SPF = os.path.join(PROJECT_ROOT, "CLAUDE.md")

# claude 세션 타임아웃 (executor.sh 는 무한 wait; 여기선 안전 상한)
SESSION_TIMEOUT = int(os.getenv("HEYSQUID_SESSION_TIMEOUT", "1800"))  # 30분
SESSION_END_MARKER = '"type":"result"'  # stream-json 세션 종료 신호


def _log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [gateway] {msg}\n"
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    print(line, end="", flush=True)


def _find_claude() -> str | None:
    for cand in (shutil.which("claude"),
                 os.path.expanduser("~/.local/bin/claude"),
                 "/usr/local/bin/claude"):
        if cand and os.path.exists(cand):
            return cand
    return None


# PM 초기 프롬프트 (executor.sh PROMPT 와 동일 — pm-workflow 준수)
PROMPT_NEW = (
    "Act as a PM following the instructions in CLAUDE.md.\n"
    "1) Read data/identity.json to identify yourself and the user.\n"
    "2) Read data/permanent_memory.md (persistent memory).\n"
    "3) Read data/session_memory.md (recent context, active tasks).\n"
    "4) Call check_crash_recovery(); if it returns recovery info, notify and continue.\n"
    "4.5) Call check_interrupted(); if interrupted, check new messages first then act on intent.\n"
    "5) Call check_telegram() from heysquid/telegram_bot.py to get new messages.\n"
    "5.5) If the message involves threads/스레드 content, read workspaces/threads/context.md FIRST.\n"
    "6) Evaluate as a PM: conversation→reply_telegram(); task→plan+confirm; approval→execute.\n"
    "7) After done, save session_memory.md and exit cleanly. "
    "The gateway handles persistence — do NOT run standby loops or sleep commands.\n"
    "8) Record important decisions/lessons in data/permanent_memory.md (keep under 200 lines).\n"
    "IMPORTANT: Always use reply_telegram() for ALL responses. "
    "Never call send_message_sync() directly."
)

PROMPT_CONTINUE = (
    "New messages arrived. Call check_telegram() to get them, then handle following PM workflow. "
    "Use reply_telegram() for responses. Do NOT run standby loops or sleep — exit cleanly when done."
)


async def run_claude(mode: str = "new") -> int:
    """claude PM 세션 1회 실행. mode='new' (cold) | 'continue' (hot -c).

    Return: exit code (0=정상). 세션그룹 전체를 정리하여 standby 자식 잔존 방지.
    """
    claude = _find_claude()
    if not claude:
        _log("[ERROR] claude CLI not found (PATH, ~/.local/bin, /usr/local/bin)")
        return 127
    if not os.path.exists(SPF):
        _log(f"[ERROR] CLAUDE.md not found: {SPF}")
        return 2

    prompt = PROMPT_CONTINUE if mode == "continue" else PROMPT_NEW
    args = [claude, "-p"]
    if mode == "continue":
        args.append("-c")
    args += [
        "--dangerously-skip-permissions",
        "--model", "sonnet",
        "--output-format", "stream-json", "--verbose",
        "--append-system-prompt-file", SPF,
        prompt,
    ]

    # env: CLAUDECODE 제거 (claude 내부 재귀 방지) + autoupdater off
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    env["DISABLE_AUTOUPDATER"] = "1"

    # stream log 초기화 (clean slate)
    try:
        open(STREAM_LOG, "w").close()
    except Exception:
        pass

    _log(f"[INFO] claude session start (mode={mode})")
    stream_f = open(STREAM_LOG, "a", encoding="utf-8")
    log_f = open(LOG_FILE, "a", encoding="utf-8")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=stream_f,        # stream-json → STREAM_LOG (stream_viewer 소비)
            stderr=log_f,
            cwd=PROJECT_ROOT,
            env=env,
            start_new_session=True,  # os.setsid — 자식까지 같은 세션그룹
        )
    except Exception as e:
        _log(f"[ERROR] claude launch failed: {e}")
        stream_f.close(); log_f.close()
        return 1

    pgid = os.getpgid(proc.pid)
    try:
        ec = await asyncio.wait_for(proc.wait(), timeout=SESSION_TIMEOUT)
    except asyncio.TimeoutError:
        _log(f"[WARN] session timeout ({SESSION_TIMEOUT}s) — killing session group")
        ec = -1
        _kill_group(pgid)
    finally:
        # standby 자식 잔존 방지: 세션그룹 잔여 프로세스 정리
        _reap_group(pgid)
        stream_f.close(); log_f.close()

    _log(f"[INFO] claude session done (mode={mode}, exit={ec})")
    return ec if ec is not None else 0


def _kill_group(pgid: int):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        time.sleep(1)


def _reap_group(pgid: int):
    """세션 종료 후 그룹에 남은 자식(standby loop 등) 정리."""
    try:
        os.killpg(pgid, 0)  # 그룹 살아있나?
    except ProcessLookupError:
        return  # 이미 깨끗
    _log(f"[INFO] reaping leftover session group {pgid}")
    _kill_group(pgid)
