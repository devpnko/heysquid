"""ChatScreen — 채팅 모드 화면"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Header

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.message_view import MessageView
from ..widgets.chat_input import ChatInput
from ..widgets.command_input import COMMANDS
from ..utils import get_at_context
from ..data_poller import poll_chat_messages, load_agent_status, is_executor_live
from ..colors import AGENT_COLORS


class ChatScreen(Screen):
    """Chat 모드 — 메시지 뷰 + 입력"""

    DEFAULT_CSS = """
    ChatScreen {
        layout: vertical;
    }
    #chat-header {
        height: 1;
        padding: 0 1;
    }
    #chat-sep-top {
        height: 1;
        color: $surface;
    }
    #chat-sep-bottom {
        height: 1;
        color: $surface;
    }
    #chat-status-bar {
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    #autocomplete-hint {
        height: 1;
        margin: 0 2;
        display: none;
    }
    #autocomplete-hint.has-hint {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="chat-header")
        yield AgentCompactBar()
        yield Static("─" * 120, id="chat-sep-top")
        yield MessageView(id="chat-messages")
        yield Static("─" * 120, id="chat-sep-bottom")
        yield ChatInput(id="chat-input")
        yield Static("", id="autocomplete-hint")
        yield Static(self._status_bar_text(), id="chat-status-bar")

    def _header_text(self, pm_status: str = "idle") -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = f"[bold green]● LIVE[/bold green]" if live else "[dim]○ IDLE[/dim]"
        # PM 상태 표시
        pm_indicator = ""
        if pm_status == "chatting":
            pm_indicator = "  [bold cyan]💬 chatting[/bold cyan]"
        elif pm_status == "thinking":
            pm_indicator = "  [bold #cc66ff]💭 thinking[/bold #cc66ff]"
        elif pm_status == "working":
            pm_indicator = "  [bold #ff9f43]⚙️ working[/bold #ff9f43]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[CHAT][/bold {pm_color}]  {indicator}{pm_indicator}"

    def _status_bar_text(self) -> str:
        return "[dim] q:quit  Ctrl+1/2/3/4:mode  Ctrl+\u2190\u2192  Enter:send  Tab:/ @완성  drag+Ctrl+C:복사[/dim]"

    def on_text_area_changed(self, event) -> None:
        """ChatInput 텍스트 변경 → 자동완성 힌트 업데이트"""
        hint = self._compute_autocomplete_hint(event.text_area.text)
        hint_widget = self.query_one("#autocomplete-hint", Static)
        if hint:
            hint_widget.update(f"[dim]{hint}[/dim]")
            hint_widget.add_class("has-hint")
        else:
            hint_widget.update("")
            hint_widget.remove_class("has-hint")

    def _compute_autocomplete_hint(self, text: str) -> str:
        """입력 텍스트 기반 자동완성 힌트 계산"""
        # 슬래시 커맨드
        if text.startswith("/"):
            partial = text.lstrip("/").rstrip(" ").lower()
            if text.endswith(" ") and partial in COMMANDS:
                return ""
            candidates = COMMANDS if not partial else [c for c in COMMANDS if c.startswith(partial)]
            if candidates:
                return "  " + " · ".join(f"/{c}" for c in candidates)
            return ""
        # @멘션
        at_ctx = get_at_context(text)
        if at_ctx:
            _, _, candidates = at_ctx
            if candidates:
                return "  " + " · ".join(f"@{c}" for c in candidates)
        return ""

    def refresh_data(self, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신 — 각 섹션 독립적으로 보호"""
        # 메시지 업데이트 최우선
        try:
            messages = poll_chat_messages()
            msg_view = self.query_one("#chat-messages", MessageView)
            msg_view.update_messages(messages)
        except Exception:
            pass

        # 에이전트 상태 (실패해도 무시)
        try:
            status = load_agent_status()
            pm_status = status.get("pm", {}).get("status", "idle")
            header = self.query_one("#chat-header", Static)
            header.update(self._header_text(pm_status))
            bar = self.query_one(AgentCompactBar)
            bar.update_status(status)
        except Exception:
            pass

        # 상태바
        if flash:
            try:
                status_bar = self.query_one("#chat-status-bar", Static)
                status_bar.update(f"[dim] {flash}[/dim]")
            except Exception:
                pass

    def clear_flash(self) -> None:
        """flash 메시지 클리어"""
        status_bar = self.query_one("#chat-status-bar", Static)
        status_bar.update(self._status_bar_text())
