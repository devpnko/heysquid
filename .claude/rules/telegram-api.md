# 채널 API 요약 + 멀티 워크스페이스

## 응답 API — 반드시 broadcast 함수만 사용!

**중요: 사용자에게 응답할 때 send_message_sync()를 직접 쓰지 마라.**
send_message_sync()는 텔레그램 한 채널에만 전송된다.
사용자가 TUI/Telegram/어디서 메시지를 보내든, 응답은 **모든 채널**에 도착해야 한다.

```python
# ✅ 올바른 방법 — 모든 채널에 브로드캐스트
from telegram_bot import reply_telegram  # = reply_broadcast의 래퍼
reply_telegram(chat_id, message_id, "텍스트")

# ❌ 절대 금지 — 텔레그램에만 전송됨. 다른 채널 누락!
# from telegram_sender import send_message_sync

# 메시지 확인 → 작업 흐름
from telegram_bot import check_telegram, pick_next_task
from telegram_bot import create_working_lock, remove_working_lock
from telegram_bot import reserve_memory_telegram
from telegram_bot import report_telegram  # (instruction, result_text, chat_id, timestamps, message_ids, files=[])
from telegram_bot import mark_done_telegram
from telegram_bot import load_memory, poll_new_messages

# 세션 메모리
from telegram_bot import load_session_memory, compact_session_memory, save_session_summary

# 세션 시작 시 — 크래시/중단 복구
from telegram_bot import check_crash_recovery, check_interrupted
```

## 멀티 워크스페이스 (workspace.py)

여러 프로젝트를 전환하며 작업할 수 있다.

```python
from workspace import (
    list_workspaces,       # 프로젝트 목록
    get_workspace,         # 특정 프로젝트 정보
    switch_workspace,      # 전환 + context.md 반환
    register_workspace,    # 새 프로젝트 등록
    update_progress,       # 진행 상태 기록
)
```

- 사용자가 프로젝트를 언급하면 `switch_workspace()`로 전환
- `check_telegram()`이 메시지에서 자동으로 워크스페이스 감지
