"""
agent_dashboard.py -- heysquid agent dashboard status manager

Manages agent state in data/agent_status.json.
The gameboard HTML reads this file every 3 seconds for live updates.
"""

import json
import os
import sys
import subprocess
from datetime import datetime

from .config import DATA_DIR_STR as DATA_DIR, get_template_path
from .agents import VALID_AGENTS, AGENTS, AGENT_NAMES

STATUS_FILE = os.path.join(DATA_DIR, 'agent_status.json')
# User's data/ copy takes priority; fall back to bundled template
_user_html = os.path.join(DATA_DIR, 'dashboard_v4.html')
GAMEBOARD_HTML = _user_html if os.path.exists(_user_html) else get_template_path('dashboard_v4.html')

VALID_STATUSES = ['idle', 'working', 'complete', 'error']


def _load_status():
    """Load current status JSON"""
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_status()


def _save_status(data):
    """Save status JSON with updated timestamp"""
    data['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Ensure _registry is always present for dashboard HTML
    if '_registry' not in data:
        data['_registry'] = {
            name: {
                "emoji": info["emoji"], "animal": info["animal"],
                "color": info["color"], "color_hex": info["color_hex"],
                "label": info["label"], "css_class": info["css_class"],
            }
            for name, info in AGENTS.items()
        }
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_status():
    """Default idle state for all agents (dynamically built from registry)"""
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
    # _registry: dashboard HTML이 읽어서 동적 렌더링에 사용
    status["_registry"] = {
        name: {
            "emoji": info["emoji"], "animal": info["animal"],
            "color": info["color"], "color_hex": info["color_hex"],
            "label": info["label"], "css_class": info["css_class"],
        }
        for name, info in AGENTS.items()
    }
    return status


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

    data = _load_status()
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
        if status == 'idle':
            data[agent]['hp'] = 100
        elif status == 'working':
            data[agent]['hp'] = 60
        elif status == 'complete':
            data[agent]['hp'] = 100
        elif status == 'error':
            data[agent]['hp'] = 30

    _save_status(data)


def set_current_task(task_name: str):
    """Set the current quest/task name shown on the dashboard."""
    data = _load_status()
    data['current_task'] = task_name
    _save_status(data)


def add_mission_log(agent: str, message: str):
    """Add an entry to the mission log (max 50 entries)."""
    data = _load_status()
    entry = {
        "time": datetime.now().strftime('%H:%M:%S'),
        "agent": agent,
        "message": message
    }
    data['mission_log'].append(entry)
    if len(data['mission_log']) > 50:
        data['mission_log'] = data['mission_log'][-50:]
    _save_status(data)


def reset_all():
    """Reset all agents to idle state."""
    data = _default_status()
    now = datetime.now().strftime('%H:%M:%S')
    data['mission_log'] = [{"time": now, "agent": "system", "message": "시스템 초기화 완료."}]
    _save_status(data)


def update_external_ai(name: str, status: str, task: str = ''):
    """Update external AI character status (shown on dashboard)."""
    data = _load_status()
    if 'external_ai' not in data:
        data['external_ai'] = {}
    data['external_ai'][name] = {'status': status, 'task': task}
    _save_status(data)


def set_pm_speech(text: str):
    """Set PM speech bubble text (shown for ~5s on dashboard)."""
    data = _load_status()
    if 'pm' not in data:
        data['pm'] = {"status": "idle", "task": "", "hp": 100}
    data['pm']['speech'] = text
    _save_status(data)


def dispatch_agent(agent: str, desk: str, task: str, hp: int = None):
    """Dispatch agent to a desk with a task."""
    update_agent_status(agent, 'working', task, hp, assignment=desk)
    add_mission_log(agent, task)


def recall_agent(agent: str, message: str = 'Task complete'):
    """Return agent to idle pool."""
    update_agent_status(agent, 'idle', '', 100, assignment=None)
    add_mission_log(agent, message)


def take_dashboard_screenshot(output_path: str = None) -> str:
    """Take a screenshot of the dashboard HTML using Playwright headless.
    Injects current agent_status.json data via page.evaluate().

    Returns:
        File path on success, None on failure.
    """
    if output_path is None:
        output_path = os.path.join(DATA_DIR, 'dashboard_screenshot.png')

    # Write a temp script that reads the JSON file directly
    script_path = os.path.join(DATA_DIR, '_dashboard_shot.py')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(f'''import asyncio, json
from playwright.async_api import async_playwright

async def shot():
    # Read status data
    with open("{STATUS_FILE}", "r", encoding="utf-8") as sf:
        data = json.load(sf)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={{"width": 1200, "height": 900}})
        await page.goto("file://{GAMEBOARD_HTML}", wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

        # Inject agent status data
        await page.evaluate(
            "data => {{ if (typeof loadDashboardData === 'function') loadDashboardData(data); }}",
            data
        )
        await page.wait_for_timeout(1000)

        await page.screenshot(path="{output_path}", full_page=False)
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


def update_workspace(name, status=None, department=None, description=None):
    """Update workspace status in agent_status.json for dashboard visualization."""
    data = _load_status()
    if 'workspaces' not in data:
        data['workspaces'] = {}
    if name not in data['workspaces']:
        data['workspaces'][name] = {
            'status': 'standby', 'department': None,
            'last_active': '', 'description': '',
        }
    ws = data['workspaces'][name]
    if status is not None:
        ws['status'] = status
    if department is not None:
        ws['department'] = department
    if description is not None:
        ws['description'] = description
    ws['last_active'] = datetime.now().strftime('%Y-%m-%d')
    _save_status(data)


def sync_workspaces():
    """Sync workspace data from workspaces/ directory to agent_status.json."""
    from .config import WORKSPACES_DIR
    data = _load_status()
    if 'workspaces' not in data:
        data['workspaces'] = {}

    ws_dir = str(WORKSPACES_DIR)
    if os.path.isdir(ws_dir):
        for name in os.listdir(ws_dir):
            ws_path = os.path.join(ws_dir, name)
            if os.path.isdir(ws_path) and name not in data['workspaces']:
                data['workspaces'][name] = {
                    'status': 'standby', 'department': None,
                    'last_active': '', 'description': name,
                }
    _save_status(data)


def send_dashboard_photo(chat_id):
    """Take a screenshot and send it via Telegram."""
    from dotenv import load_dotenv
    from .config import get_env_path
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
