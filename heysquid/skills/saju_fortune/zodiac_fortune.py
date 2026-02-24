"""띠별 일일 운세 생성기 — dokkebi-v2 사주 엔진 로직 기반.

일진(日辰)의 천간지지를 계산하고, 각 띠(12지신)의 오행과의
상생/상극 관계를 분석하여 연년생별 운세를 생성한다.
"""

from datetime import date, timedelta
import random

# === 천간지지 기본 데이터 ===

STEMS = ['갑', '을', '병', '정', '무', '기', '경', '신', '임', '계']
BRANCHES = ['자', '축', '인', '묘', '진', '사', '오', '미', '신', '유', '술', '해']

# 띠 이름 (지지 순서)
ZODIAC_NAMES = ['쥐', '소', '호랑이', '토끼', '용', '뱀', '말', '양', '원숭이', '닭', '개', '돼지']
ZODIAC_EMOJI = ['🐭', '🐂', '🐯', '🐰', '🐉', '🐍', '🐴', '🐑', '🐵', '🐔', '🐕', '🐷']

# 천간 → 오행
STEM_ELEMENTS = {
    '갑': '목', '을': '목',
    '병': '화', '정': '화',
    '무': '토', '기': '토',
    '경': '금', '신': '금',
    '임': '수', '계': '수',
}

# 지지 → 오행
BRANCH_ELEMENTS = {
    '자': '수', '축': '토', '인': '목', '묘': '목',
    '진': '토', '사': '화', '오': '화', '미': '토',
    '신': '금', '유': '금', '술': '토', '해': '수',
}

# 오행 순서 (상생: +1, 상극: +2)
ELEMENT_ORDER = ['목', '화', '토', '금', '수']

# === 20~40대 타겟 연년생 (2026년 기준) ===
# 각 띠별 2개 연년생 (년생 → 나이)
ZODIAC_YEARS = {
    '쥐': [96, 84],      # 30세, 42세
    '소': [97, 85],      # 29세, 41세
    '호랑이': [98, 86],  # 28세, 40세
    '토끼': [99, 87],    # 27세, 39세
    '용': [0, 88],       # 26세 (00년생), 38세
    '뱀': [1, 89],       # 25세 (01년생), 37세
    '말': [2, 90],       # 24세, 36세
    '양': [3, 91],       # 23세, 35세
    '원숭이': [4, 92],   # 22세, 34세
    '닭': [5, 93],       # 21세, 33세
    '개': [6, 94],       # 20세, 32세
    '돼지': [95, 83],    # 31세, 43세
}


def _format_year(y: int) -> str:
    """연도를 '00년생' 형식으로 포맷."""
    return f"{y:02d}년생"


# === 일진 계산 (dokkebi-v2 pillar-calculator.ts 포팅) ===

# 기준 에포크: 1900년 2월 19일 = 갑자일
EPOCH = date(1900, 2, 19)


def calculate_day_pillar(target: date) -> tuple[str, str, str, str]:
    """특정 날짜의 일진(天干地支)을 계산한다.

    Returns:
        (천간, 지지, 천간오행, 지지오행)
    """
    diff = (target - EPOCH).days
    offset = ((diff % 60) + 60) % 60  # 60갑자 순환
    stem_idx = offset % 10
    branch_idx = offset % 12

    stem = STEMS[stem_idx]
    branch = BRANCHES[branch_idx]
    return stem, branch, STEM_ELEMENTS[stem], BRANCH_ELEMENTS[branch]


def get_element_relation(a: str, b: str) -> str:
    """오행 a와 b의 관계를 판단한다.

    Returns:
        'same' | 'generate' (a가 b를 생) | 'generated' (b가 a를 생) |
        'control' (a가 b를 극) | 'controlled' (b가 a를 극)
    """
    if a == b:
        return 'same'
    ai = ELEMENT_ORDER.index(a)
    bi = ELEMENT_ORDER.index(b)
    if (ai + 1) % 5 == bi:
        return 'generate'    # a → b 상생 (내가 생해주는 관계)
    if (bi + 1) % 5 == ai:
        return 'generated'   # b → a 상생 (생을 받는 관계)
    if (ai + 2) % 5 == bi:
        return 'control'     # a → b 상극 (내가 극하는 관계)
    if (bi + 2) % 5 == ai:
        return 'controlled'  # b → a 상극 (극을 당하는 관계)
    return 'same'  # fallback


# === 운세 텍스트 풀 ===
# 관계별로 다양한 운세 문구 (짧게, 20~25자 이내)

