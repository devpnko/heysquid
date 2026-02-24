"""heysquid.core.plugin_loader — 공유 plugin discovery + runner.

skills/ 와 automations/ 패키지가 공통으로 사용하는 엔진.
"""

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass
class PluginContext:
    """플러그인 실행 컨텍스트"""
    triggered_by: str = "scheduler"  # "scheduler" | "manual" | "pm" | "webhook"
    chat_id: int = 0
    args: str = ""
    payload: dict = field(default_factory=dict)
    callback_url: str = ""


def _load_plugins_config() -> dict:
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


def discover_plugins(package_name: str, package_dir: Path) -> dict[str, dict]:
    """지정된 패키지 디렉토리 스캔 → SKILL_META가 있는 모듈 자동 수집."""
    config = _load_plugins_config()
    registry: dict[str, dict] = {}
    for folder in package_dir.iterdir():
        if not folder.is_dir() or folder.name.startswith("_") or folder.name == "__pycache__":
            continue
        try:
            mod = importlib.import_module(f"{package_name}.{folder.name}")
            meta = getattr(mod, "SKILL_META", None)
            if not meta:
                continue

            # config override 적용
            override = config.get(folder.name, {})
            if override:
                meta = {**meta, **override}

            if not meta.get("enabled", True):
                meta["_module"] = mod
                meta["_execute"] = None
                registry[folder.name] = meta
                continue

            meta["_module"] = mod
            meta["_execute"] = getattr(mod, "execute", None)
            registry[folder.name] = meta
        except Exception as e:
            logger.warning(f"Plugin {folder.name} 로드 실패: {e}")
    return registry


def run_plugin(package_name: str, name: str, ctx: PluginContext | None = None,
               registry: dict = None) -> dict:
    """플러그인 execute() 실행 + dashboard 상태 업데이트."""
    if registry is None:
        from pathlib import Path as _P
        pkg = importlib.import_module(package_name)
        pkg_dir = _P(pkg.__file__).parent
        registry = discover_plugins(package_name, pkg_dir)

    meta = registry.get(name)
    if not meta:
        return {"ok": False, "error": f"플러그인 '{name}' 없음"}

    if not meta.get("enabled", True):
        return {"ok": False, "error": f"플러그인 '{name}' 비활성화됨"}

    execute_fn = meta.get("_execute")
    if not execute_fn:
        return {"ok": False, "error": f"플러그인 '{name}': execute() 없음"}

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

    # 콜백 URL이 있으면 결과 전송
    if ctx and ctx.callback_url:
        _send_callback(ctx.callback_url, name, response)

    return response


def _send_callback(url: str, plugin_name: str, result: dict):
    """완료 콜백 전송 (best-effort, 실패해도 무시)."""
    try:
        import requests
        requests.post(url, json={"plugin": plugin_name, **result}, timeout=10)
    except Exception as e:
        logger.warning(f"Callback 실패 ({url}): {e}")
