#!/bin/bash
# telecode 실시간 모니터링
# 사용법: bash scripts/monitor.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STREAM_LOG="$ROOT/logs/executor.stream.jsonl"

echo "============================================"
echo "  telecode 실시간 모니터"
echo "  stream: $STREAM_LOG"
echo "  Ctrl+C로 종료"
echo "============================================"
echo ""

# stream log가 없으면 생성
touch "$STREAM_LOG"

tail -f "$STREAM_LOG" | python3 "$ROOT/scripts/stream_viewer.py"
