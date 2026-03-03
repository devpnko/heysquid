"""Heartbeat runner — one activity cycle per agent."""

import logging
import random
import time
from datetime import datetime, timedelta

from .agent_manager import load_agent, save_agent, list_agents, get_beat, build_system_prompt
from .api_client import FanMoltClient
from .content_gen import generate_post, generate_post_from_recipe, generate_reply, generate_comment

logger = logging.getLogger(__name__)

MAX_COMMENTED_POSTS_CACHE = 100   # ring buffer max size
MAX_REPLIED_COMMENTS_CACHE = 200  # ring buffer max size


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


def _rt(agent: dict) -> dict:
    """Get (and lazily create) the _now runtime state dict."""
    return agent.setdefault("_now", {
        "stats": {"posts": 0, "comments": 0, "replies": 0},
        "last_post_at": None,
        "last_heartbeat_at": None,
        "recipe_states": {},
        "commented_posts": [],
        "replied_comments": [],
    })


def _handle(agent: dict) -> str:
    """Get agent handle, supporting both v2 (who.handle) and v1 (handle)."""
    return agent.get("who", {}).get("handle") or agent.get("handle", "?")


def _api_key(agent: dict) -> str:
    """Get agent API key, supporting both v2 (where.api_key) and v1 (api_key)."""
    return agent.get("where", {}).get("api_key") or agent.get("api_key", "")


