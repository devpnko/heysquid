"""ChatScreen — 채팅 모드 화면"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static, Header

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.message_view import MessageView
from ..widgets.chat_input import ChatInput
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
    """

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="chat-header")
        yield AgentCompactBar()
        yield Static("─" * 120, id="chat-sep-top")
        yield MessageView(id="chat-messages")
        yield Static("─" * 120, id="chat-sep-bottom")
        yield ChatInput(id="chat-input")
        yield Static(self._status_bar_text(), id="chat-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = f"[bold green]● LIVE[/bold green]" if live else "[dim]○ IDLE[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[CHAT][/bold {pm_color}]  {indicator}"

    def _status_bar_text(self) -> str:
        return "[dim] q:quit  Ctrl+1/2/3/4:mode  Ctrl+\u2190\u2192  Enter:send  Tab:@완성[/dim]"

    def refresh_data(self, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신"""
        messages = poll_chat_messages()
        status = load_agent_status()

        # 헤더 업데이트
        header = self.query_one("#chat-header", Static)
        header.update(self._header_text())

        # 에이전트 바 업데이트
        bar = self.query_one(AgentCompactBar)
        bar.update_status(status)

        # 메시지 뷰 업데이트
        msg_view = self.query_one("#chat-messages", MessageView)
        msg_view.update_messages(messages)

        # 상태바
        if flash:
            status_bar = self.query_one("#chat-status-bar", Static)
            status_bar.update(f"[dim] {flash}[/dim]")

    def clear_flash(self) -> None:
        """flash 메시지 클리어"""
        status_bar = self.query_one("#chat-status-bar", Static)
        status_bar.update(self._status_bar_text())
