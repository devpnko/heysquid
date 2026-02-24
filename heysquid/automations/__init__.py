"""heysquid.automations — 자동 반복 플러그인 (schedule/interval)."""

from pathlib import Path

from ..core.plugin_loader import discover_plugins, run_plugin, PluginContext

_DIR = Path(__file__).parent


def discover_automations() -> dict[str, dict]:
    """automations/ 하위 폴더 스캔 → SKILL_META가 있는 모듈 자동 수집."""
    return discover_plugins("heysquid.automations", _DIR)


_registry_cache = None


def get_automation_registry() -> dict[str, dict]:
    """캐시된 automation 레지스트리 반환."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = discover_automations()
    return _registry_cache


def reload_automations():
    """automation 레지스트리 새로고침."""
    global _registry_cache
    _registry_cache = None
    return get_automation_registry()


def run_automation(name: str, ctx: PluginContext | None = None) -> dict:
    """automation을 이름으로 실행."""
    registry = get_automation_registry()
    return run_plugin("heysquid.automations", name, ctx, registry=registry)
