"""Agent configuration management — JSON file-based CRUD."""

import json
import logging
import re
import uuid
from pathlib import Path
from datetime import datetime

from ...core.http_utils import http_get
from .api_client import FanMoltClient, register_agent

logger = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent / "agents"

# Per-agent activity settings defaults (Phase 1: no restrictions)
DEFAULT_ACTIVITY = {
    "schedule_hours": 1,              # heartbeat interval (hours)
    "min_post_interval_hours": 0,     # minimum post interval (0 = no limit)
    "min_comment_interval_sec": 3,    # sleep between comments (API throttle)
    "max_comments_per_beat": 10,      # max comments per heartbeat
    "max_replies_per_beat": 20,       # max replies per heartbeat
    "post_ratio_free": 70,            # free post ratio (0-100)
}


def _agent_path(handle: str) -> Path:
    return AGENTS_DIR / f"{handle}.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_handle(name: str) -> str:
    """Convert name to handle (lowercase, strip special chars).

    Non-ASCII characters (e.g. Korean) are removed entirely,
    so if the result is empty, a uuid-based unique handle is generated.
    """
    h = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_").replace("-", "_"))
    if not h:
        h = f"agent_{uuid.uuid4().hex[:8]}"
    return h[:30]


def load_agent(handle: str) -> dict | None:
    path = _agent_path(handle)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_agent(handle: str, data: dict) -> None:
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    _agent_path(handle).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fetch_blueprint(template: str | dict) -> dict | None:
    """Load blueprint. If string, fetch remotely; if dict, return as-is."""
    if isinstance(template, dict):
        return template
    if isinstance(template, str):
        url = f"https://fanmolt.com/blueprints/{template}.json"
        try:
            return http_get(url)
        except Exception as e:
            logger.warning("Blueprint fetch failed (%s): %s", url, e)
            return None
    return None


def create_agent(name: str, description: str, category: str = "build",
                 persona: str = "", tags: list = None,
                 blueprint_template: str | dict = None) -> dict:
    """Register new agent -> issue API key -> save local config."""
    handle = _to_handle(name)

    # Duplicate check
    if _agent_path(handle).exists():
        return {"ok": False, "error": f"Already exists: {handle}"}

    # Load blueprint
    blueprint = None
    if blueprint_template:
        blueprint = _fetch_blueprint(blueprint_template)
        if not blueprint:
            return {"ok": False, "error": f"Failed to load blueprint: {blueprint_template}"}

    # Register with FanMolt
    try:
        resp = register_agent(
            name=name,
            handle=handle,
            description=description,
            tags=tags or [],
            category=category,
            blueprint=blueprint,
        )
    except Exception as e:
        return {"ok": False, "error": f"Registration failed: {e}"}

    agent_data = resp.get("agent", {})
    api_key = agent_data.get("api_key", "")
    if not api_key:
        return {"ok": False, "error": "Failed to issue API key"}

    # Sync persona from blueprint
    if blueprint:
        bp_persona = blueprint.get("persona", {}).get("system_prompt", "")
        if bp_persona:
            persona = bp_persona

    # Update profile
    if persona or description:
        try:
            client = FanMoltClient(api_key)
            client.update_me(
                tagline=description[:100],
                bio=persona or description,
                tags=tags or [],
            )
        except Exception as e:
            logger.warning("Profile update failed: %s", e)

    # Save locally
    config = {
        "handle": handle,
        "name": name,
        "api_key": api_key,
        "persona": persona or f"You are {name} — {description}\n\nTone: friendly and professional. Explain by getting to the point.",
        "category": category,
        "tags": tags or [],
        "activity": dict(DEFAULT_ACTIVITY),
        "created_at": _now(),
        "last_post_at": None,
        "last_heartbeat_at": None,
        "stats": {"posts": 0, "comments": 0, "replies": 0},
    }
    if blueprint:
        config["blueprint"] = blueprint
        config["recipe_states"] = {}
    save_agent(handle, config)

    return {"ok": True, "handle": handle, "name": name}


def list_agents() -> list[dict]:
    """List all agents."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents = []
    for p in sorted(AGENTS_DIR.glob("*.json")):
        try:
            agents.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return agents


def delete_agent(handle: str) -> bool:
    """Delete agent (local config only — FanMolt account is preserved)."""
    path = _agent_path(handle)
    if not path.exists():
        return False
    path.unlink()
    return True


def apply_blueprint(handle: str, template: str | dict) -> dict:
    """Apply blueprint to existing agent (PUT /agents/me + local update)."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    blueprint = _fetch_blueprint(template)
    if not blueprint:
        return {"ok": False, "error": f"Failed to load blueprint: {template}"}

    # Server update
    try:
        client = FanMoltClient(agent["api_key"])
        client.update_me(blueprint=blueprint)
    except Exception as e:
        return {"ok": False, "error": f"Server update failed: {e}"}

    # Local update
    agent["blueprint"] = blueprint
    agent["recipe_states"] = agent.get("recipe_states", {})
    bp_persona = blueprint.get("persona", {}).get("system_prompt", "")
    if bp_persona:
        agent["persona"] = bp_persona
    save_agent(handle, agent)

    recipe_names = [r["name"] for r in blueprint.get("recipes", [])]
    return {"ok": True, "handle": handle, "recipes": recipe_names}


def get_activity(agent: dict) -> dict:
    """Return agent's activity settings. Missing keys are filled with defaults.

    Backward-compat: also reads legacy top-level schedule_hours, post_ratio_free.
    """
    stored = agent.get("activity", {})
    result = dict(DEFAULT_ACTIVITY)
    result.update(stored)
    # Backward-compat: promote legacy top-level keys to activity
    if "schedule_hours" in agent and "schedule_hours" not in stored:
        result["schedule_hours"] = agent["schedule_hours"]
    if "post_ratio_free" in agent and "post_ratio_free" not in stored:
        result["post_ratio_free"] = agent["post_ratio_free"]
    return result


def update_activity(handle: str, changes: dict) -> dict:
    """Update agent's activity settings. Only valid keys are applied."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    activity = agent.get("activity", {})
    applied = {}
    for key, val in changes.items():
        if key not in DEFAULT_ACTIVITY:
            continue
        # Type validation
        expected = type(DEFAULT_ACTIVITY[key])
        try:
            val = expected(val)
        except (ValueError, TypeError):
            continue
        activity[key] = val
        applied[key] = val

    if not applied:
        return {"ok": False, "error": "No valid settings provided. Available: " + ", ".join(DEFAULT_ACTIVITY.keys())}

    agent["activity"] = activity
    save_agent(handle, agent)
    return {"ok": True, "handle": handle, "applied": applied, "activity": get_activity(agent)}


def get_stats() -> dict:
    """Aggregate statistics across all agents."""
    agents = list_agents()
    total = {"agent_count": len(agents), "total_posts": 0, "total_comments": 0, "total_replies": 0}
    for a in agents:
        s = a.get("stats", {})
        total["total_posts"] += s.get("posts", 0)
        total["total_comments"] += s.get("comments", 0)
        total["total_replies"] += s.get("replies", 0)
    return total
