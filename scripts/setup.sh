#!/bin/bash
# heysquid initial setup script
#
# Usage: bash scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
HEYSQUID_DIR="$ROOT/heysquid"

echo "========================================"
echo "  heysquid initial setup"
echo "========================================"
echo ""

# 1. Check Python
echo "[1/6] Checking Python..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "  $PY_VER"
else
    echo "  [ERROR] Python3 is not installed."
    echo "  brew install python3"
    exit 1
fi

# 2. Create Python venv
echo ""
echo "[2/6] Creating Python virtual environment..."
if [ -d "$ROOT/venv" ]; then
    echo "  Already exists: $ROOT/venv"
else
    python3 -m venv "$ROOT/venv"
    echo "  [OK] venv created"
fi

# 3. pip install
echo ""
echo "[3/6] Installing dependencies..."
source "$ROOT/venv/bin/activate"
pip install -r "$HEYSQUID_DIR/requirements.txt" --quiet
echo "  [OK] Dependencies installed"

# 4. Configure .env file
echo ""
echo "[4/6] Configuring .env file..."
if [ -f "$HEYSQUID_DIR/.env" ]; then
    echo "  Already exists: $HEYSQUID_DIR/.env"
else
    cp "$HEYSQUID_DIR/.env.example" "$HEYSQUID_DIR/.env"
    echo "  Copied .env.example."
    echo ""
    echo "  *** Configuration required ***"
    echo "  Open $HEYSQUID_DIR/.env and set the following values:"
    echo ""
    echo "    TELEGRAM_BOT_TOKEN=<bot token from @BotFather>"
    echo "    TELEGRAM_ALLOWED_USERS=<allowed Telegram user IDs>"
    echo ""
fi

# 5. Create directories
echo ""
echo "[5/6] Creating directories..."
mkdir -p "$ROOT/data"
mkdir -p "$ROOT/tasks"
mkdir -p "$ROOT/workspaces"
mkdir -p "$ROOT/logs"
echo "  [OK] data/, tasks/, workspaces/, logs/ created"

# 6. launchd symlinks
echo ""
echo "[6/6] Configuring launchd..."
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"

ln -sf "$SCRIPT_DIR/com.heysquid.watcher.plist" "$LAUNCH_AGENTS/com.heysquid.watcher.plist"
ln -sf "$SCRIPT_DIR/com.heysquid.briefing.plist" "$LAUNCH_AGENTS/com.heysquid.briefing.plist"
echo "  [OK] plist symlinks created"

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Set bot token in $HEYSQUID_DIR/.env"
echo "  2. bash scripts/run.sh start  (start daemon)"
echo "  3. Send a message on Telegram"
echo ""
echo "Manual testing:"
echo "  source venv/bin/activate"
echo "  python heysquid/telegram_listener.py  (test message reception)"
echo "  bash scripts/executor.sh              (run executor manually)"
echo ""
