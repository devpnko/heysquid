"""threads_fortune._content_generator — 14:00/20:00 사주 콘텐츠 초안 생성.

만세력 근거 + 소재 뱅크 → 자연스러운 사주 분석 글 초안.
주간 배치로 뽑고 검수 후 큐에 등록하는 용도.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from ._engine import get_day_pillar, HEAVENLY_STEMS, STEM_ELEMENT
from ._content_bank import (
    SIPSUNG_PATTERNS,
    ILJU_ADJECTIVES,
    ILGAN_TRAITS,
    YEONPRO_HOOKS,
    MBTI_SAJU_HOOKS,
    CTA_PATTERNS,
)

# ── 일간→십성 계산 (간략화) ──────────────────────────────────

# 일간이 주어졌을 때, 오늘의 천간과의 관계 = 십성
# 여기서는 매일 달라지는 "오늘의 십성 테마"를 뽑는 용도

_SIPSUNG_ORDER = ["비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "인성"]

def _get_ten_god(day_stem: str, target_stem: str) -> str:
    """일간과 대상 천간의 십성 관계."""
    day_idx = HEAVENLY_STEMS.index(day_stem)
    target_idx = HEAVENLY_STEMS.index(target_stem)
    diff = (target_idx - day_idx) % 10
    return _SIPSUNG_ORDER[diff]


# ── 해시 기반 인덱스 선택 ────────────────────────────────────

def _pick(seed: str, pool_size: int) -> int:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return h % pool_size


# ── 14:00 사주 심리 분석 글 생성 ─────────────────────────────

def generate_saju_psychology(d: date | None = None) -> dict:
    """14:00용 사주 심리/연애 분석 글 초안.

    Returns:
        {
            "date": "2026-03-25",
            "time": "14:00",
            "type": "사주심리",
            "pillar": {...},
            "sipsung_theme": "비견",
            "draft": "초안 텍스트",
            "cta": "CTA 텍스트",
            "notes": "검수 포인트",
        }
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()

    pillar = get_day_pillar(d)
    ilju = pillar["gan"] + pillar["ji"]
    ilgan = pillar["gan"]
    element = pillar["element"]

    # 오늘의 십성 테마 결정 (날짜 기반 로테이션)
    day_of_year = d.timetuple().tm_yday
    sipsung_keys = list(SIPSUNG_PATTERNS.keys())
    theme_idx = day_of_year % len(sipsung_keys)
    theme = sipsung_keys[theme_idx]
    pattern = SIPSUNG_PATTERNS[theme]

    # 카테고리 로테이션: 연애 → 일상 → 직장 → 연애...
    categories = ["연애", "일상"]
    if "직장" in pattern:
        categories.append("직장")
    cat_idx = day_of_year % len(categories)
    category = categories[cat_idx]

    # 소재 선택
    pool = pattern[category]
    hook_idx = _pick(f"{d.isoformat()}:hook:{theme}", len(pool))
    hook = pool[hook_idx]

    # 두 번째 문장
    body_idx = _pick(f"{d.isoformat()}:body:{theme}", len(pool))
    if body_idx == hook_idx:
        body_idx = (body_idx + 1) % len(pool)
    body_line = pool[body_idx]

    # 일간 특성 연결
    trait = ILGAN_TRAITS[ilgan]
    ilju_adj = ILJU_ADJECTIVES.get(ilju, "")

    # 일간별 차이 (2-3개 비교)
    compare_stems = []
    for s in ["갑", "병", "경", "임", "정"]:
        if s != ilgan:
            compare_stems.append(s)
        if len(compare_stems) >= 2:
            break

    comparisons = []
    for s in compare_stems:
        t = ILGAN_TRAITS[s]
        comparisons.append(f"{s}({t['성격']}): {t[category] if category == '연애' else t['키워드']}")

    # 초안 조합
    draft_lines = [
        hook,
        "",
        f"사주에서 이걸 '{theme}({pattern['한줄']})'이라고 해.",
        body_line,
        "",
        f"특히 오늘 같은 {ilju}({ilju_adj}) 일주에는 이런 기운이 더 강해져.",
        "",
    ]

    # 일간별 비교
    draft_lines.append(f"{ilgan}({trait['성격']}) 일간: {trait[category] if category == '연애' else trait['약점']}")
    for comp in comparisons:
        draft_lines.append(comp)

    # 마무리
    endings = [
        "나만 이런 건가 싶겠지만, 사주에 다 나와있어.",
        "결국 아는 만큼 대처할 수 있어.",
        "본인 일간 알면 왜 그랬는지 이해돼.",
        "사주 모르고 연애하면 계속 같은 실수 반복해.",
        "알면 달라져. 진짜로.",
    ]
    ending_idx = _pick(f"{d.isoformat()}:ending", len(endings))
    draft_lines.append("")
    draft_lines.append(endings[ending_idx])

    draft = "\n".join(draft_lines)

    # CTA 선택
    cta = CTA_PATTERNS.get(category == "연애" and "연애운" or "사주심리", CTA_PATTERNS["기본"])

    return {
        "date": d.isoformat(),
        "time": "14:00",
        "type": "사주심리",
        "category": category,
        "pillar": pillar,
        "sipsung_theme": theme,
        "draft": draft,
        "cta": cta,
        "notes": f"십성 테마: {theme}, 카테고리: {category}, 일주: {ilju}({ilju_adj}). 문장 자연스러운지 검수 필요.",
    }


