"""Backward-compat wrapper — 기존 `python -m heysquid.briefing` 호출 지원."""

from .skills import run_skill, SkillContext


def main():
    ctx = SkillContext(triggered_by="manual")
    result = run_skill("briefing", ctx)
    if not result["ok"]:
        print(f"Briefing 실패: {result['error']}")


if __name__ == "__main__":
    main()
