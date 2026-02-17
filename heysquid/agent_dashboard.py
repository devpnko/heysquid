"""
agent_dashboard.py -- heysquid agent dashboard status manager

Manages agent state in data/agent_status.json.
The gameboard HTML reads this file every 3 seconds for live updates.
"""

import json
import os
import subprocess
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
STATUS_FILE = os.path.join(DATA_DIR, 'agent_status.json')
GAMEBOARD_HTML = os.path.join(DATA_DIR, 'gameboard_ocean_pixel.html')

VALID_AGENTS = ['pm', 'researcher', 'developer', 'reviewer', 'tester']
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
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_status():
    """Default idle state for all agents"""
    return {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "current_task": "",
        "pm": {"status": "idle", "task": "", "hp": 100},
        "researcher": {"status": "idle", "task": "", "hp": 100},
        "developer": {"status": "idle", "task": "", "hp": 100},
        "reviewer": {"status": "idle", "task": "", "hp": 100},
        "tester": {"status": "idle", "task": "", "hp": 100},
        "mission_log": [
            {"time": datetime.now().strftime('%H:%M:%S'), "agent": "system", "message": "시스템 대기중..."}
        ]
    }


def update_agent_status(agent: str, status: str, task: str = '', hp: int = None):
    """Update a single agent's status.

    Args:
        agent: 'pm', 'researcher', 'developer', 'reviewer', 'tester'
        status: 'idle', 'working', 'complete', 'error'
        task: description of what the agent is doing
        hp: 0-100, auto-set based on status if omitted
    """
    if agent not in VALID_AGENTS:
        return
    if status not in VALID_STATUSES:
        return

    data = _load_status()
    data[agent]['status'] = status
    data[agent]['task'] = task

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
            ['/Users/hyuk/ohmyclawbot/venv/bin/python3', script_path],
            capture_output=True, text=True, timeout=30
        )
        if 'OK' in result.stdout:
            return output_path
        else:
            print(f'[DASHBOARD] Screenshot error: {result.stderr[:200]}')
    except Exception as e:
        print(f'[DASHBOARD] Screenshot exception: {e}')
    return None


def send_dashboard_photo(chat_id):
    """Take a screenshot and send it via Telegram."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
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
