"""MessageView -- Scrollable chat message view."""

from datetime import datetime

from textual.widgets import Static
from textual.containers import VerticalScroll

from heysquid.core.agents import AGENTS
from ..colors import AGENT_COLORS, CHANNEL_TAG


class MessageView(VerticalScroll):
    """Scrollable chat message view."""

    DEFAULT_CSS = """
    MessageView {
        height: 1fr;
        padding: 0 1;
    }
    MessageView > Static {
        width: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_snapshot = (0, None)
        self._auto_scroll = True

    def on_scroll_y(self) -> None:
        """Determine auto-scroll on scroll position change."""
        # Keep auto_scroll if near bottom (within 2 lines)
        if self.scroll_y >= self.max_scroll_y - 2:
            self._auto_scroll = True
        else:
            self._auto_scroll = False

    def update_messages(self, messages: list[dict]) -> None:
        """Update view with message list."""
        snapshot = (len(messages), messages[-1] if messages else None)
        if snapshot == self._last_snapshot:
            return

        # Skip refresh during selection (prevent widget destruction)
        try:
            if self.screen.selections:
                return
        except Exception:
            pass

        self._last_snapshot = snapshot

        # Remove existing content and rebuild
        self.remove_children()
        last_date = None

        for msg in messages:
            ts = msg.get("timestamp", "")
            msg_type = msg.get("type", "")
            text = msg.get("text", "")
            channel = msg.get("channel", msg.get("source", "telegram"))

            # Parse date/time
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                date_str = dt.strftime("%Y/%m/%d")
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                date_str = ""
                time_str = "??:??"

            # Date separator
            if date_str and date_str != last_date:
                last_date = date_str
                self.mount(Static(
                    f"[dim]── {date_str} ──[/dim]",
                    classes="date-sep",
                ))

            # Sender header
            ch_tag = CHANNEL_TAG.get(channel, f"[{channel}]")
            pm_color = AGENT_COLORS.get("pm", "#ff6b9d")

            if msg_type == "user":
                source = msg.get("source", channel)
                if source == "tui":
                    sender = f"[#00d4ff][{time_str}] {ch_tag} COMMANDER[/#00d4ff]"
                else:
                    name = msg.get("first_name") or msg.get("username") or "User"
                    sender = f"[bold white][{time_str}] {ch_tag} {name}[/bold white]"
            else:
                sender = f"[{pm_color}][{time_str}] SQUID 🦑[/{pm_color}]"

            self.mount(Static(sender, classes="msg-header"))

            # Body (markup=False: prevent Rich parsing errors from user text with [] etc.)
            if text:
                self.mount(Static(f"  {text}", classes="msg-body", markup=False))

            # File attachments
            files = msg.get("files", [])
            for fi in files:
                fname = fi.get("name") or fi.get("type", "file")
                icon = "🖼️" if fi.get("type") == "photo" else "📎"
                self.mount(Static(f"  {icon} {fname}", classes="msg-body", markup=False))

        # Auto-scroll
        if self._auto_scroll:
            self.call_after_refresh(self.scroll_end, animate=False)
