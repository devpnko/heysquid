#!/bin/bash
# heysquid 초기 설정 스크립트
#
# 사용법: bash scripts/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
HEYSQUID_DIR="$ROOT/heysquid"

echo "========================================"
echo "  heysquid 초기 설정"
echo "========================================"
echo ""

# 1. Python 확인
echo "[1/6] Python 확인..."
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "  $PY_VER"
else
    echo "  [ERROR] Python3이 설치되어 있지 않습니다."
    echo "  brew install python3"
    exit 1
fi

# 2. Python venv 생성
echo ""
echo "[2/6] Python 가상환경 생성..."
if [ -d "$ROOT/venv" ]; then
    echo "  이미 존재합니다: $ROOT/venv"
else
    python3 -m venv "$ROOT/venv"
    echo "  [OK] venv 생성 완료"
fi

# 3. pip install
echo ""
echo "[3/6] 의존성 설치..."
source "$ROOT/venv/bin/activate"
pip install -r "$HEYSQUID_DIR/requirements.txt" --quiet
echo "  [OK] 의존성 설치 완료"

# 4. .env 파일 설정
echo ""
echo "[4/6] .env 파일 설정..."
if [ -f "$HEYSQUID_DIR/.env" ]; then
    echo "  이미 존재합니다: $HEYSQUID_DIR/.env"
else
    cp "$HEYSQUID_DIR/.env.example" "$HEYSQUID_DIR/.env"
    echo "  .env.example을 복사했습니다."
    echo ""
    echo "  *** 설정이 필요합니다 ***"
    echo "  $HEYSQUID_DIR/.env 파일을 열어서 다음 값을 설정하세요:"
    echo ""
    echo "    TELEGRAM_BOT_TOKEN=<@BotFather에서 발급한 봇 토큰>"
    echo "    TELEGRAM_ALLOWED_USERS=<허용할 텔레그램 사용자 ID>"
    echo ""
fi

# 5. 디렉토리 생성
echo ""
echo "[5/6] 디렉토리 생성..."
mkdir -p "$ROOT/data"
mkdir -p "$ROOT/tasks"
mkdir -p "$ROOT/workspaces"
mkdir -p "$ROOT/logs"
echo "  [OK] data/, tasks/, workspaces/, logs/ 생성 완료"

# 6. launchd 심볼릭 링크
echo ""
echo "[6/6] launchd 설정..."
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"

ln -sf "$SCRIPT_DIR/com.heysquid.watcher.plist" "$LAUNCH_AGENTS/com.heysquid.watcher.plist"
ln -sf "$SCRIPT_DIR/com.heysquid.briefing.plist" "$LAUNCH_AGENTS/com.heysquid.briefing.plist"
echo "  [OK] plist 심볼릭 링크 생성 완료"

echo ""
echo "========================================"
echo "  설정 완료!"
echo "========================================"
echo ""
echo "다음 단계:"
echo "  1. $HEYSQUID_DIR/.env 파일에서 봇 토큰 설정"
echo "  2. bash scripts/run.sh start  (데몬 시작)"
echo "  3. 텔레그램에서 메시지 보내기"
echo ""
echo "수동 테스트:"
echo "  source venv/bin/activate"
echo "  python heysquid/telegram_listener.py  (메시지 수신 테스트)"
echo "  bash scripts/executor.sh              (executor 수동 실행)"
echo ""
