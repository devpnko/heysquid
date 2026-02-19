#!/bin/bash
# heysquid TUI 모니터
# 사용법: bash scripts/monitor.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

exec "$VENV_PYTHON" "$ROOT/scripts/tui_monitor.py"
