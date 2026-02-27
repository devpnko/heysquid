"""Heartbeat runner — one activity cycle per agent."""

import logging
import random
import time
from datetime import datetime, timedelta

from .agent_manager import load_agent, save_agent, list_agents, get_activity
from .api_client import FanMoltClient
from .content_gen import generate_post, generate_post_from_recipe, generate_reply, generate_comment

logger = logging.getLogger(__name__)

MAX_COMMENTED_POSTS_CACHE = 100  # ring buffer max size


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hours_since(iso_str: str | None) -> float:
    if not iso_str:
        return 999
    try:
        dt = datetime.fromisoformat(iso_str)
        return (datetime.now() - dt).total_seconds() / 3600
    except Exception:
        return 999


# Minimum interval per trigger type (hours)
_TRIGGER_INTERVALS = {
    "daily": 20,       # ~1 day (with buffer)
    "weekly": 160,     # ~7 days (with buffer)
    "every_4h": 4,
}


def _get_due_recipes(agent: dict) -> list[dict]:
    """Return list of blueprint recipes that are due for execution."""
    blueprint = agent.get("blueprint")
    if not blueprint:
        return []

    recipe_states = agent.get("recipe_states", {})
    due = []

    for recipe in blueprint.get("recipes", []):
        trigger = recipe.get("trigger", "on_demand")
        if trigger == "on_demand":
            continue

        interval = _TRIGGER_INTERVALS.get(trigger)
        if interval is None:
            continue

        state = recipe_states.get(recipe["name"], {})
        last_run = state.get("last_run")
        if _hours_since(last_run) >= interval:
            due.append(recipe)

    return due


def run_heartbeat(handle: str) -> dict:
    """One heartbeat cycle for a single agent.

    Priority: reply to comments > engage in feed > write post
    Activity settings are read from per-agent JSON config.
    """
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}", "handle": handle}

    act = get_activity(agent)
    client = FanMoltClient(agent["api_key"])
    persona = agent.get("persona", "")
    blueprint = agent.get("blueprint")
    engagement = blueprint.get("engagement", {}) if blueprint else {}
    result = {"handle": handle, "replies": 0, "comments": 0, "posted": False}

    llm_failed = False

    # 1. Check notifications -> reply to comments (highest priority)
    reply_style = engagement.get("reply_style")
    try:
        last_noti_id = agent.get("last_notification_id")
        noti_params = {"since": agent.get("last_heartbeat_at")}
        if last_noti_id:
            noti_params = {"after_id": last_noti_id}
        notifications = client.get_notifications(
            since=noti_params.get("since"),
            after_id=noti_params.get("after_id"),
        )
        replied = 0
        for n in notifications:
            if replied >= act["max_replies_per_beat"]:
                break
            if n.get("type") in ("comment.created", "comment.reply"):
                try:
                    reply = generate_reply(persona, n, reply_style=reply_style)
                    client.create_comment(n["post_id"], reply, parent_id=n.get("comment_id"))
                    replied += 1
                    if act["min_comment_interval_sec"] > 0:
                        time.sleep(act["min_comment_interval_sec"])
                except RuntimeError:
                    llm_failed = True
                    logger.warning("%s: LLM unavailable — skipping replies", handle)
                    break
                except Exception as e:
                    logger.warning("Reply failed: %s", e)
            # Update cursor (regardless of processing result)
            if n.get("id"):
                agent["last_notification_id"] = n["id"]
        result["replies"] = replied
    except Exception as e:
        logger.warning("Notification fetch failed: %s", e)

    # 2. Browse feed -> leave comments (skip already commented posts)
    engage_topics = engagement.get("engage_topics")
    if not llm_failed:
        try:
            feed = client.get_feed(sort="new", limit=15)
            commented = 0
            commented_posts = set(agent.get("commented_posts", []))
            for post in feed:
                if commented >= act["max_comments_per_beat"]:
                    break
                post_id = post.get("id", "")
                # Skip own posts or already commented posts
                creator = post.get("creator", {})
                if creator.get("handle") == handle:
                    continue
                if post_id in commented_posts:
                    continue
                try:
                    comment = generate_comment(persona, post, engage_topics=engage_topics)
                    if comment:
                        client.create_comment(post_id, comment)
                        commented += 1
                        commented_posts.add(post_id)
                        if act["min_comment_interval_sec"] > 0:
                            time.sleep(act["min_comment_interval_sec"])
                except RuntimeError:
                    llm_failed = True
                    logger.warning("%s: LLM unavailable — skipping comments", handle)
                    break
                except Exception as e:
                    logger.warning("Comment failed: %s", e)
            result["comments"] = commented
            # ring buffer: keep only the last 100
            agent["commented_posts"] = list(commented_posts)[-MAX_COMMENTED_POSTS_CACHE:]
        except Exception as e:
            logger.warning("Feed fetch failed: %s", e)

    # 3. Write post (cooldown check, skip if LLM failed)
    post_interval = act["min_post_interval_hours"]
    can_post = post_interval <= 0 or _hours_since(agent.get("last_post_at")) >= post_interval
    if not llm_failed and can_post:
        try:
            prev_titles = _get_prev_titles(client)
            due_recipes = _get_due_recipes(agent)

            if due_recipes:
                # Blueprint mode: run due recipes sequentially
                rules = blueprint.get("rules") if blueprint else None
                recipe_states = agent.get("recipe_states", {})
                for recipe in due_recipes:
                    try:
                        post_data = generate_post_from_recipe(
                            persona, recipe, rules=rules, prev_titles=prev_titles,
                        )
                        client.create_post(**post_data)
                        recipe_states.setdefault(recipe["name"], {})["last_run"] = _now()
                        result["posted"] = True
                        agent["last_post_at"] = _now()
                        prev_titles.append(post_data.get("title", ""))
                    except RuntimeError:
                        llm_failed = True
                        logger.warning("%s: LLM unavailable — skipping recipe %s", handle, recipe["name"])
                        break
                    except Exception as e:
                        logger.warning("Recipe %s execution failed: %s", recipe["name"], e)
                agent["recipe_states"] = recipe_states
            else:
                # Legacy mode: no blueprint or no due recipes
                post_data = generate_post(persona, agent.get("category", "build"), prev_titles)
                ratio = act["post_ratio_free"]
                post_data["is_free"] = random.random() * 100 < ratio
                client.create_post(**post_data)
                result["posted"] = True
                agent["last_post_at"] = _now()
        except RuntimeError:
            llm_failed = True
            logger.warning("%s: LLM unavailable — skipping post", handle)
        except Exception as e:
            logger.warning("Post creation failed: %s", e)

    if llm_failed:
        result["llm_unavailable"] = True

    # 4. Save state
    agent["last_heartbeat_at"] = _now()
    stats = agent.get("stats", {})
    stats["replies"] = stats.get("replies", 0) + result["replies"]
    stats["comments"] = stats.get("comments", 0) + result["comments"]
    if result["posted"]:
        stats["posts"] = stats.get("posts", 0) + 1
    agent["stats"] = stats
    save_agent(handle, agent)

    result["ok"] = True
    return result


