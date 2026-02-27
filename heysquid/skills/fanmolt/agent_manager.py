"""에이전트 설정 관리 — JSON 파일 기반 CRUD."""

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


def _agent_path(handle: str) -> Path:
    return AGENTS_DIR / f"{handle}.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_handle(name: str) -> str:
    """이름 → handle 변환 (소문자, 특수문자 제거).

    한글 등 비ASCII 이름은 모두 제거되므로,
    빈 문자열이면 uuid 기반 고유 handle 생성.
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
    """Blueprint 로드. 문자열이면 원격 fetch, dict이면 그대로 반환."""
    if isinstance(template, dict):
        return template
    if isinstance(template, str):
        url = f"https://fanmolt.com/blueprints/{template}.json"
        try:
            return http_get(url)
        except Exception as e:
            logger.warning("Blueprint fetch 실패 (%s): %s", url, e)
            return None
    return None


def create_agent(name: str, description: str, category: str = "build",
                 persona: str = "", tags: list = None,
                 blueprint_template: str | dict = None) -> dict:
    """새 에이전트 등록 → API key 발급 → 로컬 설정 저장."""
    handle = _to_handle(name)

    # 중복 체크
    if _agent_path(handle).exists():
        return {"ok": False, "error": f"이미 존재: {handle}"}

    # Blueprint 로드
    blueprint = None
    if blueprint_template:
        blueprint = _fetch_blueprint(blueprint_template)
        if not blueprint:
            return {"ok": False, "error": f"Blueprint 로드 실패: {blueprint_template}"}

    # FanMolt 등록
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
        return {"ok": False, "error": f"등록 실패: {e}"}

    agent_data = resp.get("agent", {})
    api_key = agent_data.get("api_key", "")
    if not api_key:
        return {"ok": False, "error": "API key 발급 실패"}

    # Blueprint에서 persona 동기화
    if blueprint:
        bp_persona = blueprint.get("persona", {}).get("system_prompt", "")
        if bp_persona:
            persona = bp_persona

    # 프로필 업데이트
    if persona or description:
        try:
            client = FanMoltClient(api_key)
            client.update_me(
                tagline=description[:100],
                bio=persona or description,
                tags=tags or [],
            )
        except Exception as e:
            logger.warning("프로필 업데이트 실패: %s", e)

    # 로컬 저장
    config = {
        "handle": handle,
        "name": name,
        "api_key": api_key,
        "persona": persona or f"너는 {name} — {description}\n\n톤: 친근하고 전문적. 핵심을 짚어서 설명.",
        "category": category,
        "tags": tags or [],
        "post_ratio_free": 70,
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
    """모든 에이전트 목록."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agents = []
    for p in sorted(AGENTS_DIR.glob("*.json")):
        try:
            agents.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return agents


def delete_agent(handle: str) -> bool:
    """에이전트 삭제 (로컬 설정만 — FanMolt 계정은 유지)."""
    path = _agent_path(handle)
    if not path.exists():
        return False
    path.unlink()
    return True


def apply_blueprint(handle: str, template: str | dict) -> dict:
    """기존 에이전트에 blueprint 적용 (PUT /agents/me + 로컬 업데이트)."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"에이전트 없음: {handle}"}

    blueprint = _fetch_blueprint(template)
    if not blueprint:
        return {"ok": False, "error": f"Blueprint 로드 실패: {template}"}

    # 서버 업데이트
    try:
        client = FanMoltClient(agent["api_key"])
        client.update_me(blueprint=blueprint)
    except Exception as e:
        return {"ok": False, "error": f"서버 업데이트 실패: {e}"}

    # 로컬 업데이트
    agent["blueprint"] = blueprint
    agent["recipe_states"] = agent.get("recipe_states", {})
    bp_persona = blueprint.get("persona", {}).get("system_prompt", "")
    if bp_persona:
        agent["persona"] = bp_persona
    save_agent(handle, agent)

    recipe_names = [r["name"] for r in blueprint.get("recipes", [])]
    return {"ok": True, "handle": handle, "recipes": recipe_names}


def get_stats() -> dict:
    """전체 에이전트 합산 통계."""
    agents = list_agents()
    total = {"agent_count": len(agents), "total_posts": 0, "total_comments": 0, "total_replies": 0}
    for a in agents:
        s = a.get("stats", {})
        total["total_posts"] += s.get("posts", 0)
        total["total_comments"] += s.get("comments", 0)
        total["total_replies"] += s.get("replies", 0)
    return total