FORTUNE_POOL = {
    'generate': {  # 일진→띠 상생 = 띠가 에너지 받음 → 길
        'general': [
            '좋은 기운 들어오는 날',
            '흐름 잘 타는 하루',
            '귀인 도움 있을 수 있어',
            '새 기회 열리는 날',
            '오늘 시작하면 순조로워',
        ],
        'young': [
            '뜻밖의 연락이 기회',
            '약속 잡아 에너지↑',
            '하고 싶던 거 오늘 해',
            '좋은 인연 만날 흐름',
            '직감 따라가면 답 나와',
        ],
        'older': [
            '정리하면 새 시작 열려',
            '인맥이 성과로 이어져',
            '기다리면 결과 온다',
            '오래된 관계서 힌트',
            '경험이 빛나는 하루',
        ],
    },
    'generated': {  # 띠→일진 상생 = 띠가 에너지 줌 → 소모/보람
        'general': [
            '도움 주면 복이 돼',
            '베풀면 돌아오는 날',
            '보람 있는 하루',
            '남 위한 일이 행운으로',
        ],
        'young': [
            '도움 요청 거절 말고',
            '도와주다 좋은 인연↑',
            '체력 관리하며 움직여',
        ],
        'older': [
            '조언하면 복 돌아와',
            '경험 나누면 관계↑',
            '소소한 투자 아끼지 마',
        ],
    },
    'same': {  # 같은 오행 → 동반/경쟁
        'general': [
            '같은 뜻 가진 사람 만나',
            '협력이 답이야',
            '비교 말고 내 길 가',
            '뜻 맞는 사람과 시너지',
        ],
        'young': [
            '같이하면 시너지 터져',
            '내 속도로 가면 돼',
            '관심사 모임 가봐',
        ],
        'older': [
            '역할 명확히 나눠',
            '파트너십 점검 필요',
            '팀플이 낫은 날',
        ],
    },
    'control': {  # 일진이 띠를 극함 → 압박, 조심
        'general': [
            '조심히 움직이는 게 나아',
            '무리하지 마 쉬어',
            '참는 게 이득인 날',
        ],
        'young': [
            '쉬는 것도 실력이야',
            '유혹 조심 침착하게',
            '급한 결정 내일로',
            '몸 신호 들어봐',
        ],
        'older': [
            '욕심 내려놓으면 편해',
            '양보하면 마찰 줄어',
            '지금은 때를 기다려',
        ],
    },
    'controlled': {  # 띠가 일진을 극함 → 추진력, 주도권
        'general': [
            '밀어붙이되 선 지켜',
            '결단력 좋은 날',
            '추진력↑ 빠르게 움직여',
        ],
        'young': [
            '솔직한 게 답이야',
            '리더십 발휘 기회',
            '미루지 마 오늘 해',
            '직감 믿고 결정해',
        ],
        'older': [
            '결단 타이밍 왔어',
            '소신대로 밀어붙여',
            '부드럽게 이끌면 OK',
        ],
    },
}


def generate_daily_zodiac_fortune(target: date, seed: int | None = None) -> dict:
    """특정 날짜의 띠별 운세를 생성한다.

    Args:
        target: 대상 날짜
        seed: 랜덤 시드 (같은 날짜+시드 → 같은 결과)

    Returns:
        {
            'date': '2026-02-23',
            'day_of_week': '월',
            'day_pillar': '갑자',
            'day_element': '수',
            'fortunes': [
                {
                    'zodiac': '쥐', 'emoji': '🐭',
                    'relation': 'same',
                    'years': [
                        {'year': '96년생', 'fortune': '...'},
                        {'year': '84년생', 'fortune': '...'},
                    ]
                },
                ...
            ]
        }
    """
    if seed is None:
        seed = target.toordinal()
    rng = random.Random(seed)

    stem, branch, stem_element, branch_element = calculate_day_pillar(target)

    days_kr = ['월', '화', '수', '목', '금', '토', '일']
    day_of_week = days_kr[target.weekday()]

    fortunes = []
    global_used: set[str] = set()  # 전체 글에서 중복 방지
    for i, (zodiac_name, emoji) in enumerate(zip(ZODIAC_NAMES, ZODIAC_EMOJI)):
        zodiac_branch = BRANCHES[i]
        zodiac_element = BRANCH_ELEMENTS[zodiac_branch]

        # 일진 지지의 오행 vs 띠의 오행 관계
        relation = get_element_relation(branch_element, zodiac_element)

        pool = FORTUNE_POOL[relation]
        years = ZODIAC_YEARS[zodiac_name]

        year_fortunes = []
        used_fortunes = global_used  # 전체 글에서 중복 방지
        for j, y in enumerate(years):
            age_pool = pool['young'] if j == 0 else pool['older']
            combined = age_pool + pool['general']
            # 중복 제거: 이미 사용된 문구 제외
            available = [f for f in combined if f not in used_fortunes]
            if not available:
                available = combined  # fallback
            fortune_text = rng.choice(available)
            used_fortunes.add(fortune_text)
            year_fortunes.append({
                'year': _format_year(y),
                'fortune': fortune_text,
            })

        fortunes.append({
            'zodiac': zodiac_name,
            'emoji': emoji,
            'branch': zodiac_branch,
            'element': zodiac_element,
            'relation': relation,
            'years': year_fortunes,
        })

    return {
        'date': target.isoformat(),
        'day_of_week': day_of_week,
        'day_pillar': f'{stem}{branch}',
        'day_stem_element': stem_element,
        'day_branch_element': branch_element,
        'fortunes': fortunes,
    }


def format_thread_post(fortune_data: dict) -> str:
    """운세 데이터를 Threads 게시글 텍스트로 포맷한다.

    500자 이내를 목표로 한다.
    """
    d = fortune_data['date'].replace('-', '/')
    dow = fortune_data['day_of_week']

    lines = [f"{d[5:]} {dow} 띠별 운세 🔮"]

    for f in fortune_data['fortunes']:
        emoji = f['emoji']
        y1 = f['years'][0]
        y2 = f['years'][1]
        line = f"{emoji}{y1['year']}: {y1['fortune']}/{y2['year']}: {y2['fortune']}"
        lines.append(line)

    lines.append("가장 정확한 오늘의 운세는 댓글에 🔮")

    return "\n".join(lines)


def generate_week_fortunes(start: date) -> list[dict]:
    """일주일치 운세를 미리 생성한다."""
    results = []
    for i in range(7):
        target = start + timedelta(days=i)
        fortune = generate_daily_zodiac_fortune(target)
        results.append(fortune)
    return results


if __name__ == "__main__":
    # 테스트: 오늘 운세 생성
    today = date.today()
    fortune = generate_daily_zodiac_fortune(today)
    text = format_thread_post(fortune)
    print(f"일진: {fortune['day_pillar']} ({fortune['day_stem_element']}/{fortune['day_branch_element']})")
    print(f"글자 수: {len(text)}")
    print("---")
    print(text)
