"""
FanMolt skill — AI creator registration/operation/report automation.

A remote control for SQUID to manage FanMolt agents.
The owner only defines the persona; SQUID handles the heartbeat loop.

Usage:
    fanmolt create <name> <description>   — register agent
    fanmolt list                           — list agents
    fanmolt stats                          — statistics
    fanmolt beat [name]                    — run 1 heartbeat cycle
    fanmolt post <name> [recipe_name]      — write 1 post
    fanmolt blueprint <name> <template>    — apply blueprint
    fanmolt instructions <name>            — view instructions
    fanmolt config <name> [key=value ...]  — view/change activity settings
    fanmolt del <name>                     — delete agent
"""

SKILL_META = {
    "name": "fanmolt",
    "description": "FanMolt AI creator management — registration, activity, reports",
    "trigger": "manual",
    "enabled": True,
    "icon": "💰",
}


def execute(**kwargs) -> dict:
    """Skill entry point.

    triggered_by="scheduler" → heartbeat for all agents
    triggered_by="manual"    → parse args and run subcommand
    """
    from .agent_manager import create_agent, list_agents, delete_agent, get_stats
    from .heartbeat_runner import run_heartbeat, run_all, force_post

    triggered_by = kwargs.get("triggered_by", "manual")
    args = kwargs.get("args", "").strip()
    chat_id = kwargs.get("chat_id", 0)

    # scheduler → full heartbeat
    if triggered_by == "scheduler":
        results = run_all()
        report = _format_report(results)
        _send_telegram(chat_id, report)
        return {"ok": True, "report": report, "results": results}

    # manual → subcommand
    parts = args.split(None, 1)
    cmd = parts[0].lower() if parts else "help"
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd == "create":
        return _cmd_create(cmd_args, chat_id)
    elif cmd == "list":
        return _cmd_list(chat_id)
    elif cmd == "stats":
        return _cmd_stats(chat_id)
    elif cmd == "beat":
        return _cmd_beat(cmd_args, chat_id)
    elif cmd == "post":
        return _cmd_post(cmd_args, chat_id)
    elif cmd == "blueprint":
        return _cmd_blueprint(cmd_args, chat_id)
    elif cmd == "instructions":
        return _cmd_instructions(cmd_args, chat_id)
    elif cmd == "config":
        return _cmd_config(cmd_args, chat_id)
    elif cmd == "del":
        return _cmd_del(cmd_args, chat_id)
    else:
        msg = (
            "fanmolt commands:\n"
            "  create <name> <description>   — register agent\n"
            "  list                           — list agents\n"
            "  stats                          — statistics\n"
            "  beat [name]                    — heartbeat\n"
            "  post <name> [recipe_name]      — write post\n"
            "  blueprint <name> <template>    — apply blueprint\n"
            "  instructions <name>            — view instructions\n"
            "  config <name> [key=val ...]    — activity settings\n"
            "  del <name>                     — delete agent"
        )
        _send_telegram(chat_id, msg)
        return {"ok": True, "message": msg}


# --- subcommands ---


def _cmd_create(args: str, chat_id: int) -> dict:
    from .agent_manager import create_agent

    parts = args.split(None, 1)
    if not parts:
        return {"ok": False, "error": "Usage: fanmolt create <name> <description>"}
    name = parts[0]
    desc = parts[1] if len(parts) > 1 else f"{name} AI creator"
    result = create_agent(name=name, description=desc)
    msg = f"✅ {name} registered" if result.get("ok") else f"❌ Registration failed: {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_list(chat_id: int) -> dict:
    from .agent_manager import list_agents, get_beat

    agents = list_agents()
    if not agents:
        msg = "No registered agents"
    else:
        lines = [f"📋 {len(agents)} agent(s):"]
        for a in agents:
            name = a.get("who", {}).get("name") or a.get("name", "?")
            handle = a.get("who", {}).get("handle") or a.get("handle", "?")
            posts = (a.get("_now") or {}).get("stats", a.get("stats", {})).get("posts", 0)
            act = get_beat(a)
            sched = act["schedule_hours"]
            lines.append(f"  • {name} (@{handle}) — {posts} post(s) | ⏱{sched}h")
        msg = "\n".join(lines)
    _send_telegram(chat_id, msg)
    return {"ok": True, "agents": agents}


def _cmd_stats(chat_id: int) -> dict:
    from .agent_manager import get_stats

    stats = get_stats()
    msg = (
        f"📊 FanMolt overall stats\n"
        f"  Agents: {stats['agent_count']}\n"
        f"  Posts: {stats['total_posts']}\n"
        f"  Comments: {stats['total_comments']}\n"
        f"  Replies: {stats['total_replies']}"
    )
    _send_telegram(chat_id, msg)
    return {"ok": True, "stats": stats}


def _cmd_beat(args: str, chat_id: int) -> dict:
    from .heartbeat_runner import run_heartbeat, run_all

    handle = args.strip()
    if handle:
        result = run_heartbeat(handle)
    else:
        results = run_all()
        result = {"all": results}
    msg = _format_report([result] if handle else results)
    _send_telegram(chat_id, msg)
    return {"ok": True, "result": result}


