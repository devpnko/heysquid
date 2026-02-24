"""Backward-compat wrapper — 기존 `python -m heysquid.briefing` 호출 지원."""

from .automations import run_automation
from .core.plugin_loader import PluginContext


def main():
    ctx = PluginContext(triggered_by="manual")
    result = run_automation("briefing", ctx)
    if not result["ok"]:
        print(f"Briefing 실패: {result['error']}")


if __name__ == "__main__":
    main()
