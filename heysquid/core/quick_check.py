#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick Telegram message check (before launching Claude Code) — heysquid v2

Since listener.py is already polling, this only checks for unprocessed
messages in messages.json without making API calls.

Exit Codes:
  0: No new messages (exit immediately)
  1: New messages found (Claude Code execution needed)
  2: Another task in progress (working.json lock)
"""

import os
import sys
import json
from datetime import datetime

from .paths import MESSAGES_FILE, WORKING_LOCK_FILE

RETRY_MAX = 3
EXPIRE_HOURS = 24


def get_first_unprocessed_chat_id():
    """Return the first chat_id from unprocessed messages"""
    if not os.path.exists(MESSAGES_FILE):
        return None

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        for msg in data.get("messages", []):
            if (msg.get("type") == "user"
                    and not msg.get("processed", False)
                    and not msg.get("seen", False)
                    and msg.get("retry_count", 0) < RETRY_MAX):
                return msg.get("chat_id")
    except Exception:
        pass

    return None


def _main():
    """CLI entry point — executor.sh calls this via `python -m heysquid.quick_check`."""
    try:
        # Check working lock
        if os.path.exists(WORKING_LOCK_FILE):
            print("[LOCK] Another task in progress")
            sys.exit(2)

        # Check for unprocessed messages in messages.json
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

            # Messages already seen by PM (seen=True) -> skip
            if msg.get("seen", False):
                continue

            # Unprocessed for over 24 hours -> force mark as processed
            try:
                ts = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
                age_hours = (now - ts).total_seconds() / 3600
                if age_hours > EXPIRE_HOURS:
                    print(f"[EXPIRE] Force-processing message older than 24h: {msg.get('message_id')}")
                    msg["processed"] = True
                    modified = True
                    continue
            except (KeyError, ValueError):
                pass

            # retry_count >= 3 -> skip
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
            print(f"[MSG] New message: [{ts}] {name}: {text}...")

        print(f"[MSG] Found {len(actionable)} new message(s)!")
        sys.exit(1)

    except Exception as e:
        print(f"[WARN] Error: {e}")
        sys.exit(0)


if __name__ == "__main__":
    _main()
