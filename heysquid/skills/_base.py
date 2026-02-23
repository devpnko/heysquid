"""heysquid.skills._base — skill auto-discovery + run_skill() interface."""

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class SkillContext:
    """스킬 실행 컨텍스트"""
    triggered_by: str = "scheduler"  # "scheduler" | "manual" | "pm" | "webhook"
    chat_id: int = 0
    args: str = ""
    payload: dict = field(default_factory=dict)   # webhook/API에서 받은 데이터
    callback_url: str = ""                        # 완료 후 콜백 URL (n8n 등)


def _load_skills_config() -> dict:
    """data/skills_config.json 로드 (없으면 빈 dict)"""
    config_path = DATA_DIR / "skills_config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"skills_config.json 로드 실패: {e}")
        return {}


def discover_skills() -> dict[str, dict]:
    """skills/ 하위 폴더 스캔 → SKILL_META가 있는 모듈 자동 수집"""
    skills_dir = Path(__file__).parent
    config = _load_skills_config()
    registry = {}
    for folder in skills_dir.iterdir():
        if not folder.is_dir() or folder.name.startswith("_") or folder.name == "__pycache__":
            continue
        try:
            mod = importlib.import_module(f"heysquid.skills.{folder.name}")
            meta = getattr(mod, "SKILL_META", None)
            if not meta:
                continue

            # config override 적용
            override = config.get(folder.name, {})
            if override:
                meta = {**meta, **override}

            if not meta.get("enabled", True):
                # disabled 스킬도 레지스트리에 등록 (목록 표시용)
                meta["_module"] = mod
                meta["_execute"] = None
                registry[folder.name] = meta
                continue

            meta["_module"] = mod
            meta["_execute"] = getattr(mod, "execute", None)
            registry[folder.name] = meta
        except Exception as e:
            logger.warning(f"Skill {folder.name} 로드 실패: {e}")
    return registry


_registry_cache = None


def get_skill_registry() -> dict[str, dict]:
    """캐시된 스킬 레지스트리 반환"""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = discover_skills()
    return _registry_cache


def reload_skills():
    """스킬 레지스트리 새로고침 (새 스킬 감지)"""
    global _registry_cache
    _registry_cache = None
    return get_skill_registry()


def run_skill(name: str, ctx: SkillContext | None = None) -> dict:
    """스킬을 이름으로 실행. dashboard 상태 업데이트 포함."""
    registry = get_skill_registry()
    meta = registry.get(name)
    if not meta:
        return {"ok": False, "error": f"스킬 '{name}' 없음"}

    if not meta.get("enabled", True):
        return {"ok": False, "error": f"스킬 '{name}' 비활성화됨"}

    execute_fn = meta.get("_execute")
    if not execute_fn:
        return {"ok": False, "error": f"스킬 '{name}': execute() 없음"}

    from heysquid.dashboard import update_skill_status
    update_skill_status(name, 'running')
    try:
        result = execute_fn(**(ctx.__dict__ if ctx else {}))
        update_skill_status(name, 'idle', last_result='success')
        response = {"ok": True, "result": result}
    except Exception as e:
        update_skill_status(name, 'error', last_result='error',
                            last_error=str(e)[:200])
        response = {"ok": False, "error": str(e)}

    # 콜백 URL이 있으면 결과 전송 (n8n 등)
    if ctx and ctx.callback_url:
        _send_callback(ctx.callback_url, name, response)

    return response


def _send_callback(url: str, skill_name: str, result: dict):
    """완료 콜백 전송 (best-effort, 실패해도 무시)."""
    try:
        import requests
        requests.post(url, json={"skill": skill_name, **result}, timeout=10)
    except Exception as e:
        logger.warning(f"Callback 실패 ({url}): {e}")
