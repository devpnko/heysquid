"""heysquid.core.plugin_loader — shared plugin discovery + runner.

Common engine used by both skills/ and automations/ packages.
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
    """Plugin execution context"""
    triggered_by: str = "scheduler"  # "scheduler" | "manual" | "pm" | "webhook"
    chat_id: int = 0
    args: str = ""
    payload: dict = field(default_factory=dict)
    callback_url: str = ""


def _load_plugins_config() -> dict:
    """Load data/skills_config.json (empty dict if not found)"""
    config_path = DATA_DIR / "skills_config.json"
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load skills_config.json: {e}")
        return {}


def discover_plugins(package_name: str, package_dir: Path) -> dict[str, dict]:
    """Scan the given package directory -> auto-collect modules with SKILL_META."""
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

            # Apply config override
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
            logger.warning(f"Failed to load plugin {folder.name}: {e}")
    return registry


def run_plugin(package_name: str, name: str, ctx: PluginContext | None = None,
               registry: dict = None) -> dict:
    """Run plugin execute() + update dashboard status."""
    if registry is None:
        from pathlib import Path as _P
        pkg = importlib.import_module(package_name)
        pkg_dir = _P(pkg.__file__).parent
        registry = discover_plugins(package_name, pkg_dir)

    meta = registry.get(name)
    if not meta:
        return {"ok": False, "error": f"Plugin '{name}' not found"}

    if not meta.get("enabled", True):
        return {"ok": False, "error": f"Plugin '{name}' is disabled"}

    execute_fn = meta.get("_execute")
    if not execute_fn:
        return {"ok": False, "error": f"Plugin '{name}': no execute() function"}

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

    # Send result if callback URL is provided
    if ctx and ctx.callback_url:
        _send_callback(ctx.callback_url, name, response)

    return response


def _send_callback(url: str, plugin_name: str, result: dict):
    """Send completion callback (best-effort, failures ignored)."""
    try:
        import requests
        requests.post(url, json={"plugin": plugin_name, **result}, timeout=10)
    except Exception as e:
        logger.warning(f"Callback failed ({url}): {e}")
