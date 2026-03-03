"""Agent configuration management — JSON file-based CRUD."""

import json
import logging
import re
import uuid
from pathlib import Path
from datetime import datetime

from ...core.http_utils import http_get, get_secret
from .api_client import FanMoltClient, register_agent

logger = logging.getLogger(__name__)

AGENTS_DIR = Path(__file__).parent / "agents"

# 기본 owner_id — 등록 시 자동으로 대시보드에 연결
DEFAULT_OWNER_ID = get_secret("FANMOLT_OWNER_ID", "")

# Per-agent beat (activity rhythm) defaults
DEFAULT_BEAT = {
    "schedule_hours": 1,              # heartbeat interval (hours)
    "min_post_interval_hours": 0,     # minimum post interval (0 = no limit)
    "min_comment_interval_sec": 3,    # sleep between comments (API throttle)
    "max_comments_per_beat": 10,      # max comments per heartbeat
    "max_replies_per_beat": 20,       # max replies per heartbeat
    "post_ratio_free": 70,            # free post ratio (0-100)
}

# Backward-compat alias
DEFAULT_ACTIVITY = DEFAULT_BEAT


def _agent_path(handle: str) -> Path:
    return AGENTS_DIR / f"{handle}.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_handle(name: str) -> str:
    """Convert name to handle (lowercase, strip special chars)."""
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


def build_system_prompt(agent: dict) -> str:
    """Compose LLM system prompt from agent v2 sections.

    Falls back to legacy persona string if v2 sections are absent.
    """
    # Fallback: legacy flat structure (v1)
    if "soul" not in agent and "who" not in agent:
        return agent.get("persona", "")

    who = agent.get("who", {})
    soul = agent.get("soul", {})
    what = agent.get("what", {})
    whom = agent.get("whom", {})
    mind = agent.get("mind", {})

    parts = []

    # Identity + mission
    creature = who.get("creature", "")
    core = soul.get("core", "")
    if creature and core:
        parts.append(f"# Who I Am\n{creature}. {core}")
    elif core:
        parts.append(f"# Who I Am\n{core}")
    elif creature:
        parts.append(f"# Who I Am\n{creature}")

    # Style
    tone = soul.get("tone", [])
    if tone:
        parts.append(f"## My Style\nTone: {', '.join(tone)}")

    # Expertise
    domain = what.get("domain", "")
    topics = what.get("topics", [])
    if domain or topics:
        if domain and topics:
            expertise_str = f"{domain}: {', '.join(topics[:6])}"
        elif domain:
            expertise_str = domain
        else:
            expertise_str = ", ".join(topics[:6])
        parts.append(f"## My Expertise\n{expertise_str}")

    # Audience
    audience_who = whom.get("audience", {}).get("who", "")
    if audience_who:
        parts.append(f"## My Audience\n{audience_who}")

    # Lessons (from mind — accumulated wisdom influences behaviour)
    lessons = mind.get("lessons", [])
    if lessons:
        lessons_str = "\n".join(f"- {l}" for l in lessons[-5:])
        parts.append(f"## What I've Learned\n{lessons_str}")

    # Boundaries / rules
    boundaries = soul.get("boundaries", [])
    if boundaries:
        boundaries_str = "\n".join(f"- {b}" for b in boundaries)
        parts.append(f"## My Rules\n{boundaries_str}")

    return "\n\n".join(parts) if parts else ""


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
    """Register new agent -> issue API key -> save local config (v2 structure)."""
    handle = _to_handle(name)

    if _agent_path(handle).exists():
        return {"ok": False, "error": f"Already exists: {handle}"}

    blueprint = None
    if blueprint_template:
        blueprint = _fetch_blueprint(blueprint_template)
        if not blueprint:
            return {"ok": False, "error": f"Failed to load blueprint: {blueprint_template}"}

    try:
        resp = register_agent(
            name=name,
            handle=handle,
            description=description,
            tags=tags or [],
            category=category,
            blueprint=blueprint,
            owner_id=DEFAULT_OWNER_ID or None,
        )
    except Exception as e:
        return {"ok": False, "error": f"Registration failed: {e}"}

    agent_data = resp.get("agent", {})
    api_key = agent_data.get("api_key", "")
    if not api_key:
        return {"ok": False, "error": "Failed to issue API key"}

    bp_persona = (blueprint or {}).get("persona") or {}
    bp_expertise = (blueprint or {}).get("expertise") or {}
    bp_engagement = (blueprint or {}).get("engagement") or {}
    bp_recipes = (blueprint or {}).get("recipes") or []
    bp_rules = (blueprint or {}).get("rules") or []

    soul_core = (
        bp_persona.get("system_prompt")
        or persona
        or f"You are {name} — {description}\n\nTone: friendly and professional. Get to the point."
    )

    # Update FanMolt profile
    try:
        client = FanMoltClient(api_key)
        client.update_me(
            tagline=description[:100],
            bio=soul_core[:500],
            tags=tags or [],
        )
    except Exception as e:
        logger.warning("Profile update failed: %s", e)

    config = {
        "who": {
            "handle": handle,
            "name": name,
            "emoji": "",
            "creature": "",
            "born_at": _now(),
        },
        "soul": {
            "core": soul_core,
            "tone": bp_persona.get("tone", []),
            "boundaries": bp_rules,
            "updated_at": _now(),
        },
        "what": {
            "domain": bp_expertise.get("domain", category),
            "topics": bp_expertise.get("topics", tags or []),
            "languages": bp_persona.get("languages", ["ko"]),
            "sources": bp_expertise.get("sources", []),
        },
        "whom": {
            "pm": {"name": "상혁", "notes": ""},
            "audience": {
                "who": "",
                "wants": [],
                "topics": bp_engagement.get("engage_topics", tags or []),
            },
        },
        "mind": {"events": [], "lessons": []},
        "do": {
            "recipes": bp_recipes,
            "engagement": {
                "reply_style": bp_engagement.get("reply_style", "helpful"),
                "browse_feed": bp_engagement.get("browse_feed", True),
            },
        },
        "beat": dict(DEFAULT_BEAT),
        "where": {
            "platform": "fanmolt",
            "api_key": api_key,
            "category": category,
            "tags": tags or [],
        },
        "_now": {
            "stats": {"posts": 0, "comments": 0, "replies": 0},
            "last_post_at": None,
            "last_heartbeat_at": None,
            "recipe_states": {},
            "commented_posts": [],
            "replied_comments": [],
        },
    }
    save_agent(handle, config)
    return {"ok": True, "handle": handle, "name": name}


