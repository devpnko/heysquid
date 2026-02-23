#!/bin/bash
# heysquid executor — Mac 포팅 (mybot_autoexecutor.bat → executor.sh)
#
# 핵심 로직:
# 1. Claude CLI 설치 확인
# 2. 프로세스 충돌 감지 (3중 안전장치)
# 3. quick_check.py로 메시지 유무 확인
# 4. 세션 재개 시도 (claude -p -c) → 실패 시 새 세션
# 5. 락 파일 정리

set -euo pipefail

# Claude Code 중첩 세션 방지 해제 (executor는 독립 세션이므로)
unset CLAUDECODE 2>/dev/null || true

# 경로 설정
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

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/data"

# 로그 함수
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

# ========================================
# PM 프로세스 kill 함수
# ========================================
# claude CLI는 시작 후 cmdline을 "claude"로 재작성하므로 pgrep으로 못 찾음.
# 해결: caffeinate(시스템 바이너리, cmdline 불변) → 부모 PID = 실제 claude.
# PID 파일 불필요, 어떤 환경에서든 동작.

kill_all_pm() {
    # 1차: caffeinate → 부모(claude) 찾아서 kill
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
    # 2차: pgrep 패턴 (append-system-prompt-file)
    pkill -f "append-system-prompt-file" 2>/dev/null || true
    # 3차: PID 파일 fallback
    if [ -f "$PIDFILE" ]; then
        while IFS= read -r OLD_PID; do
            [ -n "$OLD_PID" ] && kill "$OLD_PID" 2>/dev/null && log "[KILL] PID=$OLD_PID (from pidfile)"
        done < "$PIDFILE"
        rm -f "$PIDFILE"
    fi
    sleep 2
    # force kill: 같은 순서로 -9
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
}

is_pm_alive() {
    pgrep -f "caffeinate.*append-system-prompt-file" > /dev/null 2>&1
}

# ========================================
# trap 핸들러
# ========================================
cleanup() {
    local exit_code=${?:-0}
    log "[CLEANUP] executor.sh exiting (code=$exit_code)"
    # stream_viewer 정리 (독립 프로세스)
    [ -n "${VIEWER_PID:-}" ] && kill "$VIEWER_PID" 2>/dev/null || true
    kill_all_pm
    rm -f "$LOCKFILE" "$EXECUTOR_PIDFILE" 2>/dev/null
    log "[CLEANUP] Done."
}
trap cleanup EXIT INT TERM

# ========================================
# Claude CLI 자동 탐지
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

# executor.sh 자신의 PID 기록 (trigger_executor의 dedup 체크에 사용)
echo $$ > "$EXECUTOR_PIDFILE"
log "[INFO] executor.pid=$$"

# ========================================
# 프로세스 중복 실행 방지
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

# 2. Lock 파일 확인 (listener가 pre-lock을 생성하므로 여기서 삭제하지 않음)
#    executor.sh가 step 4에서 lock을 덮어씀. no-message exit 시 정리함.
if [ -f "$LOCKFILE" ]; then
    log "[INFO] Lock file exists (pre-lock by listener or previous crash). Proceeding..."
fi

# 3. 빠른 메시지 확인 (Python으로 먼저 확인)
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

# 4. Lock 파일 생성
echo "$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCKFILE"
log "Lock file created: $LOCKFILE"

# (착수 알림은 listener가 이미 전송하므로 여기서는 생략)

# CLAUDE.md 존재 확인
if [ ! -f "$SPF" ]; then
    log "[ERROR] CLAUDE.md not found: $SPF"
    rm -f "$LOCKFILE" 2>/dev/null
    exit 2
fi

# Claude 버전 기록
"$CLAUDE_EXE" --version >> "$LOG" 2>&1 || true

export DISABLE_AUTOUPDATER=1

# Claude 실행 프롬프트 — PM 모드
PROMPT="CLAUDE.md의 지침에 따라 PM으로서 행동할 것.
1) data/identity.json을 읽어 나의 정체성(display_name이 내 이름)과 사용자를 확인.
2) data/permanent_memory.md를 읽어 영구 기억(사용자 선호, 핵심 결정, 교훈)을 파악.
3) data/session_memory.md를 읽어 최근 대화 맥락, 활성 작업을 파악.
4) check_crash_recovery()로 이전 세션 비정상 종료 확인.
   - 반환값 있으면: 이전 작업이 중단된 것. 사용자에게 알리고 이어서 처리.
     복구 정보에 원본 메시지와 작업 내용이 있으므로 사용자에게 다시 묻지 말 것.
   - None이면: 정상 시작.
