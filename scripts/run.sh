#!/bin/bash
# heysquid 데몬 관리 스크립트
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

# .env 로드 (토큰 유무 판별용)
if [ -f "$ROOT/heysquid/.env" ]; then
    set -a; source "$ROOT/heysquid/.env" 2>/dev/null; set +a
fi

case "${1:-}" in
    start)
        echo "heysquid 데몬 시작..."

        # LaunchAgents 디렉토리 확인
        mkdir -p "$LAUNCH_AGENTS"

        # 레거시 briefing plist 제거
        launchctl unload "$BRIEFING_DST" 2>/dev/null || true
        rm -f "$BRIEFING_DST" 2>/dev/null

        # 심볼릭 링크 생성 (이미 있으면 덮어쓰기)
        ln -sf "$WATCHER_SRC" "$WATCHER_DST"
        ln -sf "$SCHEDULER_SRC" "$SCHEDULER_DST"

        # launchd에 등록
        launchctl load "$WATCHER_DST" 2>/dev/null || true
        launchctl load "$SCHEDULER_DST" 2>/dev/null || true

        # Slack listener (토큰 있으면만)
        if [ -n "$SLACK_BOT_TOKEN" ]; then
            ln -sf "$SLACK_SRC" "$SLACK_DST"
            launchctl load "$SLACK_DST" 2>/dev/null || true
            echo "[OK] Slack listener 시작 (Socket Mode)"
        fi

        # Discord listener (토큰 있으면만)
        if [ -n "$DISCORD_BOT_TOKEN" ]; then
            ln -sf "$DISCORD_SRC" "$DISCORD_DST"
            launchctl load "$DISCORD_DST" 2>/dev/null || true
            echo "[OK] Discord listener 시작 (Gateway)"
        fi

        # 대시보드 HTTP 서버
        if ! lsof -i :8420 > /dev/null 2>&1; then
            nohup bash "$SCRIPT_DIR/serve_dashboard.sh" > "$ROOT/logs/dashboard_server.log" 2>&1 &
            echo "[OK] 대시보드 서버 (http://localhost:8420/dashboard.html)"
        else
            echo "[OK] 대시보드 서버 이미 실행 중"
        fi

        echo "[OK] Telegram listener 시작 (10초 폴링 + 즉시 executor 트리거)"
        echo "[OK] scheduler 등록 (1분 간격 — 스킬 자동 실행)"
        echo ""
        echo "대시보드: http://localhost:8420/dashboard.html"
        echo "TUI 모니터: bash scripts/monitor.sh"
        echo "로그: tail -f logs/executor.log"
        echo "상태 확인: bash scripts/run.sh status"
        ;;

    stop)
        echo "heysquid 데몬 중지..."

        launchctl unload "$WATCHER_DST" 2>/dev/null || true
        launchctl unload "$SCHEDULER_DST" 2>/dev/null || true
        launchctl unload "$SLACK_DST" 2>/dev/null || true
        launchctl unload "$DISCORD_DST" 2>/dev/null || true
        launchctl unload "$BRIEFING_DST" 2>/dev/null || true

        # H-5: 심볼릭 링크 제거 (stale symlink 방지)
        rm -f "$WATCHER_DST" "$SCHEDULER_DST" "$SLACK_DST" "$DISCORD_DST" "$BRIEFING_DST" 2>/dev/null

        # 대시보드 서버 종료
        pkill -f "http.server 8420" 2>/dev/null || true

        # executor + Claude + caffeinate 전부 종료 (대기 루프 중일 수 있음)
        pkill -f "bash.*executor.sh" 2>/dev/null || true
        pkill -f "caffeinate.*claude" 2>/dev/null || true
        pkill -f "claude.*append-system-prompt-file" 2>/dev/null || true
        pkill -f "tee.*executor.stream" 2>/dev/null || true

        # 실제로 죽었는지 확인 (최대 5초 대기, 안 죽으면 SIGKILL)
        for i in 1 2 3 4 5; do
            if ! pgrep -f "claude.*append-system-prompt-file" > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        if pgrep -f "claude.*append-system-prompt-file" > /dev/null 2>&1; then
            echo "[WARN] Claude가 안 죽어서 강제 종료 (kill -9)..."
            pkill -9 -f "caffeinate.*claude" 2>/dev/null || true
            pkill -9 -f "claude.*append-system-prompt-file" 2>/dev/null || true
            pkill -9 -f "tee.*executor.stream" 2>/dev/null || true
            sleep 1
        fi

        # H-4: Slack/Discord listener 프로세스 종료
        pkill -f "slack_listener" 2>/dev/null || true
        pkill -f "discord_listener" 2>/dev/null || true

        # 잠금 파일 정리 (대기 루프 중 executor.lock이 남을 수 있음)
        rm -f "$ROOT/data/executor.lock" 2>/dev/null
        rm -f "$ROOT/data/working.json" 2>/dev/null

        echo "[OK] 데몬 + 잠금 파일 정리 완료"
        ;;

    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;

    status)
        echo "=== heysquid 데몬 상태 ==="
        echo ""

        echo "--- Listeners ---"
        if launchctl list 2>/dev/null | grep -q "com.heysquid.watcher"; then
            echo "  [TG] Telegram: 실행 중"
        else
            echo "  [TG] Telegram: 중지됨"
        fi
        if launchctl list 2>/dev/null | grep -q "com.heysquid.slack"; then
            echo "  [SL] Slack: 실행 중"
        elif [ -n "$SLACK_BOT_TOKEN" ]; then
            echo "  [SL] Slack: 중지됨 (토큰 설정됨)"
        else
            echo "  [SL] Slack: 미설정"
        fi
        if launchctl list 2>/dev/null | grep -q "com.heysquid.discord"; then
            echo "  [DC] Discord: 실행 중"
        elif [ -n "$DISCORD_BOT_TOKEN" ]; then
            echo "  [DC] Discord: 중지됨 (토큰 설정됨)"
        else
            echo "  [DC] Discord: 미설정"
        fi

        echo ""
        echo "--- scheduler (스킬 자동 실행) ---"
        if launchctl list 2>/dev/null | grep -q "com.heysquid.scheduler"; then
            echo "  상태: 실행 중"
            launchctl list | grep "com.heysquid.scheduler"
        else
            echo "  상태: 중지됨"
        fi

        echo ""
        echo "--- 프로세스 ---"
        if pgrep -f "telegram_listener" > /dev/null 2>&1; then
            echo "  Telegram listener: 실행 중"
        else
            echo "  Telegram listener: 중지됨"
        fi
        if pgrep -f "slack_listener" > /dev/null 2>&1; then
            echo "  Slack listener: 실행 중"
        else
            echo "  Slack listener: 중지됨"
        fi
        if pgrep -f "discord_listener" > /dev/null 2>&1; then
            echo "  Discord listener: 실행 중"
        else
            echo "  Discord listener: 중지됨"
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

        echo ""
        echo "--- 대시보드 서버 ---"
        if lsof -i :8420 > /dev/null 2>&1; then
            echo "  상태: 실행 중 (http://localhost:8420/dashboard.html)"
        else
            echo "  상태: 중지됨"
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

        echo ""
        echo "--- 등록된 스킬 ---"
        "$ROOT/venv/bin/python" -c "
