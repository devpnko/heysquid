#!/bin/bash
# 매일 08:00 KST에 운세 자동 게시
# crontab에 등록

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# logs 디렉토리 생성
mkdir -p "$PROJECT_DIR/logs"

# 기존 threads_cron 항목 제거 후 추가
(crontab -l 2>/dev/null | grep -v threads_cron; echo "0 8 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/threads_cron.py --fortune >> logs/threads_cron.log 2>&1") | crontab -

echo "Cron registered: daily 08:00 threads fortune"
echo "Project dir: $PROJECT_DIR"
echo ""
echo "Verify with: crontab -l | grep threads"
