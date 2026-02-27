# Skill & Automation Writing Guide

## Automation vs Skill

| | Automation | Skill |
|--|-----------|-------|
| **Location** | `heysquid/automations/` | `heysquid/skills/` |
| **Nature** | Automatic recurring (schedule/interval) | Manually invoked capability |
| **Trigger** | `schedule`, `interval` | `manual`, `webhook` |
| **Examples** | briefing, threads_post | deep_work, marketing, saju_fortune |
| **Dashboard** | Kanban Automation column | - |

## Structure

```
heysquid/
├── core/
│   ├── plugin_loader.py  # Shared discovery + runner engine
│   └── http_utils.py     # HTTP utilities (get_secret, http_get, ...)
├── automations/           # Automatic recurring (schedule/interval)
│   ├── __init__.py
│   ├── briefing/
│   └── threads_post/
├── skills/                # Manually invoked capabilities
│   ├── __init__.py
│   ├── _base.py           # Delegates to core/plugin_loader
│   ├── _http.py           # Delegates to core/http_utils (backward compat)
│   ├── GUIDE.md           # This file
│   └── hello_world/       # Example skill (reference for writing new skills)
```

## Creating a New Automation

```python
# heysquid/automations/my_automation/__init__.py

SKILL_META = {
    "name": "my_automation",
    "description": "Automated task that runs daily at 9 AM",
    "trigger": "schedule",      # "schedule" | "interval"
    "schedule": "09:00",        # HH:MM when trigger=schedule
    "enabled": True,
    "icon": "⏰",
}

def execute(**kwargs):
    # Put your logic here
    return {"done": True}
```

## Creating a New Skill

```python
# heysquid/skills/my_skill/__init__.py

SKILL_META = {
    "name": "my_skill",
    "description": "What this skill does",
    "trigger": "manual",       # "manual" | "webhook"
    "enabled": True,
    "icon": "🔧",
}

def execute(**kwargs):
    # Put your logic here
    return {"done": True}
```

## SKILL_META Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Y | Identifier (must match folder name) |
| `description` | Y | Description |
| `trigger` | Y | `"manual"`, `"schedule"`, `"interval"`, `"webhook"` |
| `schedule` | When trigger=schedule | `"HH:MM"` format (e.g., `"09:00"`) |
| `enabled` | - | Defaults to `True`. Set `False` to disable |
| `icon` | - | Dashboard Machine Room icon |
| `workspace` | - | Linked workspace name |

---

## execute() Function

```python
def execute(triggered_by="scheduler", chat_id=0, args="",
            payload=None, callback_url="", **kwargs):
    """
    Args:
        triggered_by: Who triggered execution ("scheduler" | "manual" | "pm" | "webhook")
        chat_id: Telegram chat_id (used for sending notifications)
        args: String arguments (from TUI: `/skill my_skill args`)
        payload: dict (JSON body received from webhook)
        callback_url: URL to POST to upon completion (e.g., n8n)
        **kwargs: For future extensions — must always be included

    Returns:
        dict or any value. run_skill()/run_automation() wraps it as {"ok": True, "result": return_value}.
        On exception, automatically handled as {"ok": False, "error": message}.
    """
```

You must always include `**kwargs` so that existing plugins won't break when new fields are added to PluginContext.

---

## HTTP Utilities

Use these instead of calling `requests` directly for external API calls:

```python
from heysquid.core.http_utils import get_secret, http_get, http_post_json, http_post_form

# Load secret from environment variables
token = get_secret("MY_API_TOKEN")

# GET
data = http_get("https://api.example.com/data", token=token)

# POST JSON
result = http_post_json("https://api.example.com/create",
                        payload={"key": "value"}, token=token)

# POST form-encoded (for legacy APIs)
result = http_post_form("https://api.example.com/submit",
                        data={"field": "value"}, token=token)
```

The old import `from heysquid.skills._http import ...` still works (backward compat).

---

## How to Run

### 1. Scheduler (Automation, automatic)
`trigger: "schedule"`, `schedule: "09:00"` → runs automatically every day at 9 AM

### 2. TUI (manual)
```
/skill my_skill
/skill my_skill args
```

### 3. Directly from PM
```python
# Automation
from heysquid.automations import run_automation
from heysquid.core.plugin_loader import PluginContext
ctx = PluginContext(triggered_by="pm", chat_id=12345)
result = run_automation("briefing", ctx)

# Skill
from heysquid.skills import run_skill, SkillContext
ctx = SkillContext(triggered_by="pm", chat_id=12345, args="args")
result = run_skill("my_skill", ctx)
```

### 4. Webhook (external trigger)
```bash
curl -X POST http://localhost:8585/webhook/briefing \
  -H "X-Webhook-Secret: secret" \
  -H "Content-Type: application/json" \
  -d '{"args": "args", "chat_id": 12345}'
```

Webhook looks for automations first, then falls back to skills.

---

## Config Override

Use `data/skills_config.json` to change settings without modifying code:

```json
{
  "briefing": {
    "schedule": "08:30",
    "enabled": false
  }
}
```

Both automations and skills share the same config file.
