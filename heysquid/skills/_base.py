"""heysquid.skills._base — skill auto-discovery + run_skill() interface.

core.plugin_loader에 위임. 기존 API 유지.
"""

from pathlib import Path

from ..core.plugin_loader import (  # noqa: F401
    discover_plugins, run_plugin, PluginContext as SkillContext,
)

_DIR = Path(__file__).parent


def discover_skills() -> dict[str, dict]:
    """skills/ 하위 폴더 스캔 → SKILL_META가 있는 모듈 자동 수집."""
    return discover_plugins("heysquid.skills", _DIR)


_registry_cache = None


def get_skill_registry() -> dict[str, dict]:
    """캐시된 스킬 레지스트리 반환."""
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = discover_skills()
    return _registry_cache


def reload_skills():
    """스킬 레지스트리 새로고침 (새 스킬 감지)."""
    global _registry_cache
    _registry_cache = None
    return get_skill_registry()


def run_skill(name: str, ctx: SkillContext | None = None) -> dict:
    """스킬을 이름으로 실행. dashboard 상태 업데이트 포함."""
    registry = get_skill_registry()
    return run_plugin("heysquid.skills", name, ctx, registry=registry)
