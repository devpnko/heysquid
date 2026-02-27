"""
FanMolt 스킬 — AI 크리에이터 등록/운영/리포트 자동화.

SQUID가 FanMolt 에이전트를 관리하는 리모컨.
오너는 persona만 정의, 나머지는 SQUID가 heartbeat 돌림.

사용법:
    fanmolt create <이름> <설명>          — 에이전트 등록
    fanmolt list                         — 목록
    fanmolt stats                        — 통계
    fanmolt beat [이름]                  — heartbeat 1사이클
    fanmolt post <이름> [레시피명]        — 글 1개 작성
    fanmolt blueprint <이름> <템플릿>     — Blueprint 적용
    fanmolt instructions <이름>           — 지시문 조회
    fanmolt del <이름>                   — 삭제
"""

SKILL_META = {
    "name": "fanmolt",
    "description": "FanMolt AI 크리에이터 관리 — 등록, 활동, 리포트",
    "trigger": "manual",
    "enabled": True,
    "icon": "💰",
}


def execute(**kwargs) -> dict:
    """스킬 진입점.

    triggered_by="scheduler" → 전체 에이전트 heartbeat
    triggered_by="manual"    → args 파싱해서 서브커맨드 실행
    """
    from .agent_manager import create_agent, list_agents, delete_agent, get_stats
    from .heartbeat_runner import run_heartbeat, run_all, force_post

    triggered_by = kwargs.get("triggered_by", "manual")
    args = kwargs.get("args", "").strip()
    chat_id = kwargs.get("chat_id", 0)

    # 스케줄러 → 전체 heartbeat
    if triggered_by == "scheduler":
        results = run_all()
        report = _format_report(results)
        _send_telegram(chat_id, report)
        return {"ok": True, "report": report, "results": results}

    # 수동 → 서브커맨드
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
    elif cmd == "del":
        return _cmd_del(cmd_args, chat_id)
    else:
        msg = (
            "fanmolt 명령어:\n"
            "  create <이름> <설명>          — 에이전트 등록\n"
            "  list                         — 목록\n"
            "  stats                        — 통계\n"
            "  beat [이름]                  — heartbeat\n"
            "  post <이름> [레시피명]        — 글 작성\n"
            "  blueprint <이름> <템플릿>     — Blueprint 적용\n"
            "  instructions <이름>           — 지시문 조회\n"
            "  del <이름>                   — 삭제"
        )
        _send_telegram(chat_id, msg)
        return {"ok": True, "message": msg}


# --- 서브커맨드 ---


def _cmd_create(args: str, chat_id: int) -> dict:
    from .agent_manager import create_agent

    parts = args.split(None, 1)
    if not parts:
        return {"ok": False, "error": "사용법: fanmolt create <이름> <설명>"}
    name = parts[0]
    desc = parts[1] if len(parts) > 1 else f"{name} AI 크리에이터"
    result = create_agent(name=name, description=desc)
    msg = f"✅ {name} 등록 완료" if result.get("ok") else f"❌ 등록 실패: {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_list(chat_id: int) -> dict:
    from .agent_manager import list_agents

    agents = list_agents()
    if not agents:
        msg = "등록된 에이전트 없음"
    else:
        lines = [f"📋 에이전트 {len(agents)}개:"]
        for a in agents:
            posts = a.get("stats", {}).get("posts", 0)
            lines.append(f"  • {a['name']} (@{a['handle']}) — 글 {posts}개")
        msg = "\n".join(lines)
    _send_telegram(chat_id, msg)
    return {"ok": True, "agents": agents}


def _cmd_stats(chat_id: int) -> dict:
    from .agent_manager import get_stats

    stats = get_stats()
    msg = (
        f"📊 FanMolt 전체 통계\n"
        f"  에이전트: {stats['agent_count']}개\n"
        f"  글: {stats['total_posts']}개\n"
        f"  댓글: {stats['total_comments']}개\n"
        f"  답변: {stats['total_replies']}개"
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
        return {"ok": False, "error": "사용법: fanmolt post <이름> [레시피명]"}
    handle = parts[0]
    recipe_name = parts[1] if len(parts) > 1 else None
    result = force_post(handle, recipe_name=recipe_name)
    label = f"{handle}" + (f" ({recipe_name})" if recipe_name else "")
    msg = f"✅ {label} 글 작성 완료" if result.get("ok") else f"❌ {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_blueprint(args: str, chat_id: int) -> dict:
    from .agent_manager import apply_blueprint

    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return {"ok": False, "error": "사용법: fanmolt blueprint <이름> <템플릿>"}
    handle, template_name = parts[0], parts[1]
    result = apply_blueprint(handle, template_name)
    if result.get("ok"):
        recipes = ", ".join(result.get("recipes", []))
        msg = f"✅ {handle}에 Blueprint 적용 완료\n레시피: {recipes}"
    else:
        msg = f"❌ {result.get('error')}"
    _send_telegram(chat_id, msg)
    return result


def _cmd_instructions(args: str, chat_id: int) -> dict:
    from .agent_manager import load_agent
    from .api_client import FanMoltClient

    handle = args.strip()
    if not handle:
        return {"ok": False, "error": "사용법: fanmolt instructions <이름>"}
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"에이전트 없음: {handle}"}

    try:
        client = FanMoltClient(agent["api_key"])
        md = client.get_instructions()
        # 텔레그램 메시지 길이 제한 (4096자)
        if len(md) > 4000:
            md = md[:4000] + "\n\n... (잘림)"
        _send_telegram(chat_id, md)
        return {"ok": True, "length": len(md)}
    except Exception as e:
        msg = f"❌ 지시문 조회 실패: {e}"
        _send_telegram(chat_id, msg)
        return {"ok": False, "error": str(e)}


def _cmd_del(args: str, chat_id: int) -> dict:
    from .agent_manager import delete_agent

    handle = args.strip()
    if not handle:
        return {"ok": False, "error": "사용법: fanmolt del <이름>"}
    ok = delete_agent(handle)
    msg = f"✅ {handle} 삭제 완료" if ok else f"❌ {handle} 찾을 수 없음"
    _send_telegram(chat_id, msg)
    return {"ok": ok}


# --- 헬퍼 ---


def _format_report(results: list) -> str:
    if not results:
        return "활동할 에이전트 없음"
    lines = ["📊 FanMolt heartbeat 완료"]
    for r in results:
        name = r.get("handle", "?")
        if r.get("error"):
            lines.append(f"  {name}: ❌ {r['error'][:50]}")
            continue
        replies = r.get("replies", 0)
        comments = r.get("comments", 0)
        posted = "글 1" if r.get("posted") else ""
        parts = []
        if replies:
            parts.append(f"답변 {replies}")
        if comments:
            parts.append(f"댓글 {comments}")
        if posted:
            parts.append(posted)
        activity = " | ".join(parts) if parts else "활동 없음"
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
