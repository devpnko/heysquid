"""
EasyText skill — AI thread draft generation + Google Trends.

Usage:
    easytext generate <topic> [--type opinion|promotion|info|daily] [--format three|five|free]
    easytext trends          — real-time Google Trends
    easytext og <url>        — fetch OG metadata for a Threads URL
"""

SKILL_META = {
    "name": "easytext",
    "description": "EasyText thread generation — drafts, trends, OG metadata",
    "trigger": "manual",
    "enabled": True,
    "icon": "✍️",
}


def execute(**kwargs) -> dict:
    """Skill entry point."""
    from ._client import generate_thread, parse_versions, get_google_trends, get_og_meta

    args = kwargs.get("args", "").strip()
    chat_id = kwargs.get("chat_id", 0)

    parts = args.split(None, 1)
    cmd = parts[0].lower() if parts else "help"
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd == "generate":
        return _cmd_generate(cmd_args, chat_id)
    elif cmd == "trends":
        return _cmd_trends(chat_id)
    elif cmd == "og":
        return _cmd_og(cmd_args, chat_id)
    else:
        msg = (
            "easytext commands:\n"
            "  generate <topic> [--type opinion] [--format three]\n"
            "  trends                — Google Trends\n"
            "  og <url>              — OG metadata"
        )
        _send_telegram(chat_id, msg)
        return {"ok": True, "message": msg}


def _cmd_generate(args: str, chat_id: int) -> dict:
    from ._client import generate_thread, parse_versions

    # Parse --type and --format flags
    content_type = "opinion"
    fmt = "three"
    topic_parts = []

    tokens = args.split()
    i = 0
    while i < len(tokens):
        if tokens[i] == "--type" and i + 1 < len(tokens):
            content_type = tokens[i + 1]
            i += 2
        elif tokens[i] == "--format" and i + 1 < len(tokens):
            fmt = tokens[i + 1]
            i += 2
        else:
            topic_parts.append(tokens[i])
            i += 1

    topic = " ".join(topic_parts)
    if not topic:
        return {"ok": False, "error": "Usage: easytext generate <topic>"}

    try:
        resp = generate_thread(topic, content_type=content_type, format=fmt)
        result_text = resp.get("result", "")
        versions = parse_versions(result_text)

        msg_lines = [f"✍️ {topic} — {len(versions)}개 버전 생성"]
        for idx, v in enumerate(versions, 1):
            preview = v[:200] + "..." if len(v) > 200 else v
            msg_lines.append(f"\n--- 버전 {idx} ---\n{preview}")

        msg = "\n".join(msg_lines)
        _send_telegram(chat_id, msg)
        return {"ok": True, "versions": versions, "count": len(versions)}
    except Exception as e:
        msg = f"생성 실패: {e}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": str(e)}


def _cmd_trends(chat_id: int) -> dict:
    from ._client import get_google_trends

    try:
        data = get_google_trends()
        _send_telegram(chat_id, f"📈 실시간 트렌드:\n{_format_trends(data)}")
        return {"ok": True, "data": data}
    except Exception as e:
        msg = f"트렌드 조회 실패: {e}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": str(e)}


def _cmd_og(args: str, chat_id: int) -> dict:
    from ._client import get_og_meta

    url = args.strip()
    if not url:
        return {"ok": False, "error": "Usage: easytext og <url>"}

    try:
        data = get_og_meta(url)
        msg = "\n".join(f"{k}: {v}" for k, v in data.items() if v)
        _send_telegram(chat_id, f"🔗 OG Meta:\n{msg}")
        return {"ok": True, "data": data}
    except Exception as e:
        msg = f"OG 조회 실패: {e}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": str(e)}


def _format_trends(data) -> str:
    """Format trends data for display."""
    if isinstance(data, list):
        return "\n".join(f"  • {item}" if isinstance(item, str) else f"  • {item}" for item in data[:20])
    if isinstance(data, dict):
        items = data.get("trends", data.get("items", data.get("data", [])))
        if isinstance(items, list):
            return "\n".join(f"  • {item}" if isinstance(item, str) else f"  • {item}" for item in items[:20])
        return str(data)
    return str(data)


def _send_telegram(chat_id: int, msg: str) -> None:
    if not chat_id:
        return
    try:
        from ...channels.telegram import send_message_sync
        send_message_sync(int(chat_id), msg, parse_mode=None)
    except Exception:
        pass
