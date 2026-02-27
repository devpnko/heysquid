"""heysquid.automations — automated recurring plugins (schedule/interval)."""

from pathlib import Path

from ..core.plugin_loader import discover_plugins, run_plugin, PluginContext

_DIR = Path(__file__).parent


def discover_automations() -> dict[str, dict]:
    """Scan automations/ subfolders and auto-collect modules with SKILL_META."""
    return discover_plugins("heysquid.automations", _DIR)


_registry_cache = None


def get_automation_registry() -> dict[str, dict]:
    """Return cached automation registry."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = discover_automations()
    return _registry_cache


def reload_automations():
    """Refresh automation registry."""
    global _registry_cache
    _registry_cache = None
    return get_automation_registry()


def run_automation(name: str, ctx: PluginContext | None = None) -> dict:
    """Run an automation by name."""
    registry = get_automation_registry()
    return run_plugin("heysquid.automations", name, ctx, registry=registry)
