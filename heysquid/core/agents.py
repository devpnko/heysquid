"""Agent registry — single source of truth for all agent information."""

AGENTS = {
    "pm": {
        "animal": "squid",
        "emoji": "🦑",
        "color": "pink",
        "color_hex": "#ff6b9d",
        "css_class": "squid-pixel-lg",
        "label": "SQUID",
        "model": "opus",
        "role": "PM/Team Lead",
    },
    "researcher": {
        "animal": "octopus",
        "emoji": "🐙",
        "color": "cyan",
        "color_hex": "#00d4ff",
        "css_class": "octopus-pixel",
        "label": "Explorer",
        "model": "haiku",
        "role": "Exploration/Research",
    },
    "developer": {
        "animal": "shark",
        "emoji": "🦈",
        "color": "orange",
        "color_hex": "#ff9f43",
        "css_class": "shark-pixel",
        "label": "Engineer",
        "model": "opus",
        "role": "Implementation/Coding",
    },
    "reviewer": {
        "animal": "turtle",
        "emoji": "🐢",
        "color": "green",
        "color_hex": "#26de81",
        "css_class": "turtle-pixel",
        "label": "Reviewer",
        "model": "sonnet",
        "role": "Review/Audit",
    },
    "tester": {
        "animal": "pufferfish",
        "emoji": "🐡",
        "color": "yellow",
        "color_hex": "#ffd32a",
        "css_class": "puffer-pixel",
        "label": "Tester",
        "model": "haiku",
        "role": "Testing/QA",
    },
    "writer": {
        "animal": "lobster",
        "emoji": "🦞",
        "color": "lavender",
        "color_hex": "#bb88ff",
        "css_class": "lobster-pixel",
        "label": "Writer",
        "model": "sonnet",
        "role": "Writing/Content",
    },
}

# Tool emoji (shared between stream_viewer + dashboard)
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

# Claude Code subagent_type -> dashboard agent mapping
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

# Convenience constants/functions
AGENT_NAMES = [k for k in AGENTS if k != "pm"]
VALID_AGENTS = list(AGENTS.keys())


def get_emoji(agent_name):
    """Agent name -> animal emoji"""
    return AGENTS.get(agent_name, {}).get("emoji", "🤖")


def get_color(agent_name):
    """Agent name -> color hex"""
    return AGENTS.get(agent_name, {}).get("color_hex", "#ffffff")


def get_role_emoji(agent_name):
    """Agent name -> role emoji (for mission_log formatting)"""
    role_emojis = {
        "pm": "🦑",
        "researcher": "🔭",
        "developer": "⚙️",
        "reviewer": "📋",
        "tester": "🧪",
        "writer": "✍️",
    }
    return role_emojis.get(agent_name, "🔧")


# Kraken Crew — Virtual experts exclusive to Kraken mode (PM simulates them)
# Deep-sea crew summoned by the Kraken — marine creature traits match their roles
KRAKEN_CREW = {
    # Builders (development/business)
    "seal":      {"name": "Seal",      "animal": "seal",        "role": "Analyst",          "emoji": "🦭",  "crew": "builders",
                  "style": "Quiet observation, evidence-based, uncovers hidden insights, market/competition frameworks"},
    "whale":     {"name": "Whale",     "animal": "whale",       "role": "Architect",        "emoji": "🐋",  "crew": "builders",
                  "style": "Big-picture thinking, pragmatic architecture, scalability tradeoffs, proven technologies"},
    "crab":      {"name": "Crab",      "animal": "crab",        "role": "Developer",        "emoji": "🦀",  "crew": "builders",
                  "style": "Precise implementation, strict TDD, 100% test coverage required, robust code"},
    "dolphin":   {"name": "Dolphin",   "animal": "dolphin",     "role": "PM",               "emoji": "🐬",  "crew": "builders",
                  "style": "WHY-driven, data-based, communication master, validate minimum features first"},
    "sailfish":  {"name": "Sailfish",  "animal": "sailfish",    "role": "Solo Dev",         "emoji": "🐟",  "crew": "builders",
                  "style": "Fastest in the sea, Quick Flow, minimal overhead, shipped > perfect"},
    "otter":     {"name": "Otter",     "animal": "otter",       "role": "Scrum Master",     "emoji": "🦦",  "crew": "builders",
                  "style": "Tool usage, checklists, zero ambiguity, servant leader"},
    "nautilus":  {"name": "Nautilus",  "animal": "nautilus",    "role": "Tech Writer",      "emoji": "🐚",  "crew": "builders",
                  "style": "Golden-ratio structure, clarity first, diagrams > long explanations"},
    "coral":     {"name": "Coral",     "animal": "coral",       "role": "UX Designer",      "emoji": "🪸",  "crew": "builders",
                  "style": "Ecosystem-based design, storytelling, empathy, simplicity->feedback"},
    # Dreamers (creativity/innovation)
    "clownfish": {"name": "Clownfish", "animal": "clownfish",   "role": "Brainstorm Coach", "emoji": "🐠",  "crew": "dreamers",
                  "style": "Safe environment, wild ideas, play-based ideation"},
    "jellyfish": {"name": "Jellyfish", "animal": "jellyfish",   "role": "Problem Solver",   "emoji": "🪼",  "crew": "dreamers",
                  "style": "500M years of adaptability, sees through, TRIZ, systems thinking, resolves contradictions"},
    "shrimp":    {"name": "Shrimp",    "animal": "cleaner shrimp", "role": "Design Thinking",  "emoji": "🦐",  "crew": "dreamers",
                  "style": "User-centered service, validate assumptions, prototype first"},
    "flyingfish":{"name": "Flyingfish","animal": "flying fish",  "role": "Innovation",       "emoji": "🐟",  "crew": "dreamers",
                  "style": "Break boundaries, shatter existing molds, business model innovation"},
    "cuttlefish":{"name": "Cuttlefish","animal": "cuttlefish",  "role": "Presentation",     "emoji": "🦑",  "crew": "dreamers",
                  "style": "Full-body color/pattern transformation, visual narrative, visual hierarchy"},
}

KRAKEN_CREW_NAMES = list(KRAKEN_CREW.keys())
