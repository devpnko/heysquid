"""에이전트 레지스트리 — 모든 에이전트 정보의 단일 소스."""

AGENTS = {
    "pm": {
        "animal": "squid",
        "emoji": "🦑",
        "color": "pink",
        "color_hex": "#ff6b9d",
        "css_class": "squid-pixel-lg",
        "label": "SQUID",
        "model": "opus",
        "role": "PM/팀 리더",
    },
    "researcher": {
        "animal": "octopus",
        "emoji": "🐙",
        "color": "cyan",
        "color_hex": "#00d4ff",
        "css_class": "octopus-pixel",
        "label": "Explorer",
        "model": "haiku",
        "role": "탐색/조사",
    },
    "developer": {
        "animal": "shark",
        "emoji": "🦈",
        "color": "orange",
        "color_hex": "#ff9f43",
        "css_class": "shark-pixel",
        "label": "Engineer",
        "model": "opus",
        "role": "구현/코딩",
    },
    "reviewer": {
        "animal": "turtle",
        "emoji": "🐢",
        "color": "green",
        "color_hex": "#26de81",
        "css_class": "turtle-pixel",
        "label": "Reviewer",
        "model": "sonnet",
        "role": "리뷰/검토",
    },
    "tester": {
        "animal": "pufferfish",
        "emoji": "🐡",
        "color": "yellow",
        "color_hex": "#ffd32a",
        "css_class": "puffer-pixel",
        "label": "Tester",
        "model": "haiku",
        "role": "테스트/QA",
    },
    "writer": {
        "animal": "lobster",
        "emoji": "🦞",
        "color": "lavender",
        "color_hex": "#bb88ff",
        "css_class": "lobster-pixel",
        "label": "Writer",
        "model": "sonnet",
        "role": "작성/콘텐츠",
    },
}

# 도구 이모지 (stream_viewer + dashboard 공용)
TOOL_EMOJI = {
    "Read": "📖",
    "Edit": "✏️",
    "Write": "📝",
    "Bash": "💻",
    "Grep": "🔍",
    "Glob": "📂",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
    "Task": "🎯",
    "sleep": "💤",
}

# Claude Code subagent_type → 대시보드 에이전트 매핑
SUBAGENT_MAP = {
    "Explore": "researcher",
    "researcher": "researcher",
    "general-purpose": "developer",
    "developer": "developer",
    "reviewer": "reviewer",
    "tester": "tester",
    "writer": "writer",
    "Plan": None,
    "Bash": None,
}

# 편의 상수/함수
AGENT_NAMES = [k for k in AGENTS if k != "pm"]
VALID_AGENTS = list(AGENTS.keys())


def get_emoji(agent_name):
    """에이전트 이름 → 동물 이모지"""
    return AGENTS.get(agent_name, {}).get("emoji", "🤖")


def get_color(agent_name):
    """에이전트 이름 → 색상 hex"""
    return AGENTS.get(agent_name, {}).get("color_hex", "#ffffff")


def get_role_emoji(agent_name):
    """에이전트 이름 → 역할 이모지 (mission_log 포맷용)"""
    role_emojis = {
        "pm": "🦑",
        "researcher": "🔭",
        "developer": "⚙️",
        "reviewer": "📋",
        "tester": "🧪",
        "writer": "✍️",
    }
    return role_emojis.get(agent_name, "🔧")


# Kraken Crew — Kraken 모드 전용 가상 전문가 (PM이 시뮬레이션)
# 크라켄이 소환하는 심해 크루 — 해양생물 습성이 역할과 매칭
KRAKEN_CREW = {
    # Builders (개발/비즈니스)
    "seal":      {"name": "Seal",      "animal": "물범",     "role": "Analyst",          "emoji": "🦭",  "crew": "builders",
                  "style": "조용한 관찰, 근거 기반, 숨겨진 인사이트 발굴, 시장/경쟁 프레임워크"},
    "whale":     {"name": "Whale",     "animal": "고래",     "role": "Architect",        "emoji": "🐋",  "crew": "builders",
                  "style": "거시적 시각, 실용적 아키텍처, 확장성 트레이드오프, 검증된 기술"},
    "crab":      {"name": "Crab",      "animal": "게",       "role": "Developer",        "emoji": "🦀",  "crew": "builders",
                  "style": "정밀한 구현, TDD 철저, 테스트 100% 필수, 견고한 코드"},
    "dolphin":   {"name": "Dolphin",   "animal": "돌고래",   "role": "PM",               "emoji": "🐬",  "crew": "builders",
                  "style": "WHY 추적, 데이터 기반, 소통의 달인, 최소 기능 검증 우선"},
    "sailfish":  {"name": "Sailfish",  "animal": "돛새치",   "role": "Solo Dev",         "emoji": "🐟",  "crew": "builders",
                  "style": "바다 최속, Quick Flow, 최소 오버헤드, shipped > perfect"},
    "otter":     {"name": "Otter",     "animal": "해달",     "role": "Scrum Master",     "emoji": "🦦",  "crew": "builders",
                  "style": "도구 사용, 체크리스트, 모호함 제로, 서번트 리더"},
    "nautilus":  {"name": "Nautilus",  "animal": "앵무조개", "role": "Tech Writer",      "emoji": "🐚",  "crew": "builders",
                  "style": "황금비율 구조, 명확성 최우선, 다이어그램 > 긴 설명"},
    "coral":     {"name": "Coral",     "animal": "산호",     "role": "UX Designer",      "emoji": "🪸",  "crew": "builders",
                  "style": "생태계 기반 설계, 스토리텔링, 공감, 단순함→피드백"},
    # Dreamers (창의/혁신)
    "clownfish": {"name": "Clownfish", "animal": "흰동가리", "role": "Brainstorm Coach", "emoji": "🐠",  "crew": "dreamers",
                  "style": "안전한 환경 조성, 와일드 아이디어, 놀이 기반 발상"},
    "jellyfish": {"name": "Jellyfish", "animal": "해파리",   "role": "Problem Solver",   "emoji": "🪼",  "crew": "dreamers",
                  "style": "5억년 적응력, 꿰뚫어 봄, TRIZ, 시스템 씽킹, 모순 해결"},
    "shrimp":    {"name": "Shrimp",    "animal": "청소새우", "role": "Design Thinking",  "emoji": "🦐",  "crew": "dreamers",
                  "style": "사용자 중심 봉사, 가정 검증, 프로토타입 우선"},
    "flyingfish":{"name": "Flyingfish","animal": "날치",     "role": "Innovation",       "emoji": "🐟",  "crew": "dreamers",
                  "style": "경계 돌파, 기존 틀 깨기, 비즈니스 모델 혁신"},
    "cuttlefish":{"name": "Cuttlefish","animal": "갑오징어", "role": "Presentation",     "emoji": "🦑",  "crew": "dreamers",
                  "style": "몸 전체 색/패턴 변환, 비주얼 내러티브, 시각 계층"},
}

KRAKEN_CREW_NAMES = list(KRAKEN_CREW.keys())
