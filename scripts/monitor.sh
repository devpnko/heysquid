#!/bin/bash
# heysquid TUI 모니터 (Textual)
# 사용법: bash scripts/monitor.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$ROOT/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

# 중복 실행 방지: 이미 TUI 모니터가 떠있으면 안내 후 종료
EXISTING=$(pgrep -f "scripts.tui_textual" | grep -v "$$")
if [ -n "$EXISTING" ]; then
    echo "⚠️  TUI 모니터가 이미 실행 중입니다 (PID: $EXISTING)"
    echo "   기존 창을 사용하거나, 먼저 종료 후 다시 실행하세요."
    exit 1
fi

cd "$ROOT" && exec "$VENV_PYTHON" -m scripts.tui_textual
