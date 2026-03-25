"""threads_fortune._content_generator — 14:00/20:00 사주 콘텐츠 생성.

전면 리팩터링: 템플릿 조합 → 브리프 생성 + AI 에세이 작성.

흐름:
1. 만세력 근거 + 십성 테마 + 훅 공식 → "브리프" 생성
2. 브리프를 AI(Claude)에게 주고 에세이형 글 작성
3. 검수 후 큐 등록
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
    YEONPRO_CAST,
    CTA_PATTERNS,
)

_SIPSUNG_ORDER = ["비견", "겁재", "식신", "상관", "편재", "정재", "편관", "정관", "편인", "인성"]

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]


def _pick(seed: str, pool_size: int) -> int:
    h = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return h % pool_size


# ── dkbsqd 훅 공식 (context.md 기반, 사주 계정 변환) ─────────

HOOK_FORMULAS = {
    "공감상황": {
        "설명": "누구나 겪는 일상 상황을 첫 줄에. 사주 용어 절대 안 씀.",
        "예시": [
            "분명 생각은 나는데, 먼저 연락은 못 하겠고.",
            "일요일 저녁에 문득 생각나는 사람 있지.",
            "좋아하는데 티 안 내는 사람, 본인만 모르는 거야.",
            "맨날 같은 유형한테 끌리는 거 나만 그래?",
            "헤어지고 나서야 그 사람 진심이었다는 걸 알아.",
            "연락 올까봐 폰 확인하는 거, 그게 이미 답이야.",
            "좋아하면서 밀어내는 사람, 주변에 꼭 한 명 있지.",
            "썸 타다 흐지부지 되는 이유, 매번 비슷하지 않아?",
            "상대가 나한테 관심 있는 건지 아닌 건지 모르겠는 그 상태.",
            "잠들기 전에 떠오르는 그 사람, 그냥 넘기면 안 돼.",
            "혼자가 편하다면서 외로운 건 뭐야.",
            "고백 타이밍 계속 미루다가 놓치는 사람.",
            "만나면 재밌는데 연락은 안 하는 그 사이.",
            "친구라고 했는데 질투나면 그건 친구가 아닌 거야.",
            "마음에 드는 사람 앞에서 오히려 말이 줄어드는 거.",
        ],
    },
    "역설": {
        "설명": "상식과 반대되는 주장. 15자 이내.",
        "예시": [
            "연락 잘하는 사람이 사실 제일 외로워.",
            "다정한 사람이 이별 뒤에 제일 무서워.",
            "잘 맞는 사람이 오히려 오래 못 가.",
            "첫눈에 반한 사람은 대부분 안 맞아.",
            "많이 좋아하는 쪽이 사실 더 유리해.",
            "집착 심한 사람이 정 떨어지면 제일 빨라.",
            "말 안 하는 사람이 제일 많이 생각해.",
            "밀당 잘하는 사람이 외로움 제일 많이 타.",
        ],
    },
    "시간감정": {
        "설명": "특정 시간/요일 + 감정. 공감 극대화.",
        "예시": [
            "월요일 아침, 출근길에 갑자기 떠오르는 얼굴이 있어?",
            "금요일 밤에 연락 오는 사람, 그 사람 마음 읽어봐.",
            "비 오는 날 유독 생각나는 사람 있지.",
            "새벽 2시에 보내려다 지운 톡, 누구한테였어?",
            "퇴근길에 갑자기 허전한 그 기분, 이유가 있어.",
            "주말 아침에 늦잠 자면서 떠오르는 사람.",
            "수요일쯤 되면 괜히 만나고 싶어지는 그 사람.",
        ],
    },
    "양자택일": {
        "설명": "두 가지 중 선택. 댓글 유도 효과 최고.",
        "예시": [
            "먼저 연락하는 타입 vs 기다리는 타입.",
            "좋아하면 티 내는 사람 vs 숨기는 사람.",
            "빠르게 빠지는 사람 vs 천천히 스며드는 사람.",
            "이별 후 바로 정리하는 사람 vs 오래 끌고 가는 사람.",
            "말로 표현하는 사람 vs 행동으로 보여주는 사람.",
            "연락 먼저 하는 사람 vs 연락 올 때까지 버티는 사람.",
        ],
    },
    "연프": {
        "설명": "연애 프로그램 장면/캐릭터 언급. 시의성 중요.",
        "예시": [
            "솔지5 보면서 제일 공감됐던 사람 있지?",
            "마인드밍글에서 마음 바뀌는 사람, 이유가 있어.",
            "연프에서 말 잘하는 사람이 이기는 게 아니더라.",
            "솔지5에서 조용히 마음 여는 사람들 있잖아.",
            "환승연애 보면 왜 다시 만나는지 이해 안 되지?",
            "나는솔로에서 매번 같은 유형 고르는 사람, 사주 봐.",
            "연프에서 제일 오래가는 커플의 공통점.",
            "하트시그널에서 눈빛만으로 다 아는 사람.",
        ],
    },
}

# ── AI 에세이 작성용 시스템 프롬프트 ─────────────────────────

ESSAY_SYSTEM_PROMPT = """너는 dkbsqd.official 스레드 계정의 글쓴이야. 사주 전문가 '도화'의 톤으로 글을 써.