def run_all() -> list[dict]:
    """Run heartbeat for all agents (ignore schedule, run all)."""
    agents = list_agents()
    results = []
    for agent in agents:
        try:
            r = run_heartbeat(agent["handle"])
            results.append(r)
        except Exception as e:
            results.append({"handle": agent.get("handle", "?"), "ok": False, "error": str(e)})
    return results


def run_due_agents() -> list[dict]:
    """Run heartbeat only for agents whose schedule_hours have elapsed.

    Each agent's activity.schedule_hours is checked individually.
    """
    agents = list_agents()
    results = []
    for agent in agents:
        handle = agent.get("handle", "?")
        act = get_activity(agent)
        interval = act["schedule_hours"]
        elapsed = _hours_since(agent.get("last_heartbeat_at"))
        if elapsed < interval:
            continue
        try:
            r = run_heartbeat(handle)
            results.append(r)
        except Exception as e:
            results.append({"handle": handle, "ok": False, "error": str(e)})
    return results


def force_post(handle: str, recipe_name: str = None) -> dict:
    """Force write 1 post immediately, ignoring cooldown. If recipe_name is given, use that recipe."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    client = FanMoltClient(agent["api_key"])
    persona = agent.get("persona", "")
    blueprint = agent.get("blueprint")

    try:
        prev_titles = _get_prev_titles(client)

        if recipe_name and blueprint:
            # Generate using specific recipe
            recipes = {r["name"]: r for r in blueprint.get("recipes", [])}
            recipe = recipes.get(recipe_name)
            if not recipe:
                available = ", ".join(recipes.keys()) or "none"
                return {"ok": False, "error": f"Recipe '{recipe_name}' not found. Available: {available}"}
            rules = blueprint.get("rules")
            post_data = generate_post_from_recipe(persona, recipe, rules=rules, prev_titles=prev_titles)
            # Update recipe_states
            recipe_states = agent.get("recipe_states", {})
            recipe_states.setdefault(recipe_name, {})["last_run"] = _now()
            agent["recipe_states"] = recipe_states
        else:
            post_data = generate_post(persona, agent.get("category", "build"), prev_titles)

        resp = client.create_post(**post_data)
        agent["last_post_at"] = _now()
        stats = agent.get("stats", {})
        stats["posts"] = stats.get("posts", 0) + 1
        agent["stats"] = stats
        save_agent(handle, agent)
        return {"ok": True, "title": post_data.get("title"), "response": resp}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_prev_titles(client: FanMoltClient) -> list[str]:
    """Fetch previous post titles (for deduplication)."""
    try:
        posts = client.list_posts(limit=10)
        return [p.get("title", "") for p in posts]
    except Exception:
        return []
