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

# 외부 AI 레지스트리
EXTERNAL_AIS = {
    "gpt": {"creature": "whale", "emoji": "🐳", "color_hex": "#4488ff"},
    "gemini": {"creature": "jellyfish", "emoji": "🪼", "color_hex": "#cc66ff"},
    "grok": {"creature": "eel", "emoji": "⚡", "color_hex": "#ffdd44"},
    "whisper": {"creature": "dolphin", "emoji": "🐬", "color_hex": "#66ddee"},
    "perplexity": {"creature": "stingray", "emoji": "🔶", "color_hex": "#ff7744"},
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
