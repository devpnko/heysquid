"""heysquid.core.scheduler — schedule 트리거 스킬을 시간 기반으로 실행.

launchd로 1분마다 호출되어, 현재 시각(HH:MM)에 매칭되는 스킬을 실행한다.

Usage:
    python -m heysquid.core.scheduler
"""

import logging
from datetime import datetime

from heysquid.skills._base import get_skill_registry, run_skill, SkillContext

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_scheduled_skills():
    """현재 시각에 매칭되는 schedule 스킬 실행"""
    from heysquid.dashboard import sync_skills

    now_hm = datetime.now().strftime("%H:%M")

    # 메타 동기화 (1분마다 호출되므로 항상 최신 유지)
    try:
        sync_skills()
    except Exception as e:
        logger.warning(f"sync_skills 실패: {e}")

    registry = get_skill_registry()

    if not registry:
        return

    for name, meta in registry.items():
        if meta.get("trigger") != "schedule":
            continue
        if meta.get("schedule") != now_hm:
            continue

        logger.info(f"Skill {name} 실행 (schedule={now_hm})")
        ctx = SkillContext(triggered_by="scheduler")
        result = run_skill(name, ctx)
        if result["ok"]:
            logger.info(f"Skill {name} 완료")
        else:
            logger.error(f"Skill {name} 실행 실패: {result['error']}")


if __name__ == "__main__":
    run_scheduled_skills()