# ── 20:00 연프 사주 분석 글 생성 ─────────────────────────────

def generate_yeonpro_analysis(d: date | None = None) -> dict:
    """20:00용 연프(연애 프로그램) 사주 분석 글 초안.

    솔로지옥/마인드밍글 스타일로 캐릭터 유형을 사주로 분석.
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()

    pillar = get_day_pillar(d)
    ilju = pillar["gan"] + pillar["ji"]
    ilgan = pillar["gan"]
    element = pillar["element"]

    # 훅 선택
    hook_idx = _pick(f"{d.isoformat()}:yeonpro:hook", len(YEONPRO_HOOKS))
    hook = YEONPRO_HOOKS[hook_idx]

    # 십성 테마 2개 선택 (대비용)
    day_of_year = d.timetuple().tm_yday
    sipsung_keys = list(SIPSUNG_PATTERNS.keys())
    theme1_idx = (day_of_year * 3) % len(sipsung_keys)
    theme2_idx = (day_of_year * 3 + 5) % len(sipsung_keys)
    theme1 = sipsung_keys[theme1_idx]
    theme2 = sipsung_keys[theme2_idx]

    p1 = SIPSUNG_PATTERNS[theme1]
    p2 = SIPSUNG_PATTERNS[theme2]

    # 연애 소재에서 뽑기
    p1_lines = p1.get("연애", p1.get("일상", []))
    p2_lines = p2.get("연애", p2.get("일상", []))

    line1_idx = _pick(f"{d.isoformat()}:yp:l1", len(p1_lines))
    line2_idx = _pick(f"{d.isoformat()}:yp:l2", len(p2_lines))

    # 일간 특성
    trait = ILGAN_TRAITS[ilgan]
    ilju_adj = ILJU_ADJECTIVES.get(ilju, "")

    draft_lines = [
        hook,
        "",
        f"{theme1}({p1['한줄']}) 타입:",
        p1_lines[line1_idx],
        "",
        f"{theme2}({p2['한줄']}) 타입:",
        p2_lines[line2_idx],
        "",
        f"오늘 같은 {ilju} 일주에는",
        f"{theme1} 기운인 사람이 더 솔직해지고",
        f"{theme2} 기운인 사람은 오히려 조심스러워져.",
        "",
        "어떤 타입이 끌리는지 보면",
        "네 사주 패턴이 보여.",
    ]

    draft = "\n".join(draft_lines)
    cta = CTA_PATTERNS["연애운"]

    return {
        "date": d.isoformat(),
        "time": "20:00",
        "type": "연프분석",
        "pillar": pillar,
        "themes": [theme1, theme2],
        "draft": draft,
        "cta": cta,
        "notes": f"십성 대비: {theme1} vs {theme2}, 일주: {ilju}({ilju_adj}). 연프 레퍼런스 추가하면 좋음.",
    }


# ── 주간 배치 생성 ───────────────────────────────────────────

def generate_weekly_drafts(start: date | None = None) -> list[dict]:
    """이번 주 14:00/20:00 초안 전부 생성.

    Returns: list of dicts (날짜별 14:00 + 20:00 = 2개씩, 주간 10~14개)
    """
    if start is None:
        start = date.today()

    # 오늘부터 일요일까지
    days_until_sunday = 6 - start.weekday()
    if days_until_sunday <= 0:
        days_until_sunday = 7

    drafts = []
    for i in range(days_until_sunday + 1):
        d = start + timedelta(days=i)
        drafts.append(generate_saju_psychology(d))
        drafts.append(generate_yeonpro_analysis(d))

    return drafts
