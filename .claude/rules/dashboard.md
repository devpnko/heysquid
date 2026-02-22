# 대시보드 실시간 로깅

작업 중 주요 단계마다 대시보드에 로그를 남긴다. 이 로그는:
- `data/agent_status.json`의 `mission_log`에 기록됨
- 대시보드 HTML이 3초마다 읽어서 표시
- 해당 에이전트 아바타 위에 말풍선으로도 표시

## 로깅 함수

```python
from telegram_bot import _dashboard_log
from agent_dashboard import add_mission_log, dispatch_agent, recall_agent, set_current_task

# PM 로그 (자동 호출 — telegram_bot.py에 내장)
# check_telegram() → "Message received"
# create_working_lock() → "Starting: [작업명]"
# report_telegram() → "Mission complete"
# remove_working_lock() → "Standing by..."

# 수동 로그 (작업 중 주요 단계에서 호출)
_dashboard_log('pm', 'Analyzing request...')
_dashboard_log('pm', 'Reading dashboard HTML...')
_dashboard_log('pm', 'Editing CSS...')

# 에이전트 배치 시
dispatch_agent('researcher', 'thread', 'Scanning feed')  # 데스크로 이동 + 로그
recall_agent('researcher', 'Feed analysis done')          # 풀로 복귀 + 로그

# 현재 작업명 (대시보드 상단에 표시)
set_current_task('Dashboard v5 — flinch fix')
```

## 로깅 타이밍 (PM이 지켜야 할 것)

| 시점 | 로그 예시 |
|------|----------|
| 메시지 수신 | 자동 (check_telegram) |
| 작업 시작 | 자동 (create_working_lock) |
| 파일 읽기 | `_dashboard_log('pm', 'Reading [파일명]')` |
| 파일 수정 | `_dashboard_log('pm', 'Editing [파일명]')` |
| 외부 호출 | `_dashboard_log('pm', 'Calling [서비스]')` |
| 에이전트 배치 | `dispatch_agent(...)` |
| 에이전트 복귀 | `recall_agent(...)` |
| 중간 보고 | `_dashboard_log('pm', 'Progress: 50%...')` |
| 작업 완료 | 자동 (report_telegram) |
| 대기 진입 | 자동 (remove_working_lock) |

**핵심**: 사용자가 대시보드를 볼 때, PM과 에이전트가 뭘 하고 있는지 실시간으로 알 수 있어야 한다.
