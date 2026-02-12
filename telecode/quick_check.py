#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
빠른 텔레그램 메시지 확인 (Claude Code 실행 전) — telecode v2

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
MESSAGES_FILE = os.path.join(DATA_DIR, "telegram_messages.json")
WORKING_LOCK_FILE = os.path.join(DATA_DIR, "working.json")

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

    unprocessed = [
        msg for msg in data.get("messages", [])
        if msg.get("type") == "user" and not msg.get("processed", False)
    ]

    if not unprocessed:
        sys.exit(0)

    for msg in unprocessed:
        text = msg.get("text", "")[:50]
        name = msg.get("first_name", "?")
        ts = msg.get("timestamp", "?")
        print(f"[MSG] 새 메시지: [{ts}] {name}: {text}...")

    print(f"[MSG] 새 메시지 {len(unprocessed)}개 발견!")
    sys.exit(1)

except Exception as e:
    print(f"[WARN] 오류: {e}")
    sys.exit(0)
