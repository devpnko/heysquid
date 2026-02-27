#!/bin/bash
# heysquid daemon management script
#
# Usage:
#   bash scripts/run.sh start     # Start daemon
#   bash scripts/run.sh stop      # Stop daemon
#   bash scripts/run.sh restart   # Restart daemon
#   bash scripts/run.sh status    # Check status
#   bash scripts/run.sh logs      # View recent logs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

WATCHER_PLIST="com.heysquid.watcher.plist"
SCHEDULER_PLIST="com.heysquid.scheduler.plist"
SLACK_PLIST="com.heysquid.slack.plist"
DISCORD_PLIST="com.heysquid.discord.plist"

WATCHER_SRC="$SCRIPT_DIR/$WATCHER_PLIST"
SCHEDULER_SRC="$SCRIPT_DIR/$SCHEDULER_PLIST"
SLACK_SRC="$SCRIPT_DIR/$SLACK_PLIST"
DISCORD_SRC="$SCRIPT_DIR/$DISCORD_PLIST"

WATCHER_DST="$LAUNCH_AGENTS/$WATCHER_PLIST"
SCHEDULER_DST="$LAUNCH_AGENTS/$SCHEDULER_PLIST"
SLACK_DST="$LAUNCH_AGENTS/$SLACK_PLIST"
DISCORD_DST="$LAUNCH_AGENTS/$DISCORD_PLIST"

# Legacy briefing plist (for cleanup)
BRIEFING_PLIST="com.heysquid.briefing.plist"
BRIEFING_DST="$LAUNCH_AGENTS/$BRIEFING_PLIST"

# Load .env (for token presence check)
if [ -f "$ROOT/heysquid/.env" ]; then
    set -a; source "$ROOT/heysquid/.env" 2>/dev/null; set +a
fi