4.5) check_interrupted()로 사용자 의도적 중단 확인.
   - 반환값 있으면: 사용자가 이전 작업을 중단한 것. 이전 작업 맥락을 기억하되,
     자동으로 이어서 하지 말 것. 반드시 새 메시지를 먼저 확인하고, 새 메시지의 의도에 따라:
     · '이어서 해' / '계속' → 이전 작업 재개
     · '그거 말고 ~해줘' → 새 작업 시작
     · '그거 하되 ~바꿔' → 이전 맥락 수정 반영
   - None이면: 중단 없음.
5) heysquid/telegram_bot.py의 check_telegram()으로 새 메시지 확인.
6) 메시지 내용에 따라 PM으로서 판단하고 적절히 응답.
   - 대화(인사/질문/잡담) → reply_telegram()으로 자연스럽게 답변.
   - 작업 요청 → 계획을 설명하고 확인 요청.
   - 확인/승인 → 실행 모드로 전환하여 작업 수행.
7) 작업/응답 완료 후 바로 종료하지 말고, CLAUDE.md의 '대기 모드' 지침에 따라 영구 대기 루프를 실행할 것.
   - sleep 30 → poll_new_messages() → 새 메시지 있으면 처리
   - 타임아웃 없음. 세션은 영구 유지. 절대 스스로 종료하지 말 것.
   - 30분마다 session_memory.md 자동 갱신 (중간 저장).
8) 세션 중 중요한 결정/교훈/선호가 생기면 data/permanent_memory.md에 기록할 것.
   - 영구 보관할 가치가 있는 것만 (사용자 선호, 핵심 결정, 반복될 교훈)
   - 200줄 이내 유지.
모든 텔레그램 응답은 heysquid/telegram_sender.py의 send_message_sync()를 사용.
대화용 간편 응답은 heysquid/telegram_bot.py의 reply_telegram()을 사용."

# 작업 디렉토리를 프로젝트 루트로 설정
cd "$ROOT"

# stream log 조건부 초기화 (30분+ stale일 때만 리셋, 아니면 유지)
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

# 항상 새 세션 시작 (세션 재개 안 함 — 메모리 시스템으로 맥락 복구)
log "[INFO] Starting new session (permanent memory + session memory)..."

# Claude → tee → 로그 파일 (stream_viewer는 분리 — 죽어도 claude에 영향 없음)
caffeinate -ims "$CLAUDE_EXE" -p --dangerously-skip-permissions \
    --model opus \
    --output-format stream-json --verbose \
    --append-system-prompt-file "$SPF" \
    "$PROMPT" \
    2>> "$LOG" | tee -a "$STREAM_LOG" > /dev/null &
PIPE_PID=$!

# stream_viewer: 독립 프로세스 (크래시 시 자동 재시작, claude 파이프와 무관)
_run_stream_viewer() {
    sleep 1  # tee가 파일 쓰기 시작할 때까지 대기
    while kill -0 "$PIPE_PID" 2>/dev/null; do
        tail -n 0 -F "$STREAM_LOG" 2>/dev/null | python3 -u "$VIEWER" 2>> "$LOG" || true
        # viewer가 죽으면 재시작 (tail도 SIGPIPE로 자연 종료)
        kill -0 "$PIPE_PID" 2>/dev/null || break
        log "[WARN] stream_viewer exited, restarting in 2s..."
        sleep 2
    done
}
_run_stream_viewer &
VIEWER_PID=$!

# caffeinate PID + 실제 claude PID 기록
# 프로세스 구조: claude(parent) → caffeinate(child)
# claude CLI는 cmdline을 "claude"로 재작성하므로 PID 파일이 유일한 추적 수단
sleep 2
CAFE_PID=$(pgrep -f "caffeinate.*append-system-prompt-file" 2>/dev/null | head -1 || true)
CLAUDE_PID=""
if [ -n "$CAFE_PID" ]; then
    # claude는 caffeinate의 부모 (PPID)
    CLAUDE_PID=$(ps -p "$CAFE_PID" -o ppid= 2>/dev/null | tr -d ' ')
fi
# fallback: caffeinate 자체라도 저장
if [ -z "$CLAUDE_PID" ]; then
    CLAUDE_PID=$(pgrep -f "append-system-prompt-file" 2>/dev/null | head -1 || true)
fi
# 둘 다 PID 파일에 저장 (한 줄에 하나씩, 중복 제거)
: > "$PIDFILE"
[ -n "$CLAUDE_PID" ] && echo "$CLAUDE_PID" >> "$PIDFILE"
[ -n "$CAFE_PID" ] && [ "$CAFE_PID" != "$CLAUDE_PID" ] && echo "$CAFE_PID" >> "$PIDFILE"
log "[INFO] Saved PIDs: claude=$CLAUDE_PID cafe=$CAFE_PID"

# 파이프라인 완료 대기
EC=0
wait $PIPE_PID || EC=$?

log "EXITCODE=$EC"
log ""

# cleanup은 trap EXIT에서 자동 실행됨
exit $EC
