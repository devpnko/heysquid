#!/bin/bash
# heysquid executor — Mac port (mybot_autoexecutor.bat -> executor.sh)
#
# Core logic:
# 1. Verify Claude CLI installation
# 2. Detect process collisions (triple safety check)
# 3. Check for new messages via quick_check.py
# 4. Attempt session resume (claude -p -c) -> fall back to new session
# 5. Clean up lock files

set -euo pipefail

# Disable Claude Code nested session prevention (executor runs as an independent session)
unset CLAUDECODE 2>/dev/null || true

# Path configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
HEYSQUID_DIR="$ROOT/heysquid"
SPF="$ROOT/CLAUDE.md"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/executor.log"
STREAM_LOG="$LOG_DIR/executor.stream.jsonl"
LOCKFILE="$ROOT/data/executor.lock"
PIDFILE="$ROOT/data/claude.pid"
EXECUTOR_PIDFILE="$ROOT/data/executor.pid"

# Create log directories
mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/data"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

# ========================================
# PM process kill function
# ========================================
# claude CLI rewrites its cmdline to "claude" after start, so pgrep cannot find it.
# Solution: caffeinate (system binary, cmdline immutable) -> parent PID = actual claude.
# No PID file needed, works in any environment.

kill_all_pm() {
    # Primary: PID file (most reliable -- catches orphan claude too)
    if [ -f "$PIDFILE" ]; then
        while IFS= read -r OLD_PID; do
            [ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null && log "[KILL] PID=$OLD_PID (from pidfile)"
        done < "$PIDFILE"
    fi
    # Secondary: find caffeinate -> kill parent (claude)
    local CAFE_PIDS
    CAFE_PIDS=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null || true)
    if [ -n "$CAFE_PIDS" ]; then
        for CPID in $CAFE_PIDS; do
            local PARENT
            PARENT=$(ps -p "$CPID" -o ppid= 2>/dev/null | tr -d ' ')
            [ -n "$PARENT" ] && kill "$PARENT" 2>/dev/null && log "[KILL] claude PID=$PARENT (parent of cafe=$CPID)"
            kill "$CPID" 2>/dev/null && log "[KILL] caffeinate PID=$CPID"
        done
    fi
    # Tertiary: pgrep pattern (append-system-prompt-file)
    pkill -f "append-system-prompt-file" 2>/dev/null || true
    sleep 2
    # force kill (-9): PID file + caffeinate pattern
    if [ -f "$PIDFILE" ]; then
        while IFS= read -r OLD_PID; do
            if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                kill -9 "$OLD_PID" 2>/dev/null && log "[KILL-9] PID=$OLD_PID (from pidfile)"
            fi
        done < "$PIDFILE"
    fi
    CAFE_PIDS=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null || true)
    if [ -n "$CAFE_PIDS" ]; then
        for CPID in $CAFE_PIDS; do
            local PARENT
            PARENT=$(ps -p "$CPID" -o ppid= 2>/dev/null | tr -d ' ')
            [ -n "$PARENT" ] && kill -9 "$PARENT" 2>/dev/null || true
            kill -9 "$CPID" 2>/dev/null || true
        done
    fi
    pkill -9 -f "append-system-prompt-file" 2>/dev/null || true
    # Verify processes are dead, then delete PID file
    if [ -f "$PIDFILE" ]; then
        local SURVIVOR=0
        while IFS= read -r OLD_PID; do
            if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                log "[WARN] PM survived kill: PID=$OLD_PID"
                SURVIVOR=1
            fi
        done < "$PIDFILE"
        if [ "$SURVIVOR" -eq 0 ]; then
            rm -f "$PIDFILE"
        else
            log "[ERROR] Some PM processes survived! PID file retained."
        fi
    fi
}

is_pm_alive() {
    # Primary: caffeinate pattern (normal state)
    if pgrep -f "caffeinate.*append-system-prompt-file" > /dev/null 2>&1; then
        return 0
    fi
    # Secondary: PID file (caffeinate dead, claude orphaned)
    if [ -f "$PIDFILE" ]; then
        while IFS= read -r OLD_PID; do
            if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
                log "[WARN] Orphan PM detected: PID=$OLD_PID (no caffeinate)"
                return 0
            fi
        done < "$PIDFILE"
    fi
    return 1
}

# ========================================
# Trap handler
# ========================================
cleanup() {
    local exit_code=${?:-0}
    log "[CLEANUP] executor.sh exiting (code=$exit_code)"
    # Clean up stream_viewer + tail (both spawned by this session and orphan processes)
    [ -n "${VIEWER_PID:-}" ] && kill "$VIEWER_PID" 2>/dev/null || true
    pkill -f "stream_viewer.py" 2>/dev/null || true
    pkill -f "tail.*executor.stream" 2>/dev/null || true
    kill_all_pm
    rm -f "$LOCKFILE" "$EXECUTOR_PIDFILE" 2>/dev/null
    log "[CLEANUP] Done."
}
trap cleanup EXIT INT TERM

