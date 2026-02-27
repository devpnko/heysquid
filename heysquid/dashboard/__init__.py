"""
agent_dashboard.py -- heysquid agent dashboard status manager

Manages agent state in data/agent_status.json.
The gameboard HTML reads this file every 3 seconds for live updates.
"""

import fcntl
import json
import os
import sys
import subprocess
import tempfile
from datetime import datetime

from ..core.config import DATA_DIR_STR as DATA_DIR, get_template_path
from ..core.agents import VALID_AGENTS, AGENTS, AGENT_NAMES
from ._store import store, SectionConfig, migrate_section_from_status

STATUS_FILE = os.path.join(DATA_DIR, 'agent_status.json')
_STATUS_LOCK = STATUS_FILE + '.lock'
CONFIG_FILE = os.path.join(DATA_DIR, 'dashboard_config.json')
SQUAD_HISTORY_FILE = os.path.join(DATA_DIR, 'squad_history.json')
GAMEBOARD_HTML = get_template_path('dashboard.html')

VALID_STATUSES = ['idle', 'working', 'complete', 'error', 'chatting', 'thinking']


def _load_dashboard_config():
    """dashboard_config.json 로드. 없으면 빈 dict."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _build_registry(config=None):
    """AGENTS에서 _registry 생성 + config 오버라이드 머지."""
    if config is None:
        config = _load_dashboard_config()
    registry = {
        name: {
            "emoji": info["emoji"], "animal": info["animal"],
            "color": info["color"], "color_hex": info["color_hex"],
            "label": info["label"], "css_class": info["css_class"],
        }
        for name, info in AGENTS.items()
    }
    agent_overrides = config.get('agents', {})
    for name, overrides in agent_overrides.items():
        if name in registry:
            if 'label' in overrides:
                registry[name]['label'] = overrides['label']
            if 'color_hex' in overrides:
                registry[name]['color_hex'] = overrides['color_hex']
    return registry


def _build_config_section(config=None):
    """agent_status.json에 포함할 _config 섹션 생성."""
    if config is None:
        config = _load_dashboard_config()
    return {
        'title': config.get('title', 'heysquid HQ'),
        'subtitle': config.get('subtitle', 'DEEP SEA AGENT COMMAND CENTER'),
        'pm_label': config.get('pm_label', 'PM — heysquid'),
        'theme': config.get('theme', 'deep-blue'),
        'display': config.get('display', {}),
    }


def _load_status(*, _raise_on_error=False):
    """Load current status JSON (core fields only — PM/agent state + mission_log).

    분리된 섹션(kanban, automations, workspaces, squad_log)은 여기서 관리하지 않는다.
    각각 store.load()/store.modify()를 통해 별도 파일로 관리된다.

    Args:
        _raise_on_error: True면 파일 읽기/파싱 실패 시 예외를 올린다.
    """
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 분리 완료된 섹션은 agent_status.json에서 제거 (stale 방지)
        for key in _SPLIT_KEYS:
            data.pop(key, None)
        return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        if _raise_on_error:
            raise
        return _default_status()


_SPLIT_KEYS = {"kanban", "automations", "workspaces", "squad_log", "skills"}


def _save_status(data):
    """Save status JSON with atomic write (tempfile + fsync + rename).

    분리된 섹션 키는 저장 직전에 제거한다 — agent_status.json에는
    PM/agent 상태 + mission_log + _registry + _config만 남긴다.
    """
    for key in _SPLIT_KEYS:
        data.pop(key, None)
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    config = _load_dashboard_config()
    data['_registry'] = _build_registry(config)
    data['_config'] = _build_config_section(config)
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix='.json.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, STATUS_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _default_status():
    """Default idle state for all agents (core fields only — no split sections)."""
    config = _load_dashboard_config()
    status = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "current_task": "",
        "mission_log": [
            {"time": datetime.now().strftime('%H:%M:%S'), "agent": "system", "message": "시스템 대기중..."}
        ],
    }
    for name, info in AGENTS.items():
        agent_data = {"status": "idle", "task": "", "hp": 100}
        if name == "pm":
            agent_data["speech"] = ""
        else:
            agent_data["assignment"] = None
        status[name] = agent_data
    status["_registry"] = _build_registry(config)
    status["_config"] = _build_config_section(config)
    return status


# --- Section registrations: automations, workspaces ---
store.register(SectionConfig("automations", "automations.json", lambda: {}))
store.register(SectionConfig("workspaces", "workspaces.json", lambda: {}))
store.register(SectionConfig("squad_log", "squad_log.json", lambda: {}))

# One-time migrations from agent_status.json
_auto_cfg = store.get_config("automations")
migrate_section_from_status("automations", _auto_cfg.file_path,
                            _auto_cfg.lock_path, _auto_cfg.bak_path)
if not os.path.exists(_auto_cfg.file_path):
    # Fallback: try old "skills" key
    migrate_section_from_status("skills", _auto_cfg.file_path,
                                _auto_cfg.lock_path, _auto_cfg.bak_path)

_ws_cfg = store.get_config("workspaces")
migrate_section_from_status("workspaces", _ws_cfg.file_path,
                            _ws_cfg.lock_path, _ws_cfg.bak_path)

_sq_cfg = store.get_config("squad_log")
migrate_section_from_status("squad_log", _sq_cfg.file_path,
                            _sq_cfg.lock_path, _sq_cfg.bak_path)


def load_and_modify_status(modifier_fn):
    """agent_status.json을 잠금 하에 읽기-수정-쓰기 (fcntl.flock)

    modifier_fn(data) → data (수정된 dict) 또는 False (저장 생략)

    Safety: 파일이 존재하는데 읽기/파싱 실패 시 → 빈 default로 덮어쓰지 않고
    재시도 1회 후에도 실패하면 저장을 건너뛴다.
    """
    import time as _time
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_STATUS_LOCK, 'w') as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            # 파일이 있으면 _raise_on_error=True로 읽기 시도
            if os.path.exists(STATUS_FILE):
                try:
                    data = _load_status(_raise_on_error=True)
                except (json.JSONDecodeError, FileNotFoundError):
                    # rename 도중 일시적 부재 또는 깨진 JSON → 50ms 후 재시도
                    _time.sleep(0.05)
                    try:
                        data = _load_status(_raise_on_error=True)
                    except (json.JSONDecodeError, FileNotFoundError):
                        # 재시도도 실패 → 기존 데이터 보호를 위해 저장 건너뜀
                        print(f"[WARN] agent_status.json 읽기 실패 — 저장 건너뜀 (데이터 보호)")
                        return _default_status()
            else:
                # 파일 자체가 없으면 새로 생성 (정상)
                data = _default_status()

            result = modifier_fn(data)
            if result is False:
                return data
            if result is None:
                result = data
            _save_status(result)
            return result
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _apply_agent_status(data, agent, status, task='', hp=None, assignment=None):
    """Internal: apply agent status change to data dict (no I/O)."""
    if agent not in data:
        data[agent] = {"status": "idle", "task": "", "hp": 100}
    data[agent]['status'] = status
    data[agent]['task'] = task

    if assignment is not None:
        data[agent]['assignment'] = assignment
    elif status == 'idle':
        data[agent]['assignment'] = None

    if hp is not None:
        data[agent]['hp'] = max(0, min(100, hp))
    else:
        hp_map = {'idle': 100, 'working': 60, 'complete': 100,
                  'error': 30, 'thinking': 80, 'chatting': 70}
        data[agent]['hp'] = hp_map.get(status, 100)


def _apply_mission_log(data, agent, message):
    """Internal: append mission log entry to data dict (no I/O)."""
    entry = {
        "time": datetime.now().strftime('%H:%M:%S'),
        "agent": agent,
        "message": message,
    }
    data['mission_log'].append(entry)
    if len(data['mission_log']) > 50:
        data['mission_log'] = data['mission_log'][-50:]


def update_agent_status(agent: str, status: str, task: str = '', hp: int = None, assignment: str = None):
    """Update a single agent's status.

    Args:
        agent: 'pm', 'researcher', 'developer', 'reviewer', 'tester', 'writer'
        status: 'idle', 'working', 'complete', 'error'
        task: description of what the agent is doing
        hp: 0-100, auto-set based on status if omitted
        assignment: desk name (e.g. 'thread', 'briefing') or None for pool
    """
    if agent not in VALID_AGENTS:
        return
    if status not in VALID_STATUSES:
        return

    def _modify(data):
        _apply_agent_status(data, agent, status, task, hp, assignment)

    load_and_modify_status(_modify)


def set_current_task(task_name: str):
    """Set the current quest/task name shown on the dashboard."""
    def _modify(data):
        data['current_task'] = task_name
    load_and_modify_status(_modify)


def add_mission_log(agent: str, message: str):
    """Add an entry to the mission log (max 50 entries).
    Filters out Bash command spam (python3 -c, wc -l, etc.)."""
    import re
    if re.search(r'python3\s+-[cu]', message):
        return
    if message.startswith('💻 python3'):
        return
    if re.search(r'💻\s*(wc|cat|head|tail|ls)\s', message):
        return

    def _modify(data):
        _apply_mission_log(data, agent, message)

    load_and_modify_status(_modify)


def add_mission_log_and_speech(agent: str, message: str):
    """Batched: mission log + PM speech in single flock (for _dashboard_log).

    Reduces 2 flock operations to 1 when called from _dashboard_log.
    """
    import re
    if re.search(r'python3\s+-[cu]', message):
        return
    if message.startswith('💻 python3'):
        return
    if re.search(r'💻\s*(wc|cat|head|tail|ls)\s', message):
        return

    def _modify(data):
        _apply_mission_log(data, agent, message)
        if agent == 'pm':
            if 'pm' not in data:
                data['pm'] = {"status": "idle", "task": "", "hp": 100}
            data['pm']['speech'] = message

    load_and_modify_status(_modify)


def reset_all():
    """Reset all agents to idle state."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_STATUS_LOCK, 'w') as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = _default_status()
            now = datetime.now().strftime('%H:%M:%S')
            data['mission_log'] = [{"time": now, "agent": "system", "message": "시스템 초기화 완료."}]
            _save_status(data)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def set_pm_speech(text: str):
    """Set PM speech bubble text (shown for ~5s on dashboard)."""
    def _modify(data):
        if 'pm' not in data:
            data['pm'] = {"status": "idle", "task": "", "hp": 100}
        data['pm']['speech'] = text
    load_and_modify_status(_modify)


