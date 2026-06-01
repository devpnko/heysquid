"""gateway.runner — 단일 asyncio 메인 루프.

흐름 (씹힘 0 설계):
  poll(fetch_new_messages 재사용: getUpdates→messages.json→👀→STOP→커서)
    → 새 메시지 있으면 디바운스(연속 입력 합치기)
    → claude 세션 1회 (run_claude)
    → 세션 종료 직후 미처리 메시지 재확인 → 있으면 continue 세션 (흡수)
    → 미처리 없을 때까지 반복 → 그 다음에야 폴링 재개

기존 bash executor.sh + trigger_executor + IDLE loop + quick_check 전부 대체.
seen 플래그 race 제거: 세션 종료 후 messages.json 의 processed=False 를 직접 확인
(seen 무시) → PM 이 봤지만 처리 못한 메시지도 즉시 재처리.
"""

import asyncio
import os

from ..config import get_env_path
from dotenv import load_dotenv

load_dotenv(get_env_path())

from ..paths import MESSAGES_FILE, WORKING_LOCK_FILE, EXECUTOR_LOCK_FILE
from ..channels._msg_store import load_telegram_messages
from ..channels import telegram_listener as tl
from .session import run_claude, _log

POLL_INTERVAL = int(os.getenv("TELEGRAM_POLLING_INTERVAL", "3"))
DEBOUNCE_SHORT = 0.18   # 짧은 메시지 settle
DEBOUNCE_LONG = 0.6     # 긴/연속 메시지 settle 상한
WORKING_STALE = 1800    # working.json 30분 이상 = stale


def _has_unprocessed() -> bool:
    """messages.json 에 미처리 user 메시지가 있나 (seen 무시 — race 제거)."""
    try:
        data = load_telegram_messages()
    except Exception:
        return False
    for m in data.get("messages", []):
        if m.get("type") == "user" and not m.get("processed", False):
            return True
    return False


def _working_active() -> bool:
    """claude 가 작업 중(working.json)이고 stale 아닌가."""
    if not os.path.exists(WORKING_LOCK_FILE):
        return False
    try:
        import json
        import time
        info = json.load(open(WORKING_LOCK_FILE, encoding="utf-8"))
        last = info.get("last_activity") or info.get("started_at")
        if last:
            import datetime
            ts = datetime.datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            age = time.time() - ts.timestamp()
            if age > WORKING_STALE:
                _log(f"[WARN] stale working.json ({age:.0f}s) — ignoring")
                return False
        return True
    except Exception:
        return True  # 파싱 실패 시 보수적으로 active 취급


async def _debounce():
    """연속 메시지 합치기: 새 메시지가 계속 들어오는 동안 짧게 대기."""
    await asyncio.sleep(DEBOUNCE_SHORT)
    waited = DEBOUNCE_SHORT
    last_count = _count_unprocessed()
    while waited < DEBOUNCE_LONG:
        await asyncio.sleep(DEBOUNCE_SHORT)
        waited += DEBOUNCE_SHORT
        cur = _count_unprocessed()
        if cur == last_count:
            break  # 더 안 들어옴 → settle
        last_count = cur


def _count_unprocessed() -> int:
    try:
        data = load_telegram_messages()
    except Exception:
        return 0
    return sum(1 for m in data.get("messages", [])
               if m.get("type") == "user" and not m.get("processed", False))


async def _drain_sessions():
    """미처리 메시지가 없어질 때까지 claude 세션을 돌림 (씹힘 0 핵심).

    첫 세션은 cold('new'), 이후 흡수는 hot('continue').
    각 세션이 끝나면 그 사이 도착한 메시지까지 재확인.
    """
    mode = "new"
    while _has_unprocessed():
        if _working_active():
            # claude 가 이미 살아 작업 중 → 새 세션 안 띄움.
            # 현재 세션이 check_telegram 으로 흡수하거나, 끝나면 다음 루프에서 처리.
            _log("[INFO] working.json active — deferring to current session")
            return
        ec = await run_claude(mode)
        if ec != 0 and ec != -1:
            _log(f"[WARN] session exit {ec} — stop draining to avoid loop")
            return
        mode = "continue"
        await asyncio.sleep(0.5)  # 파일 flush 여유


async def main_loop():
    if not tl.setup_bot_token():
        _log("[ERROR] bot token not set")
        return
    # /stop 명령 메뉴 등록 + telegram sender register (reply-to-source)
    try:
        from ..channels.telegram import register_bot_commands_sync
        register_bot_commands_sync()
    except Exception as e:
        _log(f"[WARN] command register failed: {e}")

    # 부팅 시 잔존 executor.lock 정리 (bash 시절 잔재)
    for stale in (EXECUTOR_LOCK_FILE,):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except OSError:
            pass

    _log(f"[INFO] gateway started (poll={POLL_INTERVAL}s, debounce={DEBOUNCE_SHORT}-{DEBOUNCE_LONG}s)")

    # 부팅 시 미처리 메시지 있으면 먼저 처리 (재시작 복구)
    if _has_unprocessed():
        _log("[INFO] startup: unprocessed messages found → draining")
        await _drain_sessions()

    cycle = 0
    while True:
        cycle += 1
        try:
            result = await tl.fetch_new_messages()
            # fetch_new_messages: STOP 은 내부 처리 후 0 반환, 새 메시지는 count
            if result and result > 0:
                _log(f"[MSG] {result} new message(s)")
                await _debounce()
                await _drain_sessions()
            elif _has_unprocessed():
                # 폴링은 0 인데 미처리 잔존 (이전 세션 미흡수/재시작) → 처리
                await _drain_sessions()
        except Exception as e:
            _log(f"[ERROR] loop error: {e}")
        # 좀비 자식 reap
        try:
            while True:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
        except (ChildProcessError, OSError):
            pass
        await asyncio.sleep(POLL_INTERVAL)


def main():
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        _log("[INFO] gateway stopped (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
