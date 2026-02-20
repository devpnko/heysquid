"""MessageView — 스크롤 가능 채팅 메시지 뷰"""

from datetime import datetime

from textual.widgets import Static
from textual.containers import VerticalScroll

from heysquid.core.agents import AGENTS
from ..colors import AGENT_COLORS, CHANNEL_TAG


class MessageView(VerticalScroll):
    """스크롤 가능한 채팅 메시지 뷰"""

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
        self._last_msg_count = 0
        self._auto_scroll = True

    def on_scroll_y(self) -> None:
        """스크롤 위치 변경 시 자동 스크롤 판단"""
        # 하단 근처(10px)면 auto_scroll 유지
        if self.scroll_y >= self.max_scroll_y - 2:
            self._auto_scroll = True
        else:
            self._auto_scroll = False

    def update_messages(self, messages: list[dict]) -> None:
        """메시지 리스트로 뷰 업데이트"""
        msg_count = len(messages)
        if msg_count == self._last_msg_count:
            return
        self._last_msg_count = msg_count

        # 기존 콘텐츠 제거 후 재구성
        self.remove_children()
        last_date = None

        for msg in messages:
            ts = msg.get("timestamp", "")
            msg_type = msg.get("type", "")
            text = msg.get("text", "")
            channel = msg.get("channel", msg.get("source", "telegram"))

            # 날짜/시간 파싱
            try:
                dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                date_str = dt.strftime("%Y/%m/%d")
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                date_str = ""
                time_str = "??:??"

            # 날짜 구분선
            if date_str and date_str != last_date:
                last_date = date_str
                self.mount(Static(
                    f"[dim]── {date_str} ──[/dim]",
                    classes="date-sep",
                ))

            # 발신자 헤더
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

            # 본문
            if text:
                self.mount(Static(f"  {text}", classes="msg-body"))

            # 파일 첨부
            files = msg.get("files", [])
            for fi in files:
                fname = fi.get("name") or fi.get("type", "file")
                self.mount(Static(f"  📎 {fname}", classes="msg-body"))

        # 자동 스크롤
        if self._auto_scroll:
            self.call_after_refresh(self.scroll_end, animate=False)