def dispatch_agent(agent: str, desk: str, task: str, hp: int = None):
    """Dispatch agent to a desk with a task.

    Agent status + mission log → agent_status.json (1 flock).
    Kanban activity → kanban.json (separate flock via log_agent_activity).
    """
    if agent not in VALID_AGENTS:
        return

    def _modify(data):
        _apply_agent_status(data, agent, 'working', task, hp, assignment=desk)
        _apply_mission_log(data, agent, task)

    load_and_modify_status(_modify)
    try:
        log_agent_activity(agent, task)
    except Exception:
        pass


def recall_agent(agent: str, message: str = 'Task complete'):
    """Return agent to idle pool.

    Agent status + mission log → agent_status.json (1 flock).
    Kanban activity → kanban.json (separate flock via log_agent_activity).
    """
    if agent not in VALID_AGENTS:
        return

    def _modify(data):
        _apply_agent_status(data, agent, 'idle', '', 100, assignment=None)
        _apply_mission_log(data, agent, message)

    load_and_modify_status(_modify)
    try:
        log_agent_activity(agent, message)
    except Exception:
        pass


def take_dashboard_screenshot(output_path: str = None) -> str:
    """Take a screenshot of the live dashboard.

    Strategy:
      1. Try HTTP (localhost:8420) — dashboard server serves live data, most accurate
      2. Fallback to file:// with manual data injection if server not running

    Returns:
        File path on success, None on failure.
    """
    if output_path is None:
        output_path = os.path.join(DATA_DIR, 'dashboard_screenshot.png')

    script_path = os.path.join(DATA_DIR, '_dashboard_shot.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(f'''import asyncio, json, urllib.request
from playwright.async_api import async_playwright

LIVE_URL = "http://127.0.0.1:8420/dashboard.html"
FILE_URL = "file://{GAMEBOARD_HTML}"
STATUS_FILE = "{STATUS_FILE}"
OUTPUT = "{output_path}"

def server_is_up():
    try:
        urllib.request.urlopen(LIVE_URL, timeout=2)
        return True
    except Exception:
        return False

async def shot():
    use_http = server_is_up()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={{"width": 1200, "height": 900}})

        if use_http:
            # Live dashboard — data loads automatically via polling
            await page.goto(LIVE_URL, wait_until="networkidle")
            await page.wait_for_timeout(3500)  # poll interval (3s) + render
        else:
            # Fallback — file:// with manual injection
            await page.goto(FILE_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)

            with open(STATUS_FILE, "r", encoding="utf-8") as sf:
                data = json.load(sf)
            # Merge split files for complete data
            for fname, key in [("kanban.json", "kanban"), ("automations.json", "automations"), ("workspaces.json", "workspaces")]:
                try:
                    with open(STATUS_FILE.replace("agent_status.json", fname), "r") as _sf:
                        data[key] = json.load(_sf)
                except Exception:
                    pass

            # Inject data: workspace zones FIRST, then full load for agents
            await page.evaluate("""data => {{
                if (typeof renderWorkspaceZones === 'function' && data.workspaces) {{
                    renderWorkspaceZones(data.workspaces);
                }}
                if (typeof renderSkillsPanel === 'function' && data.automations) {{
                    renderSkillsPanel(data.automations);
                }}
            }}""", data)
            await page.wait_for_timeout(500)  # let DOM settle

            # Now load full data (agents can find their desks)
            await page.evaluate(
                "data => {{ if (typeof loadDashboardData === 'function') loadDashboardData(data); }}",
                data
            )
            await page.wait_for_timeout(3000)  # wait for walk animations

        await page.screenshot(path=OUTPUT, full_page=False)
        await browser.close()

