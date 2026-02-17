# heysquid

Your personal PM agent, connected via Telegram.

## What is heysquid?

Mac에서 실행되는 Claude Code 기반 PM 에이전트.
텔레그램으로 메시지를 보내면, 대화하고 → 계획 세우고 → 실행하고 → 대기한다.

## Architecture

```
Telegram → Listener → Executor → Claude Code (PM mode) → Telegram
                                       ↕
                              Memory (permanent/session/workspace)
```

## Quick Start

1. `bash scripts/setup.sh`
2. `heysquid/.env`에서 봇 토큰 + 사용자 ID 설정
3. `bash scripts/run.sh start`
4. 텔레그램에서 메시지 전송

## Commands

- `bash scripts/run.sh start` — 데몬 시작
- `bash scripts/run.sh stop` — 데몬 중지
- `bash scripts/run.sh status` — 상태 확인
- `bash scripts/run.sh logs` — 로그 확인
- `bash scripts/monitor.sh` — 실시간 TUI 모니터

## Structure

```
/Users/hyuk/ohmyclawbot/
├── heysquid/                # 핵심 코드
│   ├── telegram_listener.py # 메시지 수신 + executor 트리거
│   ├── telegram_sender.py   # 메시지 발신
│   ├── telegram_bot.py      # 통합 봇 로직
│   ├── quick_check.py       # 메시지 유무 확인
│   ├── workspace.py         # 멀티 프로젝트 관리
│   ├── briefing.py          # 일일 브리핑
│   └── .env                 # 환경변수
├── scripts/                 # 실행 스크립트
├── data/                    # 런타임 데이터
│   ├── identity.json        # 봇 + 사용자 정체성
│   └── telegram_messages.json
├── tasks/                   # 작업 메모리
├── workspaces/              # 프로젝트별 컨텍스트
└── logs/                    # 실행 로그
```

## Telegram Commands

### 작업 중단

작업 실행 중에 잘못된 지시를 내렸거나 방향을 바꾸고 싶을 때, 아래 키워드를 텔레그램으로 보내면 즉시 중단된다.

**중단 키워드:** `멈춰` `스탑` `스톱` `중단` `그만` `취소` `잠깐만` `/stop`

```
사용자: "홈페이지 만들어줘"
squid:  "이렇게 할게요. 진행할까요?"
사용자: "응"
squid:  [작업 시작... 에이전트 배치 중...]
사용자: "멈춰"                          ← 즉시 중단
squid:  "작업 중단했어요.
         중단된 작업: 홈페이지 만들어줘
         새로운 지시를 보내주세요."
사용자: "홈페이지 말고 랜딩페이지로 해줘"  ← 새 지시
squid:  "랜딩페이지로 바꿔서 진행할게요..."
```

**동작 원리:**

```
"멈춰" 전송
  ↓
listener가 감지 (10초 이내)
  ↓
executor Claude 프로세스 kill
  ↓
working.json + executor.lock 정리
  ↓
interrupted.json 저장 (중단된 작업 정보)
  ↓
"작업 중단했어요" 알림 전송
  ↓
다음 메시지 → 새 세션 시작 → 중단 맥락 인지
```

**주의:**
- 중단은 10초 이내에 처리된다 (listener 폴링 간격)
- 중단 후 진행 중이던 작업의 부분 결과는 사라질 수 있음
- 실행 중인 작업이 없을 때 보내면 "실행 중인 작업이 없어요"로 응답

## Agent Team

PM이 직접 모든 걸 하지 않는다.
전문 에이전트에게 위임하고, 결과를 종합하여 보고한다.

| Agent | Model | Role |
|-------|-------|------|
| researcher | Haiku | 탐색/분석 |
| developer | Opus | 구현/수정 |
| reviewer | Sonnet | 리뷰 |
| tester | Haiku | 테스트 |

## Memory

- `data/permanent_memory.md` — 영구 기억 (사용자 선호, 교훈)
- `data/session_memory.md` — 세션 기억 (대화 로그, 활성 작업)
- `workspaces/{name}/context.md` — 프로젝트별 컨텍스트
