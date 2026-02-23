#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="$ROOT/venv/bin/python"
[ ! -f "$PYTHON" ] && PYTHON="python3"
exec "$PYTHON" "$SCRIPT_DIR/serve_dashboard.py"