def _get_due_recipes(agent: dict) -> list[dict]:
    """Return list of do.recipes that are due for execution."""
    do = agent.get("do") or {}
    recipes = do.get("recipes", [])
    if not recipes:
        return []

    recipe_states = _rt(agent).get("recipe_states", {})
    due = []

    for recipe in recipes:
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
    Beat settings are read from per-agent JSON config.
    """
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}", "handle": handle}

    act = get_beat(agent)
    rt = _rt(agent)
    client = FanMoltClient(_api_key(agent))
    persona = build_system_prompt(agent)
    engagement = agent.get("do", {}).get("engagement", {})
    result = {"handle": handle, "replies": 0, "comments": 0, "posted": False}

    llm_failed = False

    # 1. Check notifications -> reply to comments (highest priority)
    reply_style = engagement.get("reply_style")
    try:
        last_noti_id = rt.get("last_notification_id")
        noti_params = {"since": rt.get("last_heartbeat_at")}
        if last_noti_id:
            noti_params = {"after_id": last_noti_id}
        notifications = client.get_notifications(
            since=noti_params.get("since"),
            after_id=noti_params.get("after_id"),
        )
        replied = 0
        replied_comments = set(rt.get("replied_comments", []))
        for n in notifications:
            if replied >= act["max_replies_per_beat"]:
                break
            # Update cursor (regardless of processing result)
            cursor_id = n.get("comment_id") or n.get("id")
            if cursor_id:
                rt["last_notification_id"] = cursor_id
            if n.get("type") in ("comment.created", "comment.reply"):
                comment_id = n.get("comment_id")
                # Skip already-replied comments (dedup guard)
                if comment_id and comment_id in replied_comments:
                    logger.debug("%s: skipping already-replied comment %s", handle, comment_id)
                    continue
                try:
                    reply = generate_reply(persona, n, reply_style=reply_style)
                    client.create_comment(n["post_id"], reply, parent_id=comment_id)
                    replied += 1
                    if comment_id:
                        replied_comments.add(comment_id)
                    if act["min_comment_interval_sec"] > 0:
                        time.sleep(act["min_comment_interval_sec"])
                except RuntimeError:
                    llm_failed = True
                    logger.warning("%s: LLM unavailable — skipping replies", handle)
                    break
                except Exception as e:
                    logger.warning("Reply failed: %s", e)
        result["replies"] = replied
        # Persist replied_comments (ring buffer)
        rt["replied_comments"] = list(replied_comments)[-MAX_REPLIED_COMMENTS_CACHE:]
    except Exception as e:
        logger.warning("Notification fetch failed: %s", e)

    # 2. Browse feed -> leave comments (skip already commented posts)
    engage_topics = agent.get("whom", {}).get("audience", {}).get("topics")
    if not llm_failed:
        try:
            feed = client.get_feed(sort="new", limit=15)
            commented = 0
            commented_posts = set(rt.get("commented_posts", []))
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
                    # Fetch existing comments to avoid duplicating what's already been said
                    existing_comments = []
                    try:
                        existing_comments = client.get_comments(post_id)
                    except Exception:
                        pass
                    comment = generate_comment(
                        persona, post,
                        engage_topics=engage_topics,
                        existing_comments=existing_comments,
                    )
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
            rt["commented_posts"] = list(commented_posts)[-MAX_COMMENTED_POSTS_CACHE:]
        except Exception as e:
            logger.warning("Feed fetch failed: %s", e)

    # 3. Write post (cooldown check, skip if LLM failed)
    post_interval = act["min_post_interval_hours"]
    can_post = post_interval <= 0 or _hours_since(rt.get("last_post_at")) >= post_interval
    if not llm_failed and can_post:
        try:
            prev_titles = _get_prev_titles(client)
            due_recipes = _get_due_recipes(agent)

            if due_recipes:
                # Recipe mode: run due recipes sequentially
                rules = agent.get("soul", {}).get("boundaries") or None
                recipe_states = rt.get("recipe_states", {})
                for recipe in due_recipes:
                    try:
                        post_data = generate_post_from_recipe(
                            persona, recipe, rules=rules, prev_titles=prev_titles,
                        )
                        client.create_post(**post_data)
                        recipe_states.setdefault(recipe["name"], {})["last_run"] = _now()
                        result["posted"] = True
                        rt["last_post_at"] = _now()
                        prev_titles.append(post_data.get("title", ""))
                    except RuntimeError:
                        llm_failed = True
                        logger.warning(
                            "%s: LLM unavailable — skipping recipe %s", handle, recipe["name"]
                        )
                        break
                    except Exception as e:
                        logger.warning("Recipe %s execution failed: %s", recipe["name"], e)
                rt["recipe_states"] = recipe_states
            else:
                # Legacy mode: no recipes or none due
                category = agent.get("where", {}).get("category", "build")
                post_data = generate_post(persona, category, prev_titles)
                ratio = act["post_ratio_free"]
                post_data["is_free"] = random.random() * 100 < ratio
                client.create_post(**post_data)
                result["posted"] = True
                rt["last_post_at"] = _now()
        except RuntimeError:
            llm_failed = True
            logger.warning("%s: LLM unavailable — skipping post", handle)
        except Exception as e:
            logger.warning("Post creation failed: %s", e)

    if llm_failed:
        result["llm_unavailable"] = True

    # 4. Save state
    rt["last_heartbeat_at"] = _now()
    stats = rt.setdefault("stats", {"posts": 0, "comments": 0, "replies": 0})
    stats["replies"] = stats.get("replies", 0) + result["replies"]
    stats["comments"] = stats.get("comments", 0) + result["comments"]
    if result["posted"]:
        stats["posts"] = stats.get("posts", 0) + 1
    save_agent(handle, agent)

    result["ok"] = True
    return result


def run_all() -> list[dict]:
    """Run heartbeat for all agents (ignore schedule, run all)."""
    agents = list_agents()
    results = []
    for agent in agents:
        h = _handle(agent)
        try:
            r = run_heartbeat(h)
            results.append(r)
        except Exception as e:
            results.append({"handle": h, "ok": False, "error": str(e)})
    return results


def run_due_agents() -> list[dict]:
    """Run heartbeat only for agents whose beat.schedule_hours have elapsed."""
    agents = list_agents()
    results = []
    for agent in agents:
        h = _handle(agent)
        act = get_beat(agent)
        interval = act["schedule_hours"]
        elapsed = _hours_since(_rt(agent).get("last_heartbeat_at"))
        if elapsed < interval:
            continue
        try:
            r = run_heartbeat(h)
            results.append(r)
        except Exception as e:
            results.append({"handle": h, "ok": False, "error": str(e)})
    return results


def force_post(handle: str, recipe_name: str = None) -> dict:
    """Force write 1 post immediately, ignoring cooldown."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    client = FanMoltClient(_api_key(agent))
    persona = build_system_prompt(agent)
    rt = _rt(agent)

    try:
        prev_titles = _get_prev_titles(client)
        do = agent.get("do") or {}

        if recipe_name and do.get("recipes"):
            recipes = {r["name"]: r for r in do.get("recipes", [])}
            recipe = recipes.get(recipe_name)
            if not recipe:
                available = ", ".join(recipes.keys()) or "none"
                return {
                    "ok": False,
                    "error": f"Recipe '{recipe_name}' not found. Available: {available}",
                }
            rules = agent.get("soul", {}).get("boundaries") or None
            post_data = generate_post_from_recipe(persona, recipe, rules=rules, prev_titles=prev_titles)
            recipe_states = rt.get("recipe_states", {})
            recipe_states.setdefault(recipe_name, {})["last_run"] = _now()
            rt["recipe_states"] = recipe_states
        else:
            category = agent.get("where", {}).get("category", "build")
            post_data = generate_post(persona, category, prev_titles)

        resp = client.create_post(**post_data)
        rt["last_post_at"] = _now()
        stats = rt.setdefault("stats", {"posts": 0, "comments": 0, "replies": 0})
        stats["posts"] = stats.get("posts", 0) + 1
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
