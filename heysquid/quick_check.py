#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
빠른 텔레그램 메시지 확인 (Claude Code 실행 전) — heysquid v2

listener.py가 이미 폴링하고 있으므로, API 호출 없이
telegram_messages.json에서 미처리 메시지만 확인.

Exit Codes:
  0: 새 메시지 없음 (즉시 종료)
  1: 새 메시지 있음 (Claude Code 실행 필요)
  2: 다른 작업 진행 중 (working.json 잠금)
"""

import os
import sys
import json
from datetime import datetime

from .config import DATA_DIR_STR as DATA_DIR

MESSAGES_FILE = os.path.join(DATA_DIR, "telegram_messages.json")
WORKING_LOCK_FILE = os.path.join(DATA_DIR, "working.json")

RETRY_MAX = 3
EXPIRE_HOURS = 24


def get_first_unprocessed_chat_id():
    """미처리 메시지의 첫 번째 chat_id 반환"""
    if not os.path.exists(MESSAGES_FILE):
        return None

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for msg in data.get("messages", []):
            if (msg.get("type") == "user"
                    and not msg.get("processed", False)
                    and msg.get("retry_count", 0) < RETRY_MAX):
                return msg.get("chat_id")
    except Exception:
        pass

    return None


def _main():
    """CLI entry point — executor.sh calls this via `python -m heysquid.quick_check`."""
    try:
        # working lock 확인
        if os.path.exists(WORKING_LOCK_FILE):
            print("[LOCK] 다른 작업 진행 중")
            sys.exit(2)

        # telegram_messages.json에서 미처리 메시지 확인
        if not os.path.exists(MESSAGES_FILE):
            sys.exit(0)

        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        now = datetime.now()
        modified = False

        actionable = []
        for msg in data.get("messages", []):
            if msg.get("type") != "user" or msg.get("processed", False):
                continue

            # 24시간 초과 미처리 → 강제 완료 처리
            try:
                ts = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                age_hours = (now - ts).total_seconds() / 3600
                if age_hours > EXPIRE_HOURS:
                    print(f"[EXPIRE] 24시간 초과 메시지 강제 처리: {msg.get('message_id')}")
                    msg["processed"] = True
                    modified = True
                    continue
            except (KeyError, ValueError):
                pass

            # retry_count >= 3 → 스킵
            if msg.get("retry_count", 0) >= RETRY_MAX:
                continue

            actionable.append(msg)

        if modified:
            with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        if not actionable:
            sys.exit(0)

        for msg in actionable:
            text = msg.get("text", "")[:50]
            name = msg.get("first_name", "?")
            ts = msg.get("timestamp", "?")
            print(f"[MSG] 새 메시지: [{ts}] {name}: {text}...")

        print(f"[MSG] 새 메시지 {len(actionable)}개 발견!")
        sys.exit(1)

    except Exception as e:
        print(f"[WARN] 오류: {e}")
        sys.exit(0)


if __name__ == "__main__":
    _main()