from heysquid.skills._base import discover_skills
skills = discover_skills()
if not skills:
    print('  (등록된 스킬 없음)')
else:
    for name, meta in skills.items():
        trigger = meta.get('trigger', '?')
        schedule = meta.get('schedule', '')
        desc = meta.get('description', '')
        info = f'{trigger}'
        if schedule:
            info += f' @ {schedule}'
        print(f'  {name}: {desc} [{info}]')
" 2>/dev/null || echo "  (스킬 목록 조회 실패)"
        ;;

    logs)
        echo "=== 최근 로그 (executor) ==="
        if [ -f "$ROOT/logs/executor.log" ]; then
            tail -30 "$ROOT/logs/executor.log"
        else
            echo "(로그 없음)"
        fi

        echo ""
        echo "=== 최근 로그 (TG listener) ==="
        if [ -f "$ROOT/logs/listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/listener.stdout.log"
        else
            echo "(로그 없음)"
        fi

        echo ""
        echo "=== 최근 로그 (SL listener) ==="
        if [ -f "$ROOT/logs/slack_listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/slack_listener.stdout.log"
        else
            echo "(로그 없음)"
        fi

        echo ""
        echo "=== 최근 로그 (DC listener) ==="
        if [ -f "$ROOT/logs/discord_listener.stdout.log" ]; then
            tail -10 "$ROOT/logs/discord_listener.stdout.log"
        else
            echo "(로그 없음)"
        fi
        ;;

    *)
        echo "사용법: $0 {start|stop|restart|status|logs}"
        echo ""
        echo "  start    데몬 시작 (watcher + scheduler + listeners)"
        echo "  stop     데몬 중지"
        echo "  restart  데몬 재시작"
        echo "  status   상태 확인"
        echo "  logs     최근 로그 보기"
        exit 1
        ;;
esac