## 글쓰기 규칙

### 톤
- 친구한테 카톡하듯 자연스러운 반말
- 사주를 어렵지 않게, 일상 언어로 풀어서 설명
- 훈계/설교 절대 금지. 독자와 동등하게 대화
- "여러분~", "지금 바로~" 같은 마케팅 톤 절대 금지

### 구조 (전에 잘 된 글 패턴)
1. **훅** — 첫 줄에서 스크롤 멈추게. 사주 용어 쓰지 마. 일상 상황/감정으로.
2. **사주 연결** — "사주에서 이걸 ~라고 해" 식으로 자연스럽게 전환
3. **깊은 분석** — 십성/일간별로 구체적 차이 설명. 최소 3가지 타입 비교.
4. **마무리** — 여운/공감/질문으로. 매번 다르게.

### 형식
- 한 줄에 하나의 생각. 줄바꿈 자주
- 문단 2-3줄씩 짧게
- 전체 200-400자 (스레드 피드에 잘 보이는 길이)
- 해시태그 1-2개만 마지막에
- 이모지 0-1개 (감정 포인트에만)

### 사주 설명 방법
- 십성: 한자 병기 OK (비견(比肩))
- 일간: "경금(庚金)이거나 갑목(甲木)인 사람" 식으로 구체적
- 오행: 일상적 비유 사용 ("곧은 나무", "태양", "바다")
- **반드시 3가지 이상 타입 비교** — 독자가 "나는 어떤 타입이지?" 생각하게

### 절대 하면 안 되는 것
- 템플릿 냄새나는 글 (훅→본문→CTA 기계적 반복)
- 리스트/번호 나열 (에세이형으로)
- 사주 용어로 시작하는 글 (훅에 사주 용어 X)
- 어색한 문장, 번역체
- "~입니다", "~합니다" 존댓말
"""

# ── 14:00 사주심리 브리프 생성 ───────────────────────────────

def generate_14_brief(d: date | None = None) -> dict:
    """14:00용 사주 심리/연애 분석 브리프.

    AI에게 이 브리프를 주고 에세이를 쓰게 한다.
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()

    pillar = get_day_pillar(d)
    ilju = pillar["gan"] + pillar["ji"]
    ilgan = pillar["gan"]
    ilju_adj = ILJU_ADJECTIVES.get(ilju, "")

    # 십성 테마 (날짜별 로테이션)
    day_of_year = d.timetuple().tm_yday
    sipsung_keys = list(SIPSUNG_PATTERNS.keys())
    theme = sipsung_keys[day_of_year % len(sipsung_keys)]
    pattern = SIPSUNG_PATTERNS[theme]

    # 카테고리 (연애/일상 교대)
    category = "연애" if day_of_year % 2 == 0 else "일상"
    if category not in pattern:
        category = "연애"

    # 훅 유형 선택 (5종 로테이션)
    hook_types = ["공감상황", "역설", "시간감정", "양자택일", "공감상황"]
    hook_type = hook_types[day_of_year % len(hook_types)]
    hook_formula = HOOK_FORMULAS[hook_type]
    hook_example_idx = _pick(f"{d.isoformat()}:14:hook", len(hook_formula["예시"]))
    hook_example = hook_formula["예시"][hook_example_idx]

    # 일간 비교 대상 3개
    all_stems = ["갑", "을", "병", "정", "무", "기", "경", "신", "임", "계"]
    compare = [s for s in all_stems if s != ilgan]
    compare_picked = []
    for i in range(3):
        idx = _pick(f"{d.isoformat()}:14:comp:{i}", len(compare))
        compare_picked.append(compare[idx])
        compare.remove(compare[idx])

    # CTA
    cta = CTA_PATTERNS["연애운"] if category == "연애" else CTA_PATTERNS["사주심리"]

    # 소재 문장들
    material_lines = pattern.get(category, pattern.get("연애", []))

    return {
        "date": d.isoformat(),
        "weekday": WEEKDAY_KR[d.weekday()],
        "time": "14:00",
        "type": "사주심리",

        # 만세력 근거
        "pillar": pillar,
        "ilju": ilju,
        "ilju_adj": ilju_adj,
        "ilgan_trait": ILGAN_TRAITS[ilgan],

        # 콘텐츠 방향
        "sipsung_theme": theme,
        "sipsung_desc": pattern["한줄"],
        "category": category,
        "material_lines": material_lines,

        # 훅
        "hook_type": hook_type,
        "hook_formula_desc": hook_formula["설명"],
        "hook_example": hook_example,

        # 비교 대상 일간
        "compare_stems": [
            {"stem": s, "trait": ILGAN_TRAITS[s]} for s in compare_picked
        ],

        # CTA
        "cta": cta,

        # AI 프롬프트
        "system_prompt": ESSAY_SYSTEM_PROMPT,
        "user_prompt": _build_14_prompt(
            d, theme, pattern, category, hook_type, hook_example,
            ilju, ilju_adj, ilgan, compare_picked, material_lines,
        ),
    }