def _cmd_post(args: str, chat_id: int) -> dict:
    from .heartbeat_runner import force_post

    parts = args.strip().split(None, 1)
    if not parts:
        return {"ok": False, "error": "Usage: fanmolt post <name> [recipe_name]"}
    handle = parts[0]
    recipe_name = parts[1] if len(parts) > 1 else None
    result = force_post(handle, recipe_name=recipe_name)
    label = f"{handle}" + (f" ({recipe_name})" if recipe_name else "")
    msg = f"✅ {label} post created" if result.get("ok") else f"❌ {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_blueprint(args: str, chat_id: int) -> dict:
    from .agent_manager import apply_blueprint

    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return {"ok": False, "error": "Usage: fanmolt blueprint <name> <template>"}
    handle, template_name = parts[0], parts[1]
    result = apply_blueprint(handle, template_name)
    if result.get("ok"):
        recipes = ", ".join(result.get("recipes", []))
        msg = f"✅ Blueprint applied to {handle}\nRecipes: {recipes}"
    else:
        msg = f"❌ {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_instructions(args: str, chat_id: int) -> dict:
    from .agent_manager import load_agent
    from .api_client import FanMoltClient

    handle = args.strip()
    if not handle:
        return {"ok": False, "error": "Usage: fanmolt instructions <name>"}
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"Agent not found: {handle}"}

    try:
        api_key = agent.get("where", {}).get("api_key") or agent.get("api_key", "")
        client = FanMoltClient(api_key)
        md = client.get_instructions()
        # Telegram message length limit (4096 chars)
        if len(md) > 4000:
            md = md[:4000] + "\n\n... (truncated)"
        _send_telegram(chat_id, md)
        return {"ok": True, "length": len(md)}
    except Exception as e:
        msg = f"❌ Failed to fetch instructions: {e}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": str(e)}


def _cmd_config(args: str, chat_id: int) -> dict:
    from .agent_manager import load_agent, get_beat, update_beat, DEFAULT_BEAT as DEFAULT_ACTIVITY

    parts = args.strip().split()
    if not parts:
        # Show available config keys
        lines = ["⚙️ fanmolt config <name> [key=val ...]\n\nAvailable keys:"]
        for k, v in DEFAULT_ACTIVITY.items():
            lines.append(f"  {k} = {v}  ({type(v).__name__})")
        lines.append("\nExample: fanmolt config my_agent schedule_hours=2 max_comments_per_beat=5")
        msg = "\n".join(lines)
        _send_telegram(chat_id, msg)
        return {"ok": True, "message": msg}

    handle = parts[0]
    agent = load_agent(handle)
    if not agent:
        msg = f"❌ Agent not found: {handle}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": msg}

    # parse key=value pairs
    changes = {}
    for part in parts[1:]:
        if "=" in part:
            k, v = part.split("=", 1)
            changes[k] = v

    if not changes:
        # View mode: show current settings
        act = get_beat(agent)
        lines = [f"⚙️ {handle} activity settings:"]
        for k, v in act.items():
            default = DEFAULT_ACTIVITY.get(k)
            marker = "" if v == default else " ✏️"
            lines.append(f"  {k} = {v}{marker}")
        msg = "\n".join(lines)
        _send_telegram(chat_id, msg)
        return {"ok": True, "activity": act}

    # Update mode
    result = update_beat(handle, changes)
    if result.get("ok"):
        applied = result["applied"]
        lines = [f"✅ {handle} settings updated:"]
        for k, v in applied.items():
            lines.append(f"  {k} = {v}")
        msg = "\n".join(lines)
    else:
        msg = f"❌ {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_del(args: str, chat_id: int) -> dict:
    from .agent_manager import delete_agent

    handle = args.strip()
    if not handle:
        return {"ok": False, "error": "Usage: fanmolt del <name>"}
    ok = delete_agent(handle)
    msg = f"✅ {handle} deleted" if ok else f"❌ {handle} not found"
    _send_telegram(chat_id, msg)
    return {"ok": ok}


# --- helpers ---


def _format_report(results: list) -> str:
    if not results:
        return "No agents to run"
    lines = ["📊 FanMolt heartbeat complete"]
    for r in results:
        name = r.get("handle", "?")
        if r.get("error"):
            lines.append(f"  {name}: ❌ {r['error'][:50]}")
            continue
        replies = r.get("replies", 0)
        comments = r.get("comments", 0)
        posted = "1 post" if r.get("posted") else ""
        parts = []
        if replies:
            parts.append(f"{replies} reply(ies)")
        if comments:
            parts.append(f"{comments} comment(s)")
        if posted:
            parts.append(posted)
        activity = " | ".join(parts) if parts else "no activity"
        lines.append(f"  {name}: {activity}")
    return "\n".join(lines)


def _send_telegram(chat_id: int, msg: str) -> None:
    if not chat_id:
        return
    try:
        from ...channels.telegram import send_message_sync
        send_message_sync(int(chat_id), msg, parse_mode=None)
    except Exception:
        pass
