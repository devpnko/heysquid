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

# Persistent session loop config
IDLE_POLL_INTERVAL=2        # seconds between message checks during idle
IDLE_TIMEOUT=1800           # 30min inactivity -> exit session
CONTINUE_PROMPT="New messages arrived. Process them now.
Call check_telegram() to get the new messages, then handle them following PM workflow.
Do not re-read identity.json or memory files — your context is preserved from this session."

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
    # Kill watchdog first (prevent it from firing during cleanup)
    [ -n "${WATCHDOG_PID:-}" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
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
7) After completing the task/response, save session_memory.md, then finish and exit cleanly.
   The executor handles session persistence externally — do NOT run standby loops or sleep commands.
8) If important decisions/lessons/preferences arise during the session, record them in data/permanent_memory.md.
   - Only things worth permanently keeping (user preferences, key decisions, recurring lessons)
   - Keep under 200 lines.
IMPORTANT: Always use reply_telegram() from heysquid/telegram_bot.py for ALL responses.
Never call send_message_sync() directly — it only sends to one channel and causes duplicate messages."

# Set working directory to project root
cd "$ROOT"

# Always reset stream log for new session (clean slate for watchdog detection)
if [ -f "$STREAM_LOG" ]; then
    LOG_AGE=$(( $(date +%s) - $(stat -f%m "$STREAM_LOG" 2>/dev/null || echo 0) ))
    log "[INFO] Stream log reset (was ${LOG_AGE}s old)"
fi
> "$STREAM_LOG"

VIEWER="$ROOT/scripts/stream_viewer.py"

# ========================================
# Session-end watchdog
# ========================================
# Problem: Claude spawns child processes (standby loops) via Bash tool.
# These children keep Claude alive even after the AI session ends,
# so `wait $PIPE_PID` never returns and executor hangs forever.
# Fix: monitor stream log for session-end marker, then kill orphan children.
_session_watchdog() {
    local GRACE=5       # seconds to wait after session end before killing
    local POLL=10       # seconds between checks
    local INITIAL=60    # seconds to wait before first check (session startup)

    sleep "$INITIAL"

    while kill -0 "$PIPE_PID" 2>/dev/null; do
        # Check for session-end marker in stream log
        if grep -q '"type":"result"' "$STREAM_LOG" 2>/dev/null; then
            log "[WATCHDOG] Session end detected (type:result). Waiting ${GRACE}s grace period..."
            sleep "$GRACE"

            # Double-check: is the pipeline still alive?
            if ! kill -0 "$PIPE_PID" 2>/dev/null; then
                log "[WATCHDOG] Pipeline already exited. No action needed."
                return 0
            fi

            # Kill Claude's orphan children (standby loops, reply scripts)
            if [ -n "${CLAUDE_PID:-}" ] && kill -0 "$CLAUDE_PID" 2>/dev/null; then
                log "[WATCHDOG] Killing children of claude PID=$CLAUDE_PID..."
                pkill -P "$CLAUDE_PID" 2>/dev/null || true
                sleep 3
            fi

            # If still alive, escalate
            if kill -0 "$PIPE_PID" 2>/dev/null; then
                log "[WATCHDOG] Pipeline still alive after child kill. Running kill_all_pm..."
                kill_all_pm
                sleep 2
            fi

            # Final: force-kill the pipeline itself
            if kill -0 "$PIPE_PID" 2>/dev/null; then
                log "[WATCHDOG] Force-killing pipeline PID=$PIPE_PID"
                kill "$PIPE_PID" 2>/dev/null || true
                sleep 1
                kill -9 "$PIPE_PID" 2>/dev/null || true
            fi

            log "[WATCHDOG] Cleanup complete."
            return 0
        fi

        sleep "$POLL"
    done
    log "[WATCHDOG] Pipeline exited normally. No intervention needed."
}

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

