"""Agent color mapping -- uses hex colors directly from agents.py."""

from heysquid.core.agents import AGENTS, KRAKEN_CREW

# Agent name -> hex color
AGENT_COLORS: dict[str, str] = {
    name: info["color_hex"] for name, info in AGENTS.items()
}

# Special colors
COLORS = {
    "commander": "#ffffff",
    "system": "#888888",
    "dim": "#666666",
    "date_sep": "#555555",
    "status_bar": "#333333",
    "live": "#26de81",
    "idle_indicator": "#888888",
    "input_prompt": "#00d4ff",
}

# entry type -> color/icon
ENTRY_TYPE_STYLE = {
    "opinion": ("💬", "#ffffff"),
    "agree": ("👍", "#26de81"),
    "disagree": ("👎", "#ff6b6b"),
    "proposal": ("💡", "#ffd32a"),
    "conclusion": ("✅", "#26de81"),
    "risk": ("⚠️", "#ff9f43"),
}

# Channel tags
CHANNEL_TAG = {
    "telegram": "[TG]",
    "tui": "[TUI]",
    "system": "[SYS]",
    "discord": "[DC]",
    "slack": "[SL]",
}
