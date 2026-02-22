"""heysquid.core.scheduler — 스킬 스케줄러.

launchd로 1분마다 호출되어:
1. 현재 시각(HH:MM)에 매칭되는 schedule 스킬 실행
2. 매 호출마다 interval 스킬 실행 (예: 스레드 예약 게시)

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
        trigger = meta.get("trigger")

        # 1. schedule 트리거: 정확한 HH:MM 매칭
        if trigger == "schedule":
            if meta.get("schedule") != now_hm:
                continue
            logger.info(f"Skill {name} 실행 (schedule={now_hm})")

        # 2. interval 트리거: 매 호출마다 실행
        elif trigger == "interval":
            pass  # 항상 실행

        else:
            continue

        ctx = SkillContext(triggered_by="scheduler")
        try:
            result = run_skill(name, ctx)
            if result["ok"]:
                logger.info(f"Skill {name} 완료")
            else:
                logger.error(f"Skill {name} 실행 실패: {result['error']}")
        except Exception as e:
            logger.error(f"Skill {name} 예외: {e}")


if __name__ == "__main__":
    run_scheduled_skills()
