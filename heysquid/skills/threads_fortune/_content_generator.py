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

    # 일간별 차이 (2-3개 비교) — 자연스러운 문장으로
    compare_stems = []
    for s in ["갑", "병", "경", "임", "정"]:
        if s != ilgan:
            compare_stems.append(s)
        if len(compare_stems) >= 2:
            break

    def _ilgan_sentence(stem: str, cat: str) -> str:
        t = ILGAN_TRAITS[stem]
        if cat == "연애":
            return f"{stem}목 일간은 {t['연애']}." if stem in ("갑", "을") else f"{stem} 일간은 {t['연애']}."
        return f"{stem} 일간은 {t['약점']}."

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

    # 일간별 비교 — 자연스러운 문장
    draft_lines.append(_ilgan_sentence(ilgan, category))
    for s in compare_stems:
        draft_lines.append(_ilgan_sentence(s, category))

    # 마무리 (15개)
    endings = [
        "나만 이런 건가 싶겠지만, 사주에 다 나와있어.",
        "결국 아는 만큼 대처할 수 있어.",
        "본인 일간 알면 왜 그랬는지 이해돼.",
        "사주 모르고 연애하면 계속 같은 실수 반복해.",
        "알면 달라져. 진짜로.",
        "근데 이거 알고도 똑같이 하는 게 사람이긴 해.",
        "한 번 찾아봐. 소름 돋을 거야.",
        "이 패턴 깨고 싶으면, 일단 내 사주부터 알아야 해.",
        "몰랐으면 계속 반복했을 거야.",
        "그래서 자꾸 그런 사람한테 끌렸던 거야.",
        "사주 알면 자기 연애 패턴이 보여.",
        "이거 진짜 모르면 손해야.",
        "친구한테 물어봐. 아마 맞다고 할 거야.",
        "어쩌면 네가 못 끊는 이유도 여기 있어.",
        "웃긴 게, 본인만 모르고 주변은 다 알아.",
    ]
    ending_idx = _pick(f"{d.isoformat()}:ending:14", len(endings))
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

    # 연프 레퍼런스 풀
    _YEONPRO_REFS = [
        "솔지5", "마인드밍글", "환승연애", "나는솔로",
        "하트시그널", "짝", "연애의참견", "돌싱글즈",
    ]

    # 훅 선택 — 날짜+연도+요일로 seed를 풍부하게 해서 겹침 방지
    hook_seed = f"{d.isoformat()}:{d.year}:{d.weekday()}:yeonpro:hook"
    hook_idx = _pick(hook_seed, len(YEONPRO_HOOKS))
    hook = YEONPRO_HOOKS[hook_idx]

    # 연프 레퍼런스 선택 (날짜별 다르게)
    ref_idx = _pick(f"{d.isoformat()}:yp:ref", len(_YEONPRO_REFS))
    yeonpro_ref = _YEONPRO_REFS[ref_idx]

    # 십성 테마 2개 선택 (대비용) — 소수 곱으로 분산
    day_of_year = d.timetuple().tm_yday
    sipsung_keys = list(SIPSUNG_PATTERNS.keys())
    theme1_idx = _pick(f"{d.isoformat()}:yp:theme1", len(sipsung_keys))
    theme2_idx = _pick(f"{d.isoformat()}:yp:theme2", len(sipsung_keys))
    if theme2_idx == theme1_idx:
        theme2_idx = (theme2_idx + 1) % len(sipsung_keys)
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

    # 마무리 풀 (15개)
    yp_endings = [
        "어떤 타입이 끌리는지 보면 내 사주가 보여.",
        "매번 같은 유형한테 끌리는 이유, 사주에 있어.",
        "네가 픽한 사람이 곧 네 사주 패턴이야.",
        "이상형이 매번 바뀐다고? 사주 보면 일관성 있어.",
        "끌리는 유형엔 이유가 있어.",
        "나도 모르게 고르는 타입, 사주에 다 써있어.",
        "연프 볼 때 내 마음이 가는 사람, 우연이 아니야.",
        "매번 비슷한 사람한테 가는 건 운명이 아니라 패턴이야.",
        "좋아하는 유형이 뚜렷한 사람일수록 사주가 정직해.",
        "이거 보고 나면 연프 다르게 보여.",
        "본인 사주 모르고 연애하는 건 내비 없이 운전하는 거야.",
        "다음에 연프 볼 때 한번 대입해봐.",
        "결국 내가 끌리는 사람이 답이야.",
        "연프가 재밌는 이유, 내 패턴이 보이니까.",
        "사주 알고 나면 왜 그 사람이었는지 이해돼.",
    ]
    ending_idx = _pick(f"{d.isoformat()}:yp:ending:20", len(yp_endings))

    draft_lines = [
        hook,
        "",
        f"{yeonpro_ref} 보면 딱 보이는 두 타입이 있어.",
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
        yp_endings[ending_idx],
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
