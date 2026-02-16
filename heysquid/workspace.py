"""
멀티 프로젝트 워크스페이스 관리 — heysquid

핵심 기능:
- list_workspaces() - 등록된 프로젝트 목록
- get_workspace(name) - 특정 워크스페이스 정보
- switch_workspace(name) - 작업 디렉토리 전환, context.md 반환
- register_workspace(name, path, description) - 새 프로젝트 등록
- update_progress(name, text) - 진행 상태 업데이트
"""

import os
import json
from datetime import datetime

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
WORKSPACES_DIR = os.path.join(PROJECT_ROOT, "workspaces")
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")


def _load_workspaces():
    """workspaces.json 로드"""
    if not os.path.exists(WORKSPACES_FILE):
        return {}

    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] workspaces.json 읽기 오류: {e}")
        return {}


def _save_workspaces(data):
    """workspaces.json 저장"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_workspaces():
    """
    등록된 워크스페이스 목록 반환

    Returns:
        dict: {name: {path, description, last_active}, ...}
    """
    return _load_workspaces()


def get_workspace(name):
    """
    특정 워크스페이스 정보 반환

    Args:
        name: 워크스페이스 이름

    Returns:
        dict or None: {path, description, last_active}
    """
    workspaces = _load_workspaces()
    return workspaces.get(name)


def switch_workspace(name):
    """
    작업 디렉토리 전환 + context.md 반환

    Args:
        name: 워크스페이스 이름

    Returns:
        str: context.md 내용 (없으면 빈 문자열)
    """
    workspaces = _load_workspaces()

    if name not in workspaces:
        print(f"[WARN] 워크스페이스 '{name}'을 찾을 수 없습니다.")
        return ""

    ws = workspaces[name]
    ws_path = ws["path"]

    if not os.path.exists(ws_path):
        print(f"[WARN] 워크스페이스 경로가 존재하지 않습니다: {ws_path}")
        return ""

    # last_active 갱신
    ws["last_active"] = datetime.now().strftime("%Y-%m-%d")
    _save_workspaces(workspaces)

    print(f"[WORKSPACE] 전환: {name} -> {ws_path}")

    # context.md 읽기
    context_dir = os.path.join(WORKSPACES_DIR, name)
    context_file = os.path.join(context_dir, "context.md")

    if os.path.exists(context_file):
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] context.md 읽기 오류: {e}")

    return ""


def register_workspace(name, path, description=""):
    """
    새 프로젝트 워크스페이스 등록

    Args:
        name: 워크스페이스 이름 (영문 소문자 권장)
        path: 프로젝트 절대 경로
        description: 프로젝트 설명
    """
    workspaces = _load_workspaces()

    workspaces[name] = {
        "path": path,
        "description": description,
        "last_active": datetime.now().strftime("%Y-%m-%d")
    }

    _save_workspaces(workspaces)

    # 워크스페이스 컨텍스트 디렉토리 생성
    ws_dir = os.path.join(WORKSPACES_DIR, name)
    os.makedirs(ws_dir, exist_ok=True)

    # context.md 초기화 (없으면)
    context_file = os.path.join(ws_dir, "context.md")
    if not os.path.exists(context_file):
        with open(context_file, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{description}\n\n## 주요 파일\n\n## 진행 상황\n")

    # progress.md 초기화 (없으면)
    progress_file = os.path.join(ws_dir, "progress.md")
    if not os.path.exists(progress_file):
        with open(progress_file, "w", encoding="utf-8") as f:
            f.write(f"# {name} 진행 기록\n\n")

    print(f"[WORKSPACE] 등록 완료: {name} -> {path}")


def update_progress(name, text):
    """
    프로젝트 진행 상태 업데이트

    Args:
        name: 워크스페이스 이름
        text: 진행 상태 텍스트
    """
    ws_dir = os.path.join(WORKSPACES_DIR, name)
    os.makedirs(ws_dir, exist_ok=True)

    progress_file = os.path.join(ws_dir, "progress.md")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### [{timestamp}]\n{text}\n"

    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(entry)

    # last_active 갱신
    workspaces = _load_workspaces()
    if name in workspaces:
        workspaces[name]["last_active"] = datetime.now().strftime("%Y-%m-%d")
        _save_workspaces(workspaces)

    print(f"[PROGRESS] {name}: {text[:50]}...")


def get_progress(name):
    """
    프로젝트 진행 기록 읽기

    Args:
        name: 워크스페이스 이름

    Returns:
        str: progress.md 내용
    """
    progress_file = os.path.join(WORKSPACES_DIR, name, "progress.md")

    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] progress.md 읽기 오류: {e}")

    return ""


def init_default_workspaces():
    """기본 워크스페이스 등록 (첫 실행 시)"""
    workspaces = _load_workspaces()

    if not workspaces:
        register_workspace(
            "terabot",
            "/Users/hyuk/TERABOT",
            "오픈성지 - 휴대폰 시세 플랫폼"
        )
        register_workspace(
            "heysquid",
            "/Users/hyuk/ohmyclawbot",
            "heysquid - 텔레그램 원격 제어"
        )
        print("[WORKSPACE] 기본 워크스페이스 초기화 완료")


if __name__ == "__main__":
    print("=" * 60)
    print("heysquid 워크스페이스 관리")
    print("=" * 60)

    # 기본 워크스페이스 초기화
    init_default_workspaces()

    # 목록 출력
    workspaces = list_workspaces()
    if workspaces:
        print(f"\n등록된 워크스페이스: {len(workspaces)}개\n")
        for name, info in workspaces.items():
            print(f"  [{name}]")
            print(f"    경로: {info['path']}")
            print(f"    설명: {info.get('description', '')}")
            print(f"    최근 활동: {info.get('last_active', 'N/A')}")
            print()
    else:
        print("\n등록된 워크스페이스가 없습니다.")
