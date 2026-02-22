# 텔레그램 API 요약 + 멀티 워크스페이스

## 텔레그램 API

```python
# 대화용 간편 응답
from telegram_bot import reply_telegram
reply_telegram(chat_id, message_id, "텍스트")

# 직접 메시지 전송
from telegram_sender import send_message_sync
send_message_sync(chat_id, "텍스트")

# 새 메시지 확인
from telegram_bot import check_telegram
pending = check_telegram()

# 메시지 합산
from telegram_bot import combine_tasks
combined = combine_tasks(pending)

# 작업 잠금/해제
from telegram_bot import create_working_lock, remove_working_lock
create_working_lock(message_ids, instruction)
remove_working_lock()

# 메모리 예약
from telegram_bot import reserve_memory_telegram
reserve_memory_telegram(instruction, chat_id, timestamps, message_ids)

# 결과 리포트
from telegram_bot import report_telegram
report_telegram(instruction, result_text, chat_id, timestamps, message_ids, files=[])

# 처리 완료
from telegram_bot import mark_done_telegram
mark_done_telegram(message_ids)

# 기존 메모리 조사
from telegram_bot import load_memory
memories = load_memory()

# 대기 루프용 — 새 메시지 경량 확인
from telegram_bot import poll_new_messages
new_msgs = poll_new_messages()

# 세션 메모리 — 시작 시 로드, 50개 초과 시 정리 (톤/이벤트 자동 요약 포함)
from telegram_bot import load_session_memory, compact_session_memory
memory = load_session_memory()
compact_session_memory()

# 세션 종료 시 핵심 3줄 기록 — permanent_memory에 오늘의 핵심 저장
from telegram_bot import save_session_summary
save_session_summary()

# 크래시 복구 — 세션 시작 시 호출
from telegram_bot import check_crash_recovery
recovery = check_crash_recovery()
# recovery가 있으면: 이전 작업 중단됨. instruction, original_messages 참고.

# 사용자 중단 확인 — 세션 시작 시 호출
from telegram_bot import check_interrupted
interrupted = check_interrupted()
# interrupted가 있으면: 사용자가 의도적으로 중단한 것.
# interrupted["previous_work"]에 중단된 작업 정보.
# 이전 작업을 이어서 하지 않음. 새 메시지를 확인.
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
