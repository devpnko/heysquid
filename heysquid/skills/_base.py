"""heysquid.skills._base — skill auto-discovery + run_skill() interface.

Delegates to core.plugin_loader. Preserves existing API.
"""

from pathlib import Path

from ..core.plugin_loader import (  # noqa: F401
    discover_plugins, run_plugin, PluginContext as SkillContext,
)

_DIR = Path(__file__).parent


def discover_skills() -> dict[str, dict]:
    """Scan skills/ subfolders and auto-collect modules with SKILL_META."""
    return discover_plugins("heysquid.skills", _DIR)


_registry_cache = None


def get_skill_registry() -> dict[str, dict]:
    """Return cached skill registry."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = discover_skills()
    return _registry_cache


def reload_skills():
    """Refresh skill registry (detect new skills)."""
    global _registry_cache
    _registry_cache = None
    return get_skill_registry()


def run_skill(name: str, ctx: SkillContext | None = None) -> dict:
    """Run a skill by name. Includes dashboard state updates."""
    registry = get_skill_registry()
    return run_plugin("heysquid.skills", name, ctx, registry=registry)
