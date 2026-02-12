#!/bin/bash
# telecode 데몬 관리 스크립트
#
# 사용법:
#   bash scripts/run.sh start     # 데몬 시작
#   bash scripts/run.sh stop      # 데몬 중지
#   bash scripts/run.sh restart   # 데몬 재시작
#   bash scripts/run.sh status    # 상태 확인
#   bash scripts/run.sh logs      # 최근 로그 보기

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"

WATCHER_PLIST="com.telecode.watcher.plist"
BRIEFING_PLIST="com.telecode.briefing.plist"

WATCHER_SRC="$SCRIPT_DIR/$WATCHER_PLIST"
BRIEFING_SRC="$SCRIPT_DIR/$BRIEFING_PLIST"

WATCHER_DST="$LAUNCH_AGENTS/$WATCHER_PLIST"
BRIEFING_DST="$LAUNCH_AGENTS/$BRIEFING_PLIST"

case "${1:-}" in
    start)
        echo "telecode 데몬 시작..."

        # tmux 세션 생성 (executor 출력용)
        if ! tmux has-session -t telecode 2>/dev/null; then
            tmux new-session -d -s telecode -x 200 -y 50
            echo "[OK] tmux 세션 'telecode' 생성"
        else
            echo "[OK] tmux 세션 'telecode' 이미 존재"
        fi

        # LaunchAgents 디렉토리 확인
        mkdir -p "$LAUNCH_AGENTS"

        # 심볼릭 링크 생성 (이미 있으면 덮어쓰기)
        ln -sf "$WATCHER_SRC" "$WATCHER_DST"
        ln -sf "$BRIEFING_SRC" "$BRIEFING_DST"

        # launchd에 등록
        launchctl load "$WATCHER_DST" 2>/dev/null || true
        launchctl load "$BRIEFING_DST" 2>/dev/null || true

        echo "[OK] listener 데몬 시작 (10초 폴링 + 즉시 executor 트리거)"
        echo "[OK] briefing 스케줄 등록 (매일 09:00)"
        echo ""
        echo "실시간 모니터: tmux attach -t telecode"
        echo "상태 확인: bash scripts/run.sh status"
        ;;

    stop)
        echo "telecode 데몬 중지..."

        launchctl unload "$WATCHER_DST" 2>/dev/null || true
        launchctl unload "$BRIEFING_DST" 2>/dev/null || true

        # tmux 세션 종료
        tmux kill-session -t telecode 2>/dev/null || true

        echo "[OK] 데몬 + tmux 세션 중지 완료"
        ;;

    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;

    status)
        echo "=== telecode 데몬 상태 ==="
        echo ""

        echo "--- listener (메시지 감시 + executor 트리거) ---"
        if launchctl list 2>/dev/null | grep -q "com.telecode.watcher"; then
            echo "  상태: 실행 중"
            launchctl list | grep "com.telecode.watcher"
        else
            echo "  상태: 중지됨"
        fi

        echo ""
        echo "--- briefing (일일 브리핑) ---"
        if launchctl list 2>/dev/null | grep -q "com.telecode.briefing"; then
            echo "  상태: 등록됨"
            launchctl list | grep "com.telecode.briefing"
        else
            echo "  상태: 미등록"
        fi

        echo ""
        echo "--- tmux ---"
        if tmux has-session -t telecode 2>/dev/null; then
            echo "  telecode 세션: 활성 (tmux attach -t telecode)"
        else
            echo "  telecode 세션: 없음"
        fi

        echo ""
        echo "--- 프로세스 ---"
        if pgrep -f "telegram_listener.py" > /dev/null 2>&1; then
            echo "  listener: 실행 중"
        else
            echo "  listener: 중지됨"
        fi

        if pgrep -f "executor.sh" > /dev/null 2>&1; then
            echo "  executor.sh: 실행 중"
        else
            echo "  executor.sh: 대기"
        fi

        if pgrep -f "claude.*append-system-prompt-file" > /dev/null 2>&1; then
            echo "  Claude Code: 작업 중"
        else
            echo "  Claude Code: 대기"
        fi

        # Lock 파일 확인
        echo ""
        echo "--- 잠금 파일 ---"
        if [ -f "$ROOT/data/executor.lock" ]; then
            echo "  executor.lock: 존재 ($(cat "$ROOT/data/executor.lock"))"
        else
            echo "  executor.lock: 없음"
        fi

        if [ -f "$ROOT/data/working.json" ]; then
            echo "  working.json: 존재"
        else
            echo "  working.json: 없음"
        fi
        ;;

    logs)
        echo "=== 최근 로그 (executor) ==="
        if [ -f "$ROOT/logs/executor.log" ]; then
            tail -30 "$ROOT/logs/executor.log"
        else
            echo "(로그 없음)"
        fi

        echo ""
        echo "=== 최근 로그 (listener stdout) ==="
        if [ -f "$ROOT/logs/listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/listener.stdout.log"
        else
            echo "(로그 없음)"
        fi

        echo ""
        echo "=== 최근 로그 (listener stderr) ==="
        if [ -f "$ROOT/logs/listener.stderr.log" ]; then
            tail -10 "$ROOT/logs/listener.stderr.log"
        else
            echo "(로그 없음)"
        fi
        ;;

    *)
        echo "사용법: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start    데몬 시작 (watcher + briefing)"
        echo "  stop     데몬 중지"
        echo "  restart  데몬 재시작"
        echo "  status   상태 확인"
        echo "  logs     최근 로그 보기"
        exit 1
        ;;
esac