asyncio.run(shot())
print("OK")
''')

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True, timeout=30
        )
        if 'OK' in result.stdout:
            return output_path
        else:
            print(f'[DASHBOARD] Screenshot error: {result.stderr[:200]}')
    except Exception as e:
        print(f'[DASHBOARD] Screenshot exception: {e}')
    return None


def init_squad(topic, participants, mode="squid", virtual_experts=None):
    """squad_log 초기화. mode: 'squid' or 'kraken'."""
    squad_log = {
        "topic": topic,
        "mode": mode,
        "participants": participants,
        "virtual_experts": virtual_experts or [],
        "status": "active",
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entries": [],
    }

    store.modify("squad_log", lambda data: squad_log)
    return squad_log


def add_squad_entry(agent, entry_type, message):
    """squad_log.entries에 토론 엔트리 추가.

    Args:
        agent: 기존 에이전트명 or 'kraken:name' 형태
        entry_type: opinion | agree | disagree | risk | proposal | conclusion
        message: 발언 내용
    """
    result_entry = [None]

    def _modify(data):
        if not data or data.get('status') != 'active':
            return False  # skip save
        entry = {
            "time": datetime.now().strftime("%H:%M"),
            "agent": agent,
            "type": entry_type,
            "message": message,
        }
        data.setdefault('entries', []).append(entry)
        result_entry[0] = entry

    store.modify("squad_log", _modify)
    return result_entry[0]


def conclude_squad(conclusion):
    """squad_log.status = 'concluded', 결론 메시지 추가."""
    def _modify(data):
        if not data:
            return False  # skip save
        data['status'] = 'concluded'
        data.setdefault('entries', []).append({
            "time": datetime.now().strftime("%H:%M"),
            "agent": "pm",
            "type": "conclusion",
            "message": conclusion,
        })

    store.modify("squad_log", _modify)


def get_squad_log():
    """현재 squad_log dict 반환. 없으면 None."""
    data = store.load("squad_log")
    return data if data else None


def _load_history():
    """squad_history.json 로드"""
    try:
        with open(SQUAD_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_history(history):
    """squad_history.json 저장"""
    with open(SQUAD_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def archive_squad():
    """현재 squad_log를 squad_history.json에 아카이브."""
    squad = store.load("squad_log")
    if not squad:
        return None
    history = _load_history()
    squad['id'] = str(len(history) + 1)
    squad['archived_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history.append(squad)
    _save_history(history)
    return squad


def get_squad_history():
    """히스토리 목록 반환 (최신순)."""
    history = _load_history()
    return list(reversed(history))


def clear_squad():
    """squad_log 아카이브 후 제거."""
    archive_squad()
    store.modify("squad_log", lambda data: {})


def update_workspace(name, status=None, description=None):
    """Update workspace status in workspaces.json for dashboard visualization."""
    def _modify(data):
        if name not in data:
            data[name] = {
                'status': 'standby',
                'last_active': '', 'description': '',
            }
        ws = data[name]
        if status is not None:
            ws['status'] = status
        if description is not None:
            ws['description'] = description
        else:
            config = _load_dashboard_config()
            ws_override = config.get('workspaces', {}).get(name, {})
            if 'description' in ws_override and not ws.get('description'):
                ws['description'] = ws_override['description']
        ws['last_active'] = datetime.now().strftime('%Y-%m-%d')

    store.modify("workspaces", _modify)


def sync_workspaces():
    """Sync workspace data from workspaces/ directory to workspaces.json."""
    from ..core.config import WORKSPACES_DIR
    ws_dir = str(WORKSPACES_DIR)

    def _modify(data):
        if os.path.isdir(ws_dir):
            for name in os.listdir(ws_dir):
                ws_path = os.path.join(ws_dir, name)
                if os.path.isdir(ws_path) and name not in data:
                    data[name] = {
                        'status': 'standby',
                        'last_active': '', 'description': name,
                    }

    store.modify("workspaces", _modify)


def _compute_next_run(meta):
    """schedule 스킬의 다음 실행 시각 계산 (HH:MM → 내일 ISO 8601)."""
    schedule = meta.get("schedule", "")
    if not schedule:
        return None
    try:
        now = datetime.now()
        hour, minute = map(int, schedule.split(":"))
        from datetime import timedelta
        next_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_dt <= now:
            next_dt += timedelta(days=1)
        return next_dt.strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, AttributeError):
        return None


def sync_automations():
    """discover_automations() → automations.json 동기화.

    - 새 automation: 메타 + 초기 런타임 상태로 추가
    - 기존 automation: 메타 업데이트 + 런타임 상태(status, last_run 등) 보존
    - 삭제된 automation: automations 섹션에서 제거
    """
    from ..automations import discover_automations
    registry = discover_automations()

    def _modify(data):
        # 삭제된 automation 제거
        removed = [k for k in data if k not in registry]
        for k in removed:
            del data[k]

        # 추가/업데이트
        for name, meta in registry.items():
            runtime = data.get(name, {})
            data[name] = {
                "name": name,
                "description": meta.get("description", ""),
                "trigger": meta.get("trigger", "manual"),
                "schedule": meta.get("schedule", ""),
                "enabled": meta.get("enabled", True),
                "workspace": meta.get("workspace", ""),
                # 런타임 상태 보존
                "status": runtime.get("status", "idle"),
                "last_run": runtime.get("last_run", ""),
                "last_result": runtime.get("last_result", None),
                "last_error": runtime.get("last_error", None),
                "next_run": _compute_next_run(meta) if meta.get("trigger") == "schedule" else None,
                "run_count": runtime.get("run_count", 0),
            }

    store.modify("automations", _modify)


# backward compat alias
sync_skills = sync_automations


def update_skill_status(skill_name, status, last_result=None, last_error=None):
    """automation/skill 런타임 상태 업데이트 (running/idle/error)."""
    def _modify(data):
        entry = data.get(skill_name)
        if not entry:
            return False  # skip save

        entry['status'] = status
        if status in ('idle', 'error'):
            entry['last_run'] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            entry['run_count'] = entry.get('run_count', 0) + 1
        if last_result is not None:
            entry['last_result'] = last_result
        if last_error is not None:
            entry['last_error'] = last_error
        if entry.get('trigger') == 'schedule':
            entry['next_run'] = _compute_next_run(entry)

    store.modify("automations", _modify)


from .kanban import (                                    # noqa: F401
    add_kanban_task,
    update_kanban_by_message_ids,
    add_kanban_activity,
    delete_kanban_task,
    move_kanban_task,
    get_active_kanban_task_id,
    log_agent_activity,
    set_active_waiting,
    set_task_waiting,
    get_waiting_context,
    archive_done_tasks,
    get_archive,
    COL_AUTOMATION, COL_TODO, COL_IN_PROGRESS, COL_WAITING, COL_DONE,
)


def send_dashboard_photo(chat_id):
    """Take a screenshot and send it via Telegram."""
    from dotenv import load_dotenv
    from ..core.config import get_env_path
    load_dotenv(get_env_path())
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')

    screenshot = take_dashboard_screenshot()
    if not screenshot:
        return False

    url = f'https://api.telegram.org/bot{bot_token}/sendPhoto'
    try:
        result = subprocess.run(
            ['curl', '-s', '-X', 'POST', url,
             '-F', f'chat_id={chat_id}',
             '-F', f'photo=@{screenshot}',
             '-F', 'caption=heysquid 해저기지 현황'],
            capture_output=True, text=True, timeout=30
        )
        return '"ok":true' in result.stdout
    except Exception:
        return False
