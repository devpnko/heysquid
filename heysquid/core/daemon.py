"""heysquid.core.daemon — launchd 데몬 관리 (macOS).

plist 템플릿 렌더링, launchd 등록/해제, 프로세스 관리.
"""

import os
import shutil
import subprocess
import sys
import signal
import time
from pathlib import Path

from .config import (
    PROJECT_ROOT, DATA_DIR, LOGS_DIR, PACKAGE_DIR,
    PROJECT_ROOT_STR, get_env_path,
)

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

PLIST_NAMES = [
    "com.heysquid.watcher",
    "com.heysquid.scheduler",
    "com.heysquid.slack",
    "com.heysquid.discord",
]

# 토큰이 있어야만 시작하는 선택적 서비스
OPTIONAL_SERVICES = {
    "com.heysquid.slack": "SLACK_BOT_TOKEN",
    "com.heysquid.discord": "DISCORD_BOT_TOKEN",
}


def _python_path() -> str:
    """현재 venv의 python 경로 반환."""
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _template_dir() -> Path:
    """plist 템플릿 디렉토리 경로."""
    # 패키지 내 templates/launchd/
    pkg_templates = PACKAGE_DIR / "templates" / "launchd"
    if pkg_templates.is_dir():
        return pkg_templates
    # 프로젝트 루트 templates/launchd/
    root_templates = PROJECT_ROOT / "templates" / "launchd"
    if root_templates.is_dir():
        return root_templates
    raise FileNotFoundError("plist 템플릿 디렉토리를 찾을 수 없습니다.")


def render_plist(template_path: Path, output_path: Path) -> None:
    """plist 템플릿의 플레이스홀더를 실제 값으로 치환하여 저장."""
    content = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{PROJECT_ROOT}}": PROJECT_ROOT_STR,
        "{{PYTHON}}": _python_path(),
        "{{HOME}}": str(Path.home()),
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    output_path.write_text(content, encoding="utf-8")


def _load_env_tokens() -> dict:
    """환경변수(.env) 로드하여 토큰 존재 여부 확인."""
    env_path = get_env_path()
    tokens = {}
    if os.path.exists(env_path):
        from dotenv import dotenv_values
        tokens = dotenv_values(env_path)
    return tokens


def start() -> None:
    """데몬 시작: plist 렌더링 → launchd 등록."""
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tmpl_dir = _template_dir()
    env_tokens = _load_env_tokens()

    # 레거시 briefing plist 제거
    briefing_dst = LAUNCH_AGENTS / "com.heysquid.briefing.plist"
    if briefing_dst.exists():
        subprocess.run(["launchctl", "unload", str(briefing_dst)],
                       capture_output=True)
        briefing_dst.unlink(missing_ok=True)

    for name in PLIST_NAMES:
        # 선택적 서비스: 토큰 없으면 스킵
        required_token = OPTIONAL_SERVICES.get(name)
        if required_token and not env_tokens.get(required_token):
            continue

        template = tmpl_dir / f"{name}.plist.template"
        if not template.exists():
            print(f"  [WARN] 템플릿 없음: {template.name}")
            continue

        dst = LAUNCH_AGENTS / f"{name}.plist"
        render_plist(template, dst)
        subprocess.run(["launchctl", "load", str(dst)], capture_output=True)

        label = name.split(".")[-1].upper()
        print(f"  [OK] {label} 시작")

    # 대시보드 서버
    _start_dashboard_server()

    print()
    print(f"대시보드: http://localhost:8420/dashboard.html")
    print(f"로그: tail -f {LOGS_DIR / 'executor.log'}")
    print(f"상태 확인: heysquid status")


def _start_dashboard_server() -> None:
    """대시보드 HTTP 서버 시작 (이미 실행 중이면 스킵)."""
    result = subprocess.run(
        ["lsof", "-i", ":8420"],
        capture_output=True,
    )
    if result.returncode == 0:
        print("  [OK] 대시보드 서버 이미 실행 중")
        return

    serve_sh = PROJECT_ROOT / "scripts" / "serve_dashboard.sh"
    if serve_sh.exists():
        log_file = LOGS_DIR / "dashboard_server.log"
        with open(log_file, "a") as lf:
            subprocess.Popen(
                ["bash", str(serve_sh)],
                stdout=lf, stderr=lf,
                start_new_session=True,
            )
        print("  [OK] 대시보드 서버 시작")


def stop() -> None:
    """데몬 중지: launchd 해제 + 프로세스 kill."""
    # 1. launchd 해제
    for name in PLIST_NAMES + ["com.heysquid.briefing"]:
        dst = LAUNCH_AGENTS / f"{name}.plist"
        if dst.exists():
            subprocess.run(["launchctl", "unload", str(dst)], capture_output=True)
            dst.unlink(missing_ok=True)

    # 2. 대시보드 서버 종료
    subprocess.run(["pkill", "-f", "http.server 8420"], capture_output=True)

    # 3. executor + Claude 프로세스 종료
    subprocess.run(["pkill", "-f", "bash.*executor.sh"], capture_output=True)

    # caffeinate → 부모(claude) 추적 kill
    _kill_claude_processes()

    # 4. 추가 listener 프로세스
    for pattern in ["slack_listener", "discord_listener"]:
        subprocess.run(["pkill", "-f", pattern], capture_output=True)

    # 5. lock/pid 파일 정리
    for fname in ["executor.lock", "executor.pid", "working.json", "claude.pid"]:
        fpath = DATA_DIR / fname
        fpath.unlink(missing_ok=True)

    print("[OK] 데몬 + 잠금 파일 정리 완료")