# ========================================
# Claude CLI auto-detection
# ========================================
CLAUDE_EXE=""

if command -v claude &>/dev/null; then
    CLAUDE_EXE="$(command -v claude)"
    log "[INFO] Using Claude CLI: $CLAUDE_EXE"
elif [ -f "$HOME/.local/bin/claude" ]; then
    CLAUDE_EXE="$HOME/.local/bin/claude"
    log "[INFO] Using Claude CLI: $CLAUDE_EXE"
elif [ -f "/usr/local/bin/claude" ]; then
    CLAUDE_EXE="/usr/local/bin/claude"
    log "[INFO] Using Claude CLI: $CLAUDE_EXE"
else
    log "[ERROR] Claude CLI not found"
    log "  Searched: PATH, ~/.local/bin/claude, /usr/local/bin/claude"
    exit 99
fi

log "===== START ====="
log "ROOT=$ROOT"
log "CWD=$(pwd)"

# Record executor.sh's own PID (used for dedup check by trigger_executor)
echo $$ > "$EXECUTOR_PIDFILE"
log "[INFO] executor.pid=$$"

# ========================================
# Clean up zombie stream_viewer / tail processes
# ========================================
# Leftover stream_viewer from a previous session can pollute agent_status.json with old code
ZOMBIE_VIEWERS=$(pgrep -f "stream_viewer.py" 2>/dev/null || true)
if [ -n "$ZOMBIE_VIEWERS" ]; then
    for ZPID in $ZOMBIE_VIEWERS; do
        kill "$ZPID" 2>/dev/null && log "[CLEANUP] Killed zombie stream_viewer PID=$ZPID"
    done
    sleep 1
fi
ZOMBIE_TAILS=$(pgrep -f "tail.*executor.stream" 2>/dev/null || true)
if [ -n "$ZOMBIE_TAILS" ]; then
    for ZPID in $ZOMBIE_TAILS; do
        kill "$ZPID" 2>/dev/null && log "[CLEANUP] Killed zombie tail PID=$ZPID"
    done
fi

# ========================================
# Prevent duplicate process execution
# ========================================

if is_pm_alive; then
    if [ -f "$STREAM_LOG" ]; then
        LOG_AGE=$(( $(date +%s) - $(stat -f %m "$STREAM_LOG" 2>/dev/null || echo 0) ))
        if [ "$LOG_AGE" -gt 1800 ]; then
            log "[STALE] Claude PM idle >30m. Killing..."
            kill_all_pm
            rm -f "$LOCKFILE" 2>/dev/null
            log "[STALE] Cleared. Proceeding..."
        else
            log "[BLOCKED] Claude PM session active."
            exit 98
        fi
    else
        log "[BLOCKED] Claude PM session active."
        exit 98
    fi
fi

# 2. Check lock file (listener creates pre-lock, so we don't delete here)
#    executor.sh overwrites the lock at step 4. Cleans up on no-message exit.
if [ -f "$LOCKFILE" ]; then
    log "[INFO] Lock file exists (pre-lock by listener or previous crash). Proceeding..."
fi

# 3. Quick message check (check via Python first)
log "[QUICK_CHECK] Checking for new messages..."
cd "$ROOT"

VENV_PYTHON="$ROOT/venv/bin/python3"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

CHECK_RESULT=0
"$VENV_PYTHON" -m heysquid.quick_check >> "$LOG" 2>&1 || CHECK_RESULT=$?

if [ "$CHECK_RESULT" -eq 0 ]; then
    log "[NO_MESSAGE] No new messages. Exiting."
    rm -f "$LOCKFILE" 2>/dev/null
    log ""
    exit 0
fi

log "[NEW_MESSAGE] New messages found. Starting Claude Code..."

# 4. Create lock file
echo "$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCKFILE"
log "Lock file created: $LOCKFILE"

# (Start notification already sent by listener, so skipped here)

# Verify CLAUDE.md exists
if [ ! -f "$SPF" ]; then
    log "[ERROR] CLAUDE.md not found: $SPF"
    rm -f "$LOCKFILE" 2>/dev/null
    exit 2
fi

# Record Claude version
"$CLAUDE_EXE" --version >> "$LOG" 2>&1 || true

export DISABLE_AUTOUPDATER=1

# Claude execution prompt — PM mode
PROMPT="Act as a PM following the instructions in CLAUDE.md.
1) Read data/identity.json to identify yourself (display_name is your name) and the user.
2) Read data/permanent_memory.md to understand persistent memory (user preferences, key decisions, lessons learned).
3) Read data/session_memory.md to understand recent conversation context and active tasks.
4) Call check_crash_recovery() to check for abnormal termination of the previous session.
   - If return value exists: the previous task was interrupted. Notify the user and continue processing.
     The recovery info contains the original message and task details, so do not ask the user again.
   - If None: normal startup.