# ========================================
# Claude iteration runner (single invocation)
# ========================================
_run_claude_iteration() {
    local MODE="$1"       # "new" or "continue"
    local ITER_PROMPT="$2"

    # Kill previous watchdog/viewer if any
    [ -n "${WATCHDOG_PID:-}" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
    [ -n "${VIEWER_PID:-}" ] && kill "$VIEWER_PID" 2>/dev/null || true
    WATCHDOG_PID=""
    VIEWER_PID=""

    # Reset stream log for clean watchdog detection
    > "$STREAM_LOG"

    # Launch Claude
    if [ "$MODE" = "continue" ]; then
        log "[INFO] Continuing session (hot start)..."
        "$CLAUDE_EXE" -p -c --dangerously-skip-permissions \
            --model sonnet \
            --output-format stream-json --verbose \
            --append-system-prompt-file "$SPF" \
            "$ITER_PROMPT" \
            2>> "$LOG" | tee -a "$STREAM_LOG" > /dev/null &
    else
        log "[INFO] Starting new session (permanent memory + session memory)..."
        "$CLAUDE_EXE" -p --dangerously-skip-permissions \
            --model sonnet \
            --output-format stream-json --verbose \
            --append-system-prompt-file "$SPF" \
            "$ITER_PROMPT" \
            2>> "$LOG" | tee -a "$STREAM_LOG" > /dev/null &
    fi
    PIPE_PID=$!

    # Start stream viewer
    _run_stream_viewer &
    VIEWER_PID=$!

    # Record caffeinate PID + actual claude PID
    sleep 2
    CAFE_PID=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null | head -1 || true)
    CLAUDE_PID=""
    if [ -n "$CAFE_PID" ]; then
        CLAUDE_PID=$(ps -p "$CAFE_PID" -o ppid= 2>/dev/null | tr -d ' ')
    fi
    if [ -z "$CLAUDE_PID" ]; then
        CLAUDE_PID=$(pgrep -f "append-system-prompt-file" 2>/dev/null | head -1 || true)
    fi
    : > "$PIDFILE"
    [ -n "$CLAUDE_PID" ] && echo "$CLAUDE_PID" >> "$PIDFILE"
    [ -n "$CAFE_PID" ] && [ "$CAFE_PID" != "$CLAUDE_PID" ] && echo "$CAFE_PID" >> "$PIDFILE"
    log "[INFO] Saved PIDs: claude=$CLAUDE_PID cafe=$CAFE_PID"

    # Start session-end watchdog
    _session_watchdog &
    WATCHDOG_PID=$!
    log "[INFO] Watchdog started: PID=$WATCHDOG_PID"

    # Wait for Claude to complete
    local EC=0
    wait $PIPE_PID || EC=$?

    # Clean up watchdog/viewer for this iteration
    [ -n "$WATCHDOG_PID" ] && kill "$WATCHDOG_PID" 2>/dev/null || true
    [ -n "$VIEWER_PID" ] && kill "$VIEWER_PID" 2>/dev/null || true
    WATCHDOG_PID=""
    VIEWER_PID=""

    log "[INFO] Claude iteration done (exit=$EC, mode=$MODE)"
    return $EC
}

# ========================================
# Main execution loop
# ========================================

# First invocation (cold start)
_run_claude_iteration "new" "$PROMPT"
FIRST_EC=$?
if [ "$FIRST_EC" -ne 0 ]; then
    log "[ERROR] First session failed (exit=$FIRST_EC). Exiting."
    exit $FIRST_EC
fi

# Enter idle loop — wait for new messages, hot-restart with -c
log "[IDLE] Entering idle loop (poll=${IDLE_POLL_INTERVAL}s, timeout=${IDLE_TIMEOUT}s)..."
IDLE_START=$(date +%s)
LAST_TOUCH=$(date +%s)

while true; do
    sleep "$IDLE_POLL_INTERVAL"

    # Check idle timeout (30min)
    NOW=$(date +%s)
    IDLE_ELAPSED=$((NOW - IDLE_START))
    if [ "$IDLE_ELAPSED" -ge "$IDLE_TIMEOUT" ]; then
        log "[IDLE] Timeout reached (${IDLE_TIMEOUT}s). Ending session."
        break
    fi

    # Touch stream log every 5 minutes (prevent staleness false-positive)
    TOUCH_ELAPSED=$((NOW - LAST_TOUCH))
    if [ "$TOUCH_ELAPSED" -ge 300 ]; then
        touch "$STREAM_LOG"
        LAST_TOUCH=$NOW
    fi

    # Check for new messages
    CHECK_RESULT=0
    "$VENV_PYTHON" -m heysquid.quick_check >> "$LOG" 2>&1 || CHECK_RESULT=$?

    if [ "$CHECK_RESULT" -ne 0 ]; then
        log "[IDLE] New messages detected! Hot-starting Claude..."
        _run_claude_iteration "continue" "$CONTINUE_PROMPT"
        ITER_EC=$?
        if [ "$ITER_EC" -ne 0 ]; then
            log "[ERROR] Continue session failed (exit=$ITER_EC). Exiting loop."
            break
        fi
        IDLE_START=$(date +%s)
        LAST_TOUCH=$(date +%s)
        log "[IDLE] Back to idle loop..."
    fi
done

log "[IDLE] Session loop ended."
# cleanup runs automatically via trap EXIT
exit 0
