#!/bin/bash
# heysquid Threads cron 전체 등록 스크립트
# WSL 재설치/PC 변경 시 이 스크립트만 실행하면 복원됨
#
# 사용법: bash scripts/setup_threads_cron.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Project: $PROJECT_DIR"
echo ""

# logs 디렉토리 생성
mkdir -p "$PROJECT_DIR/logs"

# 기존 threads 관련 cron 전부 제거
(crontab -l 2>/dev/null | grep -v "threads_cron") | crontab -

# 전체 cron 등록
(crontab -l 2>/dev/null; cat << EOF
# === heysquid threads cron (managed by setup_threads_cron.sh) ===
# 07:00 오늘 예약 보고서 (텔레그램)
0 7 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/threads_cron.py --report >> logs/threads_cron.log 2>&1
# 08:00 띠별 운세 자동 생성 + 게시 + collect
0 8 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/threads_cron.py --fortune >> logs/threads_cron.log 2>&1
# 14:00 큐 게시 + collect
0 14 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/threads_cron.py >> logs/threads_cron.log 2>&1
# 20:00 큐 게시 + collect
0 20 * * * cd $PROJECT_DIR && /usr/bin/python3 scripts/threads_cron.py >> logs/threads_cron.log 2>&1
# === end heysquid threads cron ===
EOF
) | crontab -

echo "✅ Cron 등록 완료:"
echo ""
crontab -l | grep "threads_cron"
echo ""
echo "복원 완료. 검증: crontab -l"
