"""
일일 브리핑 생성기 — telecode

매일 아침 프로젝트 상태를 분석하여 텔레그램으로 전송.

분석 대상:
- 각 워크스페이스의 git log (최근 24h)
- tasks/ 디렉토리 (미처리 작업)
- workspaces/{name}/progress.md

사용법:
    python briefing.py          # 수동 실행
    (launchd로 매일 09:00 자동 실행)
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# sys.path에 telecode/ 추가
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# .env 로드
load_dotenv(os.path.join(BASE_DIR, ".env"))

CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()


def get_git_summary(repo_path):
    """
    Git 저장소의 최근 24시간 커밋 요약

    Args:
        repo_path: Git 저장소 경로

    Returns:
        str: 커밋 요약 텍스트
    """
    if not os.path.exists(os.path.join(repo_path, ".git")):
        return "(git 저장소 아님)"

    try:
        since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={since}", "--no-merges"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return "(git log 오류)"

        lines = result.stdout.strip().split("\n")
        lines = [l for l in lines if l.strip()]

        if not lines:
            return "최근 24시간 커밋 없음"

        return f"최근 24시간 커밋 {len(lines)}건:\n" + "\n".join(f"  - {l}" for l in lines[:10])

    except subprocess.TimeoutExpired:
        return "(git log 타임아웃)"
    except Exception as e:
        return f"(git 오류: {e})"


def get_pending_tasks():
    """미처리 텔레그램 메시지 수 확인"""
    messages_file = os.path.join(PROJECT_ROOT, "data", "telegram_messages.json")

    if not os.path.exists(messages_file):
        return 0

    try:
        with open(messages_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        pending = [m for m in messages if not m.get("processed", False) and m.get("type") == "user"]
        return len(pending)

    except Exception:
        return 0


def get_recent_progress(name):
    """최근 진행 기록 (마지막 3개 항목)"""
    progress_file = os.path.join(PROJECT_ROOT, "workspaces", name, "progress.md")

    if not os.path.exists(progress_file):
        return "진행 기록 없음"

    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            content = f.read()

        # ### 으로 시작하는 항목 추출
        entries = content.split("### ")
        entries = [e.strip() for e in entries if e.strip() and not e.startswith("#")]

        if not entries:
            return "진행 기록 없음"

        # 마지막 3개
        recent = entries[-3:]
        return "\n".join(f"  - {e.split(chr(10))[0]}" for e in recent)

    except Exception:
        return "진행 기록 없음"


def generate_briefing():
    """일일 브리핑 생성"""
    now = datetime.now()
    briefing_parts = []

    briefing_parts.append(f"**telecode 일일 브리핑**")
    briefing_parts.append(f"{now.strftime('%Y-%m-%d %A')}")
    briefing_parts.append("")

    # 미처리 메시지
    pending = get_pending_tasks()
    if pending > 0:
        briefing_parts.append(f"**미처리 메시지: {pending}개**")
    else:
        briefing_parts.append("미처리 메시지: 없음")
    briefing_parts.append("")

    # 워크스페이스별 상태
    workspaces_file = os.path.join(PROJECT_ROOT, "data", "workspaces.json")

    if os.path.exists(workspaces_file):
        try:
            with open(workspaces_file, "r", encoding="utf-8") as f:
                workspaces = json.load(f)
        except Exception:
            workspaces = {}
    else:
        workspaces = {}

    if workspaces:
        briefing_parts.append("**프로젝트 현황:**")
        briefing_parts.append("")

        for name, info in workspaces.items():
            ws_path = info.get("path", "")
            description = info.get("description", "")
            last_active = info.get("last_active", "N/A")

            briefing_parts.append(f"--- {name} ---")
            briefing_parts.append(f"  {description}")
            briefing_parts.append(f"  최근 활동: {last_active}")

            # Git 요약
            if os.path.exists(ws_path):
                git_summary = get_git_summary(ws_path)
                briefing_parts.append(f"  {git_summary}")

            # 진행 기록
            progress = get_recent_progress(name)
            if progress != "진행 기록 없음":
                briefing_parts.append(f"  최근 진행:")
                briefing_parts.append(f"  {progress}")

            briefing_parts.append("")

    else:
        briefing_parts.append("등록된 프로젝트 없음")
        briefing_parts.append("")

    briefing_parts.append("---")
    briefing_parts.append("_telecode 자동 브리핑_")

    return "\n".join(briefing_parts)


def send_briefing():
    """브리핑 생성 후 텔레그램으로 전송"""
    if not CHAT_ID:
        print("[ERROR] TELEGRAM_ALLOWED_USERS가 설정되지 않았습니다.")
        return False

    briefing = generate_briefing()
    print(briefing)
    print()

    try:
        from telegram_sender import send_message_sync
        success = send_message_sync(int(CHAT_ID), briefing)

        if success:
            print("[OK] 브리핑 전송 완료!")
        else:
            print("[ERROR] 브리핑 전송 실패!")

        return success

    except Exception as e:
        print(f"[ERROR] 브리핑 전송 오류: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("telecode 일일 브리핑")
    print("=" * 60)
    print()

    send_briefing()
