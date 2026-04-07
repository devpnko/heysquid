"""threads_fortune._engine -- day-pillar calculation + zodiac relation analysis.

Core saju engine ported from dokkeabi-v2 pillar-calculator.ts.
All functions are pure / deterministic (no randomness, no AI calls).
"""

from __future__ import annotations

from datetime import date, datetime

# -- constants ---------------------------------------------------------------

HEAVENLY_STEMS = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]
STEMS_HANJA = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

EARTHLY_BRANCHES = ["자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해"]
BRANCHES_HANJA = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# Epoch: 1899-12-22 = 甲子日 (갑자일)
# 검증: BTS 7명 전원 + 공인 만세력 기준 확인 (2026-03-30)
_EPOCH = date(1899, 12, 22)

# Stem -> five-element key
STEM_ELEMENT = {
    "갑": "목", "을": "목",
    "병": "화", "정": "화",
    "무": "토", "기": "토",
    "경": "금", "신": "금",
    "임": "수", "계": "수",
}

# Zodiac emoji + representative birth years (2-digit, dkbsqd format order)
ZODIAC_INFO: list[dict] = [
    {"branch": "자", "emoji": "🐭", "years": [96, 84]},
    {"branch": "축", "emoji": "🐂", "years": [97, 85]},
    {"branch": "인", "emoji": "🐯", "years": [98, 86]},
    {"branch": "묘", "emoji": "🐰", "years": [99, 87]},
    {"branch": "진", "emoji": "🐉", "years": [0, 88]},
    {"branch": "사", "emoji": "🐍", "years": [1, 89]},
    {"branch": "오", "emoji": "🐴", "years": [2, 90]},
    {"branch": "미", "emoji": "🐑", "years": [3, 91]},
    {"branch": "신", "emoji": "🐵", "years": [4, 92]},
    {"branch": "유", "emoji": "🐔", "years": [5, 93]},
    {"branch": "술", "emoji": "🐕", "years": [6, 94]},
    {"branch": "해", "emoji": "🐷", "years": [95, 83]},
]

# -- relation tables ---------------------------------------------------------

_CHUNG: set[frozenset] = {
    frozenset(("자", "오")), frozenset(("축", "미")), frozenset(("인", "신")),
    frozenset(("묘", "유")), frozenset(("진", "술")), frozenset(("사", "해")),
}

_PA: set[frozenset] = {
    frozenset(("자", "유")), frozenset(("축", "진")), frozenset(("인", "해")),
    frozenset(("묘", "오")), frozenset(("사", "신")), frozenset(("미", "술")),
}

_HAE: set[frozenset] = {
    frozenset(("자", "미")), frozenset(("축", "오")), frozenset(("인", "사")),
    frozenset(("묘", "진")), frozenset(("신", "해")), frozenset(("유", "술")),
}

# 형(刑) — stored as (A, B) pairs; self-punishment uses same branch twice
_HYUNG_PAIRS: set[frozenset] = {
    # 삼형 인신사
    frozenset(("인", "신")), frozenset(("인", "사")), frozenset(("신", "사")),
    # 삼형 축술미
    frozenset(("축", "술")), frozenset(("축", "미")), frozenset(("술", "미")),
    # 무례지형
    frozenset(("자", "묘")),
}
_HYUNG_SELF = {"진", "오", "유", "해"}  # 자형

_SAMHAP_GROUPS: list[set[str]] = [
    {"인", "오", "술"},  # 화국
    {"신", "자", "진"},  # 수국
    {"해", "묘", "미"},  # 목국
    {"사", "유", "축"},  # 금국
]

_YUKHAP: set[frozenset] = {
    frozenset(("자", "축")), frozenset(("인", "해")), frozenset(("묘", "술")),
    frozenset(("진", "유")), frozenset(("사", "신")), frozenset(("오", "미")),
}

# -- public API --------------------------------------------------------------


def get_day_pillar(d: date | datetime | None = None) -> dict:
    """Return the day pillar (ilju) for *d* (defaults to today).

    Returns:
        {"gan": "갑", "ji": "자", "gan_hanja": "甲", "ji_hanja": "子",
         "element": "목", "sexagenary_index": 0}
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()

    delta = (d - _EPOCH).days
    idx60 = delta % 60
    stem_idx = delta % 10
    branch_idx = delta % 12

    return {
        "gan": HEAVENLY_STEMS[stem_idx],
        "ji": EARTHLY_BRANCHES[branch_idx],
        "gan_hanja": STEMS_HANJA[stem_idx],
        "ji_hanja": BRANCHES_HANJA[branch_idx],
        "element": STEM_ELEMENT[HEAVENLY_STEMS[stem_idx]],
        "sexagenary_index": idx60,
    }


def _find_relations(day_ji: str, zodiac_branch: str) -> list[str]:
    """Return all relation names between *day_ji* and *zodiac_branch*."""
    pair = frozenset((day_ji, zodiac_branch))
    rels: list[str] = []

    if pair in _CHUNG:
        rels.append("충")
    if pair in _YUKHAP:
        rels.append("육합")
    for group in _SAMHAP_GROUPS:
        if day_ji in group and zodiac_branch in group:
            rels.append("삼합")
            break
    if pair in _HYUNG_PAIRS:
        rels.append("형")
    if day_ji == zodiac_branch and day_ji in _HYUNG_SELF:
        rels.append("형")
    if pair in _HAE:
        rels.append("해")
    if pair in _PA:
        rels.append("파")

    return rels


# Relation -> short advice hint (Korean)
_RELATION_HINTS: dict[str, str] = {
    "충": "갈등/변화 주의",
    "삼합": "시너지/좋은 흐름",
    "육합": "조화/협력",
    "형": "마찰/스트레스 주의",
    "해": "방해/오해 주의",
    "파": "깨짐/계획 틀어질 수 있음",
}


def analyze_zodiac_relations(day_ji: str) -> list[dict]:
    """Analyze today's day-branch against all 12 zodiac signs.

    Returns a list of 12 dicts (one per zodiac, in ZODIAC_INFO order):
        {"branch": "자", "emoji": "🐭", "years": [96, 84],
         "relations": ["충"], "advice_hint": "갈등/변화 주의"}
    """
    results: list[dict] = []
    for info in ZODIAC_INFO:
        rels = _find_relations(day_ji, info["branch"])
        if rels:
            hint = " / ".join(_RELATION_HINTS.get(r, "") for r in rels)
        else:
            hint = "평온/자기 페이스"
        results.append({
            "branch": info["branch"],
            "emoji": info["emoji"],
            "years": info["years"],
            "relations": rels if rels else ["없음"],
            "advice_hint": hint,
        })
    return results