def list_agents() -> list[dict]:
    """List all agents (excludes files starting with '_')."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents = []
    for p in sorted(AGENTS_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
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
        api_key = agent.get("where", {}).get("api_key") or agent.get("api_key", "")
        client = FanMoltClient(api_key)
        client.update_me(blueprint=blueprint)
    except Exception as e:
        return {"ok": False, "error": f"Server update failed: {e}"}

    # Local update — map blueprint fields to v2 sections
    bp_persona = blueprint.get("persona") or {}
    bp_expertise = blueprint.get("expertise") or {}
    bp_engagement = blueprint.get("engagement") or {}
    bp_recipes = blueprint.get("recipes") or []
    bp_rules = blueprint.get("rules") or []

    agent.setdefault("soul", {})
    agent.setdefault("what", {})
    agent.setdefault("do", {})
    agent.setdefault("whom", {}).setdefault("audience", {})

    if bp_persona.get("system_prompt"):
        agent["soul"]["core"] = bp_persona["system_prompt"]
    if bp_persona.get("tone"):
        agent["soul"]["tone"] = bp_persona["tone"]
    if bp_rules:
        agent["soul"]["boundaries"] = bp_rules
    if bp_expertise.get("domain"):
        agent["what"]["domain"] = bp_expertise["domain"]
    if bp_expertise.get("topics"):
        agent["what"]["topics"] = bp_expertise["topics"]
    if bp_expertise.get("sources"):
        agent["what"]["sources"] = bp_expertise["sources"]
    if bp_recipes:
        agent["do"]["recipes"] = bp_recipes
    agent["do"]["engagement"] = {
        "reply_style": bp_engagement.get("reply_style", "helpful"),
        "browse_feed": bp_engagement.get("browse_feed", True),
    }
    if bp_engagement.get("engage_topics"):
        agent["whom"]["audience"]["topics"] = bp_engagement["engage_topics"]

    agent.setdefault("_now", {}).setdefault("recipe_states", {})
    save_agent(handle, agent)

    recipe_names = [r["name"] for r in bp_recipes]
    return {"ok": True, "handle": handle, "recipes": recipe_names}


def get_beat(agent: dict) -> dict:
    """Return agent's beat (activity rhythm) settings. Missing keys filled with defaults.

    Reads from agent["beat"], with fallback to legacy agent["activity"].
    """
    stored = agent.get("beat") or agent.get("activity") or {}
    result = dict(DEFAULT_BEAT)
    result.update(stored)
    return result


# Backward-compat alias
def get_activity(agent: dict) -> dict:
    return get_beat(agent)


def update_beat(handle: str, changes: dict) -> dict:
    """Update agent's beat settings. Only valid keys are applied."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    beat = agent.get("beat", {})
    applied = {}
    for key, val in changes.items():
        if key not in DEFAULT_BEAT:
            continue
        expected = type(DEFAULT_BEAT[key])
        try:
            val = expected(val)
        except (ValueError, TypeError):
            continue
        beat[key] = val
        applied[key] = val

    if not applied:
        return {
            "ok": False,
            "error": "No valid settings provided. Available: " + ", ".join(DEFAULT_BEAT.keys()),
        }

    agent["beat"] = beat
    save_agent(handle, agent)
    return {"ok": True, "handle": handle, "applied": applied, "beat": get_beat(agent)}


# Backward-compat alias
def update_activity(handle: str, changes: dict) -> dict:
    return update_beat(handle, changes)


def update_mind(handle: str, event: str = None, lesson: str = None,
                max_events: int = 20) -> dict:
    """Append to agent's mind.events (ring buffer) or mind.lessons (unlimited).

    Events: raw observations, kept as a rolling 20-item log.
    Lessons: refined insights, accumulated indefinitely and injected into system prompt.
    """
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    mind = agent.setdefault("mind", {"events": [], "lessons": []})
    added = []

    if event:
        entry = {"at": _now()[:10], "what": event}
        mind.setdefault("events", []).append(entry)
        mind["events"] = mind["events"][-max_events:]
        added.append("event")

    if lesson:
        mind.setdefault("lessons", []).append(lesson)
        added.append("lesson")

    save_agent(handle, agent)
    return {"ok": True, "handle": handle, "added": added}


def get_stats() -> dict:
    """Aggregate statistics across all agents."""
    agents = list_agents()
    total = {
        "agent_count": len(agents),
        "total_posts": 0,
        "total_comments": 0,
        "total_replies": 0,
    }
    for a in agents:
        # Support both v2 (_now.stats) and v1 (stats) layouts
        s = (a.get("_now") or {}).get("stats") or a.get("stats") or {}
        total["total_posts"] += s.get("posts", 0)
        total["total_comments"] += s.get("comments", 0)
        total["total_replies"] += s.get("replies", 0)
    return total
