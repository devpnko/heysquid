#!/bin/bash
# telecode executor — Mac 포팅 (mybot_autoexecutor.bat → executor.sh)
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
TELECODE_DIR="$ROOT/telecode"
SPF="$ROOT/CLAUDE.md"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/executor.log"
STREAM_LOG="$LOG_DIR/executor.stream.jsonl"
LOCKFILE="$ROOT/data/executor.lock"

# 로그 디렉토리 생성
mkdir -p "$LOG_DIR"
mkdir -p "$ROOT/data"

# 로그 함수
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

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

# ========================================
# 프로세스 중복 실행 방지 (3중 안전장치)
# ========================================

# 1. Claude 프로세스 확인 (append-system-prompt-file는 executor 전용 플래그)
if pgrep -f "claude.*append-system-prompt-file" > /dev/null 2>&1; then
    # 프로세스 발견 - 로그 파일 갱신 시각 확인 (영구 세션이므로 4시간 기준)
    if [ -f "$LOG" ]; then
        LOG_AGE=$(( $(date +%s) - $(stat -f %m "$LOG" 2>/dev/null || echo 0) ))
        if [ "$LOG_AGE" -gt 14400 ]; then
            log "[STALE] Claude idle >4h. Force-killing..."
            pkill -f "claude.*append-system-prompt-file" 2>/dev/null || true
            rm -f "$LOCKFILE" 2>/dev/null
            log "[STALE] Cleared stale state. Proceeding..."
        else
            log "[BLOCKED] Executor Claude already running."
            exit 98
        fi
    else
        log "[BLOCKED] Executor Claude already running."
        exit 98
    fi
fi

# 2. Lock 파일 확인 (프로세스 없는데 Lock 있으면 오류 중단)
if [ -f "$LOCKFILE" ]; then
    log "[RECOVERY] Lock file exists but no process running - recovering from error."
    rm -f "$LOCKFILE" 2>/dev/null
    log "[INFO] Stale lock removed."
fi

# 3. 빠른 메시지 확인 (Python으로 먼저 확인)
log "[QUICK_CHECK] Checking for new messages..."
cd "$TELECODE_DIR"

VENV_PYTHON="$ROOT/venv/bin/python3"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

CHECK_RESULT=0
"$VENV_PYTHON" quick_check.py >> "$LOG" 2>&1 || CHECK_RESULT=$?

if [ "$CHECK_RESULT" -eq 0 ]; then
    log "[NO_MESSAGE] No new messages. Exiting."
    log ""
    exit 0
fi

log "[NEW_MESSAGE] New messages found. Starting Claude Code..."

# 4. Lock 파일 생성
echo "$(date '+%Y-%m-%d %H:%M:%S')" > "$LOCKFILE"
log "Lock file created: $LOCKFILE"

# 착수 알림 전송
cd "$TELECODE_DIR"
"$VENV_PYTHON" -c "
from telegram_sender import send_message_sync
from quick_check import get_first_unprocessed_chat_id
chat_id = get_first_unprocessed_chat_id()
if chat_id:
    send_message_sync(chat_id, '🔧 작업 착수합니다.')
" 2>/dev/null || true
cd "$ROOT"

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
1) data/identity.json을 읽어 나의 정체성(telecode)과 사용자를 확인.
2) data/permanent_memory.md를 읽어 영구 기억(사용자 선호, 핵심 결정, 교훈)을 파악.
3) data/session_memory.md를 읽어 최근 대화 맥락, 활성 작업을 파악.
4) check_crash_recovery()로 이전 세션 비정상 종료 확인.
   - 반환값 있으면: 이전 작업이 중단된 것. 사용자에게 알리고 이어서 처리.
     복구 정보에 원본 메시지와 작업 내용이 있으므로 사용자에게 다시 묻지 말 것.
   - None이면: 정상 시작.
5) telecode/telegram_bot.py의 check_telegram()으로 새 메시지 확인.
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
모든 텔레그램 응답은 telecode/telegram_sender.py의 send_message_sync()를 사용.
대화용 간편 응답은 telecode/telegram_bot.py의 reply_telegram()을 사용."

# 작업 디렉토리를 프로젝트 루트로 설정
cd "$ROOT"

# stream log 초기화 (실행마다 새로 시작)
> "$STREAM_LOG"

VIEWER="$ROOT/scripts/stream_viewer.py"

# 항상 새 세션 시작 (세션 재개 안 함 — 메모리 시스템으로 맥락 복구)
log "[INFO] Starting new session (permanent memory + session memory)..."
EC=0
caffeinate -ims "$CLAUDE_EXE" -p --dangerously-skip-permissions \
    --model opus \
    --output-format stream-json --verbose \
    --append-system-prompt-file "$SPF" \
    "$PROMPT" \
    2>> "$LOG" | tee "$STREAM_LOG" | python3 -u "$VIEWER" || EC=$?

log "EXITCODE=$EC"
log ""

# Lock 파일 삭제
if [ -f "$LOCKFILE" ]; then
    rm -f "$LOCKFILE" 2>/dev/null
    log "Lock file deleted: $LOCKFILE"
fi

exit $EC
