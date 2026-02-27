"""heysquid.core.scheduler — automation scheduler.

Called every minute via launchd:
1. Run schedule automations matching the current time (HH:MM)
2. Run interval automations on every invocation (e.g., scheduled thread posts)

Usage:
    python -m heysquid.core.scheduler
"""

import logging
from datetime import datetime

from heysquid.automations import get_automation_registry, run_automation
from heysquid.core.plugin_loader import PluginContext

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_scheduled_automations():
    """Run schedule automations matching the current time"""
    from heysquid.dashboard import sync_automations

    now_hm = datetime.now().strftime("%H:%M")

    # Sync metadata (called every minute, so always up to date)
    try:
        sync_automations()
    except Exception as e:
        logger.warning(f"sync_automations failed: {e}")

    try:
        from heysquid.dashboard import sync_workspaces
        sync_workspaces()
    except Exception as e:
        logger.warning(f"sync_workspaces failed: {e}")

    registry = get_automation_registry()

    if not registry:
        return

    for name, meta in registry.items():
        trigger = meta.get("trigger")

        # 1. schedule trigger: exact HH:MM matching
        if trigger == "schedule":
            if meta.get("schedule") != now_hm:
                continue
            logger.info(f"Running automation {name} (schedule={now_hm})")

        # 2. interval trigger: run on every invocation
        elif trigger == "interval":
            pass  # Always run

        else:
            continue

        ctx = PluginContext(triggered_by="scheduler")
        try:
            result = run_automation(name, ctx)
            if result["ok"]:
                logger.info(f"Automation {name} completed")
            else:
                logger.error(f"Automation {name} failed: {result['error']}")
        except Exception as e:
            logger.error(f"Automation {name} exception: {e}")


if __name__ == "__main__":
    run_scheduled_automations()