def _build_14_prompt(d, theme, pattern, category, hook_type, hook_example,
                     ilju, ilju_adj, ilgan, compare_stems, materials) -> str:
    """14:00 AI 에세이 작성용 user prompt."""
    trait = ILGAN_TRAITS[ilgan]
    weekday = WEEKDAY_KR[d.weekday()]

    comp_lines = []
    for s in compare_stems:
        t = ILGAN_TRAITS[s]
        if category == "연애":
            comp_lines.append(f"- {s}({t['성격']}): {t['연애']}")
        else:
            comp_lines.append(f"- {s}({t['성격']}): {t['약점']}")

    material_text = "\n".join(f"- {m}" for m in materials)

    return f"""오늘 {d.month}/{d.day}({weekday}) dkbsqd 14:00 글을 써줘.

## 오늘의 만세력 근거
- 일주: {ilju} ({ilju_adj})
- 일간: {ilgan} ({trait['성격']}) — {trait['키워드']}
- 일간 연애 패턴: {trait['연애']}

## 글의 주제
- 십성 테마: {theme} ({pattern['한줄']})
- 카테고리: {category}

## 소재 (이 중에서 골라 자연스럽게 녹여)
{material_text}

## 훅 (첫 줄)
- 훅 유형: {hook_type} — {HOOK_FORMULAS[hook_type]['설명']}
- 참고 예시: "{hook_example}"
- 이 예시를 그대로 쓰지 말고, 오늘 테마({theme})에 맞게 새로 만들어.

## 일간별 비교 (본문에서 3가지 타입 비교)
- {ilgan}({trait['성격']}): {trait['연애'] if category == '연애' else trait['약점']}
{chr(10).join(comp_lines)}

## 형식
- 200-400자
- 에세이형 (번호 나열 X)
- 해시태그 1-2개 마지막에
- 첫 줄은 훅. 사주 용어 안 씀.
- 마무리는 매번 다르게 (강한 선언 / 여운 / 질문 등)
"""


# ── 20:00 연프분석 브리프 생성 ───────────────────────────────

def _pick_cast_pair(d: date) -> tuple[dict, dict]:
    """날짜 기반으로 대비되는 출연자 2명 선택."""
    show = YEONPRO_CAST["솔로지옥5"]
    cast = show["출연자"]
    idx1 = _pick(f"{d.isoformat()}:20:cast1", len(cast))
    idx2 = _pick(f"{d.isoformat()}:20:cast2", len(cast))
    if idx1 == idx2:
        idx2 = (idx2 + 1) % len(cast)
    return cast[idx1], cast[idx2]


def generate_20_brief(d: date | None = None) -> dict:
    """20:00용 연프(연애 프로그램) 사주 분석 브리프.

    실제 출연자를 분석하는 글.
    """
    if d is None:
        d = date.today()
    if isinstance(d, datetime):
        d = d.date()

    pillar = get_day_pillar(d)
    ilju = pillar["gan"] + pillar["ji"]
    ilju_adj = ILJU_ADJECTIVES.get(ilju, "")
    ilgan = pillar["gan"]

    # 훅 (연프 전용)
    hook_pool = HOOK_FORMULAS["연프"]["예시"]
    hook_idx = _pick(f"{d.isoformat()}:20:hook:v3", len(hook_pool))
    hook = hook_pool[hook_idx]

    # 출연자 2명 선택
    cast1, cast2 = _pick_cast_pair(d)

    # 출연자의 사주힌트에서 십성 추출
    show_data = YEONPRO_CAST["솔로지옥5"]

    cta = CTA_PATTERNS["연애운"]

    return {
        "date": d.isoformat(),
        "weekday": WEEKDAY_KR[d.weekday()],
        "time": "20:00",
        "type": "연프분석",

        "pillar": pillar,
        "ilju": ilju,
        "ilju_adj": ilju_adj,
        "ilgan_trait": ILGAN_TRAITS[ilgan],

        "hook": hook,
        "show": "솔로지옥5",
        "cast1": cast1,
        "cast2": cast2,
        "couples": show_data.get("커플", []),

        "cta": cta,

        "system_prompt": ESSAY_SYSTEM_PROMPT,
        "user_prompt": _build_20_prompt(d, hook, cast1, cast2, ilju, ilju_adj, ilgan),
    }


