#!/bin/bash
# heysquid TUI 모니터 (Textual)
# 사용법: bash scripts/monitor.sh
# curses 버전: bash scripts/monitor.sh --curses

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

if [ "$1" = "--curses" ]; then
    exec "$VENV_PYTHON" "$ROOT/scripts/tui_monitor.py"
else
    cd "$ROOT" && exec "$VENV_PYTHON" -m scripts.tui_textual
fi
