"""Backward-compat wrapper — supports legacy `python -m heysquid.briefing` invocation."""

from .automations import run_automation
from .core.plugin_loader import PluginContext


def main():
    ctx = PluginContext(triggered_by="manual")
    result = run_automation("briefing", ctx)
    if not result["ok"]:
        print(f"Briefing failed: {result['error']}")


if __name__ == "__main__":
    main()