def _build_20_prompt(d, hook, cast1, cast2, ilju, ilju_adj, ilgan) -> str:
    """20:00 AI 에세이 작성용 user prompt — 실제 출연자 분석."""
    trait = ILGAN_TRAITS[ilgan]
    weekday = WEEKDAY_KR[d.weekday()]

    def _cast_info(c):
        lines = [f"- 이름: {c['이름']}"]
        if c.get('나이'): lines.append(f"- 나이: {c['나이']}")
        if c.get('직업'): lines.append(f"- 직업: {c['직업']}")
        if c.get('성격'): lines.append(f"- 성격: {c['성격']}")
        if c.get('연애스타일'): lines.append(f"- 연애스타일: {c['연애스타일']}")
        if c.get('MBTI') and c['MBTI'] != '알 수 없음': lines.append(f"- MBTI: {c['MBTI']}")
        if c.get('사주힌트'): lines.append(f"- 사주 분석 힌트: {c['사주힌트']}")
        return "\n".join(lines)

    return f"""오늘 {d.month}/{d.day}({weekday}) dkbsqd 20:00 글을 써줘.

## 오늘의 만세력 근거
- 일주: {ilju} ({ilju_adj})
- 일간: {ilgan} ({trait['성격']})

## 글의 방향
솔로지옥5의 **실제 출연자**를 사주로 분석하는 글.
두 출연자의 연애 스타일/성격을 사주 관점에서 비교 분석해.

## 출연자 1
{_cast_info(cast1)}

## 출연자 2
{_cast_info(cast2)}

## 훅 (첫 줄)
- 참고: "{hook}"
- 출연자 이름이나 행동을 구체적으로 언급하면서 시작. 사주 용어는 본문에서.

## 글쓰기 규칙
- 200-400자
- 에세이형, 자연스러운 반말
- 출연자 **이름을 직접 언급**하며 분석
- 사주 용어(십성, 일간 등)로 그 사람의 행동 패턴을 설명
- "왜 그런 행동을 했는지" 사주로 풀어주는 게 핵심
- 마지막에 독자 참여 유도 (나는 어떤 타입?, 어떤 사람이 끌려? 등)
- 해시태그 1-2개

## 전에 잘 된 예시 (이 톤과 깊이로)

```
솔지5에서 조용히 마음 여는 사람들 있잖아
처음엔 존재감 없다가 나중에 기억에 남는 사람.

인성(印星)이 강한 사람: 천천히 신뢰 쌓아가. 빠른 친밀감 못 믿어.
식신(食神) 일간: 자기 속도가 있어. 강요하면 더 닫혀버림.
계수(癸水): 감정이 깊어서 오래 관찰해. 마음 열면 그게 진짜야.

이런 사람이 먼저 이야기 꺼냈다면
오래 고민하고 한 말이야.
빨리 친해지려 하지 말고
천천히 기다려주는 게 정답.
#사주 #솔로지옥5 #마음읽기
```

```
이번 주 솔지5 보면서 제일 인상적이었던 거
말 잘하는 사람이 이기는 게 아니더라.
가만히 있어도 기억에 남는 사람들.
공통점이 뭔지 알아?
자기 기준이 있어. 흔들리지 않아.
좋아하면 일관되게 해.
사주로 보면 정관(正官)이나 인성(印星) 기운 있는 사람들이 그래.
화려하지 않아도 오래 남아.
```

출연자 이름과 구체적 행동을 넣어서 이 수준으로 써줘.
"""


# ── 주간 배치 ───────────────────────────────────────────────

def generate_weekly_briefs(start: date | None = None) -> list[dict]:
    """이번 주 14:00/20:00 브리프 전부 생성."""
    if start is None:
        start = date.today()

    days_until_sunday = 6 - start.weekday()
    if days_until_sunday <= 0:
        days_until_sunday = 7

    briefs = []
    for i in range(days_until_sunday + 1):
        d = start + timedelta(days=i)
        briefs.append(generate_14_brief(d))
        briefs.append(generate_20_brief(d))

    return briefs


# ── 하위 호환 ───────────────────────────────────────────────
# 기존 함수명 유지
generate_saju_psychology = generate_14_brief
generate_yeonpro_analysis = generate_20_brief
generate_weekly_drafts = generate_weekly_briefs