4.5) Call check_interrupted() to check for intentional user interruption.
   - If return value exists: the user interrupted the previous task. Remember the previous task context,
     but do not automatically resume. Always check new messages first, then act based on intent:
     * 'continue' / 'resume' -> resume previous task
     * 'forget that, do X instead' -> start new task
     * 'do that but change X' -> modify and apply previous context
   - If None: no interruption.
5) Call check_telegram() from heysquid/telegram_bot.py to check for new messages.
6) Evaluate the message content as a PM and respond appropriately.
   - Conversation (greetings/questions/chat) -> reply naturally via reply_telegram().
   - Task request -> explain the plan and ask for confirmation.
   - Confirmation/approval -> switch to execution mode and perform the task.
7) After completing a task/response, do not exit immediately. Follow the 'standby mode' instructions in CLAUDE.md to run a permanent wait loop.
   - sleep 30 -> poll_new_messages() -> process if new messages exist
   - No timeout. The session is permanent. Never terminate on your own.
   - Auto-refresh session_memory.md every 30 minutes (intermediate save).
8) If important decisions/lessons/preferences arise during the session, record them in data/permanent_memory.md.
   - Only things worth permanently keeping (user preferences, key decisions, recurring lessons)
   - Keep under 200 lines.
Use send_message_sync() from heysquid/telegram_sender.py for all Telegram responses.
Use reply_telegram() from heysquid/telegram_bot.py for quick conversational replies."

# Set working directory to project root
cd "$ROOT"

# Conditional stream log reset (only reset if stale 30m+, otherwise keep)
if [ -f "$STREAM_LOG" ]; then
    LOG_AGE=$(( $(date +%s) - $(stat -f%m "$STREAM_LOG" 2>/dev/null || echo 0) ))
    if [ "$LOG_AGE" -gt 1800 ]; then
        > "$STREAM_LOG"
        log "[INFO] Stream log reset (stale ${LOG_AGE}s)"
    fi
else
    > "$STREAM_LOG"
fi

VIEWER="$ROOT/scripts/stream_viewer.py"

# Always start a new session (no session resume -- context recovered via memory system)
log "[INFO] Starting new session (permanent memory + session memory)..."

# Claude -> tee -> log file (stream_viewer is separated -- its crash does not affect claude)
caffeinate -ims "$CLAUDE_EXE" -p --dangerously-skip-permissions \
    --model sonnet \
    --output-format stream-json --verbose \
    --append-system-prompt-file "$SPF" \
    "$PROMPT" \
    2>> "$LOG" | tee -a "$STREAM_LOG" > /dev/null &
PIPE_PID=$!

# stream_viewer: independent process (auto-restart on crash, decoupled from claude pipe)
_run_stream_viewer() {
    sleep 1  # Wait for tee to start writing to file
    while kill -0 "$PIPE_PID" 2>/dev/null; do
        tail -n 0 -F "$STREAM_LOG" 2>/dev/null | "$VENV_PYTHON" -u "$VIEWER" 2>> "$LOG" || true
        # Restart if viewer dies (tail also naturally exits via SIGPIPE)
        kill -0 "$PIPE_PID" 2>/dev/null || break
        log "[WARN] stream_viewer exited, restarting in 2s..."
        sleep 2
    done
}
_run_stream_viewer &
VIEWER_PID=$!

# Record caffeinate PID + actual claude PID
# Process structure: claude (parent) -> caffeinate (child)
# claude CLI rewrites cmdline to "claude", so PID file is the only tracking method
sleep 2
CAFE_PID=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null | head -1 || true)
CLAUDE_PID=""
if [ -n "$CAFE_PID" ]; then
    # claude is the parent of caffeinate (PPID)
    CLAUDE_PID=$(ps -p "$CAFE_PID" -o ppid= 2>/dev/null | tr -d ' ')
fi
# fallback: save caffeinate PID itself at minimum
if [ -z "$CLAUDE_PID" ]; then
    CLAUDE_PID=$(pgrep -f "append-system-prompt-file" 2>/dev/null | head -1 || true)
fi
# Save both to PID file (one per line, deduplicated)
: > "$PIDFILE"
[ -n "$CLAUDE_PID" ] && echo "$CLAUDE_PID" >> "$PIDFILE"
[ -n "$CAFE_PID" ] && [ "$CAFE_PID" != "$CLAUDE_PID" ] && echo "$CAFE_PID" >> "$PIDFILE"
log "[INFO] Saved PIDs: claude=$CLAUDE_PID cafe=$CAFE_PID"

# Wait for pipeline to complete
EC=0
wait $PIPE_PID || EC=$?

log "EXITCODE=$EC"
log ""

# cleanup runs automatically via trap EXIT
exit $EC