case "${1:-}" in
    start)
        echo "Starting heysquid daemon..."

        # Ensure LaunchAgents directory exists
        mkdir -p "$LAUNCH_AGENTS"

        # Remove legacy briefing plist
        launchctl unload "$BRIEFING_DST" 2>/dev/null || true
        rm -f "$BRIEFING_DST" 2>/dev/null

        # Create symlinks (overwrite if already exists)
        ln -sf "$WATCHER_SRC" "$WATCHER_DST"
        ln -sf "$SCHEDULER_SRC" "$SCHEDULER_DST"

        # Register with launchd
        launchctl load "$WATCHER_DST" 2>/dev/null || true
        launchctl load "$SCHEDULER_DST" 2>/dev/null || true

        # Slack listener (only if token exists)
        if [ -n "$SLACK_BOT_TOKEN" ]; then
            ln -sf "$SLACK_SRC" "$SLACK_DST"
            launchctl load "$SLACK_DST" 2>/dev/null || true
            echo "[OK] Slack listener started (Socket Mode)"
        fi

        # Discord listener (only if token exists)
        if [ -n "$DISCORD_BOT_TOKEN" ]; then
            ln -sf "$DISCORD_SRC" "$DISCORD_DST"
            launchctl load "$DISCORD_DST" 2>/dev/null || true
            echo "[OK] Discord listener started (Gateway)"
        fi

        # Dashboard HTTP server
        if ! lsof -i :8420 > /dev/null 2>&1; then
            nohup bash "$SCRIPT_DIR/serve_dashboard.sh" > "$ROOT/logs/dashboard_server.log" 2>&1 &
            echo "[OK] Dashboard server (http://localhost:8420/dashboard.html)"
        else
            echo "[OK] Dashboard server already running"
        fi

        echo "[OK] Telegram listener started (10s polling + immediate executor trigger)"
        echo "[OK] scheduler registered (1-minute interval -- automatic skill execution)"
        echo ""
        echo "Dashboard: http://localhost:8420/dashboard.html"
        echo "TUI monitor: bash scripts/monitor.sh"
        echo "Logs: tail -f logs/executor.log"
        echo "Check status: bash scripts/run.sh status"
        ;;

    stop)
        echo "Stopping heysquid daemon..."

        launchctl unload "$WATCHER_DST" 2>/dev/null || true
        launchctl unload "$SCHEDULER_DST" 2>/dev/null || true
        launchctl unload "$SLACK_DST" 2>/dev/null || true
        launchctl unload "$DISCORD_DST" 2>/dev/null || true
        launchctl unload "$BRIEFING_DST" 2>/dev/null || true

        # H-5: Remove symlinks (prevent stale symlinks)
        rm -f "$WATCHER_DST" "$SCHEDULER_DST" "$SLACK_DST" "$DISCORD_DST" "$BRIEFING_DST" 2>/dev/null

        # Stop dashboard server
        pkill -f "http.server 8420" 2>/dev/null || true

        # Terminate all executor + Claude + caffeinate processes
        # claude CLI rewrites cmdline to "claude", so track via caffeinate (immutable) -> parent (claude)
        pkill -f "bash.*executor.sh" 2>/dev/null || true

        CAFE_PIDS=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null || true)
        if [ -n "$CAFE_PIDS" ]; then
            for CPID in $CAFE_PIDS; do
                PARENT=$(ps -p "$CPID" -o ppid= 2>/dev/null | tr -d ' ')
                [ -n "$PARENT" ] && kill "$PARENT" 2>/dev/null
                kill "$CPID" 2>/dev/null
            done
        fi
        pkill -f "append-system-prompt-file" 2>/dev/null || true
        pkill -f "tee.*executor.stream" 2>/dev/null || true

        # PID file fallback
        if [ -f "$ROOT/data/claude.pid" ]; then
            while IFS= read -r PID; do
                [ -n "$PID" ] && kill "$PID" 2>/dev/null || true
            done < "$ROOT/data/claude.pid"
            rm -f "$ROOT/data/claude.pid"
        fi

        # Wait then force kill
        sleep 2
        CAFE_PIDS=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null || true)
        if [ -n "$CAFE_PIDS" ]; then
            echo "[WARN] Claude did not terminate gracefully, force killing (kill -9)..."
            for CPID in $CAFE_PIDS; do
                PARENT=$(ps -p "$CPID" -o ppid= 2>/dev/null | tr -d ' ')
                [ -n "$PARENT" ] && kill -9 "$PARENT" 2>/dev/null || true
                kill -9 "$CPID" 2>/dev/null || true
            done
            pkill -9 -f "append-system-prompt-file" 2>/dev/null || true
            sleep 1
        fi

        # H-4: Terminate Slack/Discord listener processes
        pkill -f "slack_listener" 2>/dev/null || true
        pkill -f "discord_listener" 2>/dev/null || true

        # Clean up lock files (executor.lock may remain from wait loop)
        rm -f "$ROOT/data/executor.lock" 2>/dev/null
        rm -f "$ROOT/data/executor.pid" 2>/dev/null
        rm -f "$ROOT/data/working.json" 2>/dev/null

        echo "[OK] Daemon stopped and lock files cleaned up"
        ;;

    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;

    status)
        echo "=== heysquid daemon status ==="
        echo ""

        echo "--- Listeners ---"
        if launchctl list 2>/dev/null | grep -q "com.heysquid.watcher"; then
            echo "  [TG] Telegram: running"
        else
            echo "  [TG] Telegram: stopped"
        fi
        if launchctl list 2>/dev/null | grep -q "com.heysquid.slack"; then
            echo "  [SL] Slack: running"
        elif [ -n "$SLACK_BOT_TOKEN" ]; then
            echo "  [SL] Slack: stopped (token configured)"
        else
            echo "  [SL] Slack: not configured"
        fi
        if launchctl list 2>/dev/null | grep -q "com.heysquid.discord"; then
            echo "  [DC] Discord: running"
        elif [ -n "$DISCORD_BOT_TOKEN" ]; then
            echo "  [DC] Discord: stopped (token configured)"
        else
            echo "  [DC] Discord: not configured"
        fi

        echo ""
        echo "--- scheduler (automatic skill execution) ---"
        if launchctl list 2>/dev/null | grep -q "com.heysquid.scheduler"; then
            echo "  Status: running"
            launchctl list | grep "com.heysquid.scheduler"
        else
            echo "  Status: stopped"
        fi

        echo ""
        echo "--- Processes ---"
        if pgrep -f "telegram_listener" > /dev/null 2>&1; then
            echo "  Telegram listener: running"
        else
            echo "  Telegram listener: stopped"
        fi
        if pgrep -f "slack_listener" > /dev/null 2>&1; then
            echo "  Slack listener: running"
        else
            echo "  Slack listener: stopped"
        fi
        if pgrep -f "discord_listener" > /dev/null 2>&1; then
            echo "  Discord listener: running"
        else
            echo "  Discord listener: stopped"
        fi

        if pgrep -f "executor.sh" > /dev/null 2>&1; then
            echo "  executor.sh: running"
        else
            echo "  executor.sh: idle"
        fi

        if pgrep -f "claude.*append-system-prompt-file" > /dev/null 2>&1; then
            echo "  Claude Code: working"
        else
            echo "  Claude Code: idle"
        fi

        echo ""
        echo "--- Dashboard server ---"
        if lsof -i :8420 > /dev/null 2>&1; then
            echo "  Status: running (http://localhost:8420/dashboard.html)"
        else
            echo "  Status: stopped"
        fi

        # Check lock files
        echo ""
        echo "--- Lock files ---"
        if [ -f "$ROOT/data/executor.lock" ]; then
            echo "  executor.lock: present ($(cat "$ROOT/data/executor.lock"))"
        else
            echo "  executor.lock: none"
        fi

        if [ -f "$ROOT/data/working.json" ]; then
            echo "  working.json: present"
        else
            echo "  working.json: none"
        fi

        echo ""
        echo "--- Registered skills ---"
        "$ROOT/venv/bin/python" -c "
from heysquid.skills._base import discover_skills
skills = discover_skills()
if not skills:
    print('  (no registered skills)')
else:
    for name, meta in skills.items():
        trigger = meta.get('trigger', '?')
        schedule = meta.get('schedule', '')
        desc = meta.get('description', '')
        info = f'{trigger}'
        if schedule:
            info += f' @ {schedule}'
        print(f'  {name}: {desc} [{info}]')
" 2>/dev/null || echo "  (failed to list skills)"
        ;;

    logs)
        echo "=== Recent logs (executor) ==="
        if [ -f "$ROOT/logs/executor.log" ]; then
            tail -30 "$ROOT/logs/executor.log"
        else
            echo "(no logs)"
        fi

        echo ""
        echo "=== Recent logs (TG listener) ==="
        if [ -f "$ROOT/logs/listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/listener.stdout.log"
        else
            echo "(no logs)"
        fi

        echo ""
        echo "=== Recent logs (SL listener) ==="
        if [ -f "$ROOT/logs/slack_listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/slack_listener.stdout.log"
        else
            echo "(no logs)"
        fi

        echo ""
        echo "=== Recent logs (DC listener) ==="
        if [ -f "$ROOT/logs/discord_listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/discord_listener.stdout.log"
        else
            echo "(no logs)"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start    Start daemon (watcher + scheduler + listeners)"
        echo "  stop     Stop daemon"
        echo "  restart  Restart daemon"
        echo "  status   Check status"
        echo "  logs     View recent logs"
        exit 1
        ;;
esac
