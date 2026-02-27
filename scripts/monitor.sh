#!/bin/bash
# heysquid TUI monitor (Textual)
# Usage: bash scripts/monitor.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

# Prevent duplicate execution: if TUI monitor is already running, notify and exit
EXISTING=$(pgrep -f "scripts.tui_textual" | grep -v "$$")
if [ -n "$EXISTING" ]; then
    echo "WARNING: TUI monitor is already running (PID: $EXISTING)"
    echo "   Use the existing window, or stop it first before restarting."
    exit 1
fi

cd "$ROOT" && exec "$VENV_PYTHON" -m scripts.tui_textual