def _kill_claude_processes() -> None:
    """caffeinate 래퍼를 통해 Claude 프로세스를 추적하여 종료."""
    result = subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(["pkill", "-f", "append-system-prompt-file"],
                       capture_output=True)
        return

    for cpid in result.stdout.strip().split("\n"):
        cpid = cpid.strip()
        if not cpid:
            continue
        # caffeinate의 부모 = claude
        parent_result = subprocess.run(
            ["ps", "-p", cpid, "-o", "ppid="],
            capture_output=True, text=True,
        )
        parent = parent_result.stdout.strip()
        if parent:
            subprocess.run(["kill", parent], capture_output=True)
        subprocess.run(["kill", cpid], capture_output=True)

    subprocess.run(["pkill", "-f", "append-system-prompt-file"],
                   capture_output=True)
    subprocess.run(["pkill", "-f", "tee.*executor.stream"],
                   capture_output=True)

    # 2초 대기 후 force kill
    time.sleep(2)
    result = subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        for cpid in result.stdout.strip().split("\n"):
            cpid = cpid.strip()
            if not cpid:
                continue
            parent_result = subprocess.run(
                ["ps", "-p", cpid, "-o", "ppid="],
                capture_output=True, text=True,
            )
            parent = parent_result.stdout.strip()
            if parent:
                subprocess.run(["kill", "-9", parent], capture_output=True)
            subprocess.run(["kill", "-9", cpid], capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "append-system-prompt-file"],
                       capture_output=True)


def restart() -> None:
    """데몬 재시작."""
    stop()
    time.sleep(1)
    start()


def status() -> None:
    """데몬 상태 출력."""
    print("=== heysquid 데몬 상태 ===\n")

    # Listeners
    print("--- Listeners ---")
    services = {
        "com.heysquid.watcher": ("TG", "Telegram"),
        "com.heysquid.slack": ("SL", "Slack"),
        "com.heysquid.discord": ("DC", "Discord"),
    }
    for label_name, (prefix, display) in services.items():
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True,
        )
        if label_name in result.stdout:
            print(f"  [{prefix}] {display}: 실행 중")
        else:
            print(f"  [{prefix}] {display}: 중지됨")

    # Scheduler
    print("\n--- Scheduler ---")
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if "com.heysquid.scheduler" in result.stdout:
        print("  상태: 실행 중")
    else:
        print("  상태: 중지됨")

    # 프로세스
    print("\n--- 프로세스 ---")
    processes = {
        "executor.sh": "bash.*executor.sh",
        "Claude Code": "caffeinate.*append-system-prompt-file",
    }
    for name, pattern in processes.items():
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True)
        state = "실행 중" if result.returncode == 0 else "대기"
        print(f"  {name}: {state}")

    # 대시보드
    print("\n--- 대시보드 서버 ---")
    result = subprocess.run(["lsof", "-i", ":8420"], capture_output=True)
    if result.returncode == 0:
        print("  상태: 실행 중 (http://localhost:8420/dashboard.html)")
    else:
        print("  상태: 중지됨")

    # Lock 파일
    print("\n--- 잠금 파일 ---")
    lock_file = DATA_DIR / "executor.lock"
    if lock_file.exists():
        print(f"  executor.lock: 존재 ({lock_file.read_text().strip()})")
    else:
        print("  executor.lock: 없음")

    working_file = DATA_DIR / "working.json"
    if working_file.exists():
        print("  working.json: 존재")
    else:
        print("  working.json: 없음")

    # 등록된 automations + skills
    print("\n--- 등록된 Automations ---")
    try:
        from heysquid.automations import discover_automations
        autos = discover_automations()
        if not autos:
            print("  (등록된 automation 없음)")
        else:
            for name, meta in autos.items():
                trigger = meta.get("trigger", "?")
                schedule = meta.get("schedule", "")
                desc = meta.get("description", "")
                info = f"{trigger}"
                if schedule:
                    info += f" @ {schedule}"
                print(f"  {name}: {desc} [{info}]")
    except Exception:
        print("  (automation 목록 조회 실패)")

    print("\n--- 등록된 Skills ---")
    try:
        from heysquid.skills._base import discover_skills
        skills = discover_skills()
        if not skills:
            print("  (등록된 스킬 없음)")
        else:
            for name, meta in skills.items():
                trigger = meta.get("trigger", "?")
                desc = meta.get("description", "")
                print(f"  {name}: {desc} [{trigger}]")
    except Exception:
        print("  (스킬 목록 조회 실패)")


def logs(follow: bool = False) -> None:
    """로그 출력."""
    log_file = LOGS_DIR / "executor.log"
    if not log_file.exists():
        print("(로그 없음)")
        return

    if follow:
        os.execvp("tail", ["tail", "-f", str(log_file)])
    else:
        # 최근 30줄
        with open(log_file) as f:
            lines = f.readlines()
        for line in lines[-30:]:
            print(line, end="")
