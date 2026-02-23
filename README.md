# heysquid

Your personal PM agent powered by Claude Code.

텔레그램 기반 개인 PM 에이전트 시스템.
메시지를 보내면, 대화하고 → 계획 세우고 → 실행하고 → 대기한다.

## Quick Start

```bash
pip install heysquid
heysquid init       # Interactive setup wizard
heysquid start      # Start daemon
heysquid status     # Check status
```

## 에이전트 팀

PM(SQUID)이 5명의 전문 에이전트를 운영한다.

| 역할 | 동물 | 모델 | 담당 |
|------|------|------|------|
| 🦑 PM | squid | Opus | 총괄, 의사결정 |
| 🐙 researcher | octopus | Haiku | 탐색, 조사 |
| 🦈 developer | shark | Opus | 구현, 코딩 |
| 🐢 reviewer | turtle | Sonnet | 리뷰, 검토 |
| 🐡 tester | pufferfish | Haiku | 테스트, QA |
| 🦞 writer | lobster | Sonnet | 콘텐츠 작성 |

## 아키텍처

```
Telegram → Listener → Executor → Claude Code (PM) → Telegram
                                       ↕
                              Memory (permanent/session/workspace)
                                       ↕
                              Dashboard (agent_status.json → HTML)
```

## 패키지 구조

```
heysquid/
├── core/                    # 핵심 인프라
│   ├── agents.py            # 에이전트 레지스트리 (Single Source of Truth)
│   ├── config.py            # 환경변수, 설정
│   ├── paths.py             # 경로 상수
│   ├── hub.py               # PM 허브
│   ├── workspace.py         # 멀티 프로젝트 관리
│   ├── cli.py               # CLI 진입점
│   ├── quick_check.py       # 메시지 유무 빠른 확인
│   ├── _job_flow.py         # 작업 흐름 제어
│   └── _working_lock.py     # 동시 작업 방지 잠금
│
├── channels/                # 메시징 채널
│   ├── telegram.py          # 텔레그램 봇 로직
│   ├── telegram_listener.py # 메시지 수신 + executor 트리거
│   ├── _msg_store.py        # 메시지 저장소
│   └── _base.py             # 채널 베이스
│
├── skills/                  # 스킬 모듈
│   ├── briefing/            # 뉴스 브리핑 스킬
│   │   ├── _news_fetcher.py # 뉴스 수집 (GeekNews, HN, TC, MIT)
│   │   ├── _news_scorer.py  # 뉴스 스코어링
│   │   └── _thread_drafter.py # 스레드 초안 작성
│   └── _base.py             # 스킬 베이스
│
├── memory/                  # 메모리 시스템
│   ├── session.py           # 세션 메모리 (휘발성)
│   ├── tasks.py             # 작업 메모리
│   └── recovery.py          # 크래시 복구
│
├── dashboard/               # 대시보드 연동
│   └── __init__.py          # agent_dashboard 래퍼
│
├── telegram_bot.py          # 통합 봇 API (하위 호환)
├── telegram_sender.py       # 메시지 발신
├── agent_dashboard.py       # 대시보드 상태 관리
└── briefing.py              # 브리핑 통합 (하위 호환)
```

## 디렉토리

```
heysquid/
├── heysquid/        # 핵심 패키지 (위 참조)
├── scripts/         # 실행 스크립트 (run.sh, setup.sh, executor.sh 등)
├── data/            # 런타임 데이터 (.gitignore)
├── tasks/           # 작업 메모리 (msg별 폴더)
├── workspaces/      # 프로젝트별 컨텍스트
└── logs/            # 실행 로그
```

## 사전 요구사항

- **macOS** (launchd 기반 데몬 사용)
- **Python 3.10+**
- **Claude Code CLI** (`claude` 명령어가 PATH에 있어야 함)
- **텔레그램 봇 토큰** ([@BotFather](https://t.me/BotFather)에서 발급)

## 설치

### 1. 자동 설치 (권장)

```bash
bash scripts/setup.sh
```

setup.sh가 하는 일:
1. Python 버전 확인
2. `venv/` 가상환경 생성
3. 의존성 설치 (`python-telegram-bot`, `python-dotenv`)
4. `.env.example` → `.env` 복사
5. `data/`, `tasks/`, `workspaces/`, `logs/` 디렉토리 생성
6. launchd plist 심볼릭 링크 등록

### 2. 환경변수 설정

`heysquid/.env` 파일을 편집한다:

```env
# 텔레그램 봇 토큰 (BotFather에서 발급)
TELEGRAM_BOT_TOKEN=your_bot_token_here

# 허용할 사용자 ID (쉼표로 구분하여 여러 명 가능)
TELEGRAM_ALLOWED_USERS=123456789

# 폴링 간격 (초) - 기본값: 10초
TELEGRAM_POLLING_INTERVAL=10
```

> 텔레그램 사용자 ID는 [@userinfobot](https://t.me/userinfobot)에서 확인할 수 있다.

### 3. 수동 설치 (setup.sh 없이)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r heysquid/requirements.txt
cp heysquid/.env.example heysquid/.env
# .env 편집 후
mkdir -p data tasks workspaces logs
```

## 사용법

### 데몬 시작/중지

```bash
bash scripts/run.sh start     # 데몬 시작
bash scripts/run.sh stop      # 데몬 중지
bash scripts/run.sh restart   # 재시작
bash scripts/run.sh status    # 상태 확인
bash scripts/run.sh logs      # 최근 로그 보기
```

`start` 시 다음이 실행된다:
- **listener** 데몬 등록 (launchd, 10초 폴링)
- **briefing** 스케줄 등록 (매일 09:00)
- **대시보드 서버** 시작 (`http://localhost:8420/dashboard.html`)

### 동작 흐름

```
1. 사용자가 텔레그램에 메시지 전송
2. listener가 10초 이내 감지
3. executor.sh 트리거 → Claude Code(PM 모드) 시작
4. PM이 메시지 읽고 판단:
   - 대화 → 바로 답변
   - 작업 요청 → 계획 설명 후 확인 요청
   - 확인/승인 → 에이전트 배치하여 작업 실행
5. 작업 완료 후 결과 텔레그램 전송
6. 영구 대기 루프 진입 (30초마다 새 메시지 확인)
```

### 텔레그램 명령어

작업 중 방향을 바꾸고 싶을 때, 아래 키워드를 보내면 즉시 중단된다:

**중단 키워드:** `멈춰` `스탑` `스톱` `중단` `그만` `취소` `잠깐만` `/stop`

```
사용자: "홈페이지 만들어줘"
SQUID:  "이렇게 할게요. 진행할까요?"
사용자: "응"
SQUID:  [작업 중...]
사용자: "멈춰"              ← 10초 이내 중단
SQUID:  "작업 중단했어요."
사용자: "랜딩페이지로 바꿔"  ← 새 지시
```

### 실시간 모니터링

```bash
# TUI 모니터 (터미널, 끼어들기 가능)
bash scripts/monitor.sh

# 대시보드 (브라우저)
open http://localhost:8420/dashboard.html

# 로그 실시간 확인
tail -f logs/executor.log
```

TUI 모니터는 curses 기반으로 의존성 없이 동작한다:
- `Tab` — Dashboard ↔ Stream 모드 전환
- `:stop` — 현재 작업 중단
- `:resume` — executor 재시작
- `:<텍스트>` — PM에게 메시지 전송
- `q` — TUI 종료

### 수동 테스트

```bash
source venv/bin/activate

# listener만 단독 실행 (메시지 수신 테스트)
python heysquid/telegram_listener.py

# executor 수동 실행
bash scripts/executor.sh
```

## 주요 기능

- **텔레그램 소통** — 대화/계획/실행 3단계 흐름, 영구 대기 루프
- **뉴스 브리핑** — 4개 소스(GeekNews, HN, TechCrunch, MIT) 수집 + 5기준 스코어링
- **스레드 자동화** — Playwright 기반 Threads 글 게시/답글
- **대시보드** — 에이전트 상태 실시간 시각화 (`http://localhost:8420`)
- **크래시 복구** — 작업 중 세션이 죽으면 다음 세션에서 자동 감지 및 복구
- **작업 중단** — 텔레그램에서 "멈춰", "스탑" 등 키워드로 즉시 중단
- **멀티 워크스페이스** — 여러 프로젝트를 전환하며 작업

## data/ 디렉토리

런타임 데이터로 `.gitignore`에 포함되어 있다.

| 파일 | 설명 |
|------|------|
| `identity.json` | 봇 + 사용자 정체성 |
| `agent_status.json` | 에이전트 상태 (대시보드 연동) |
| `telegram_messages.json` | 수신 메시지 저장 |
| `permanent_memory.md` | 영구 기억 (사용자 선호, 교훈) |
| `session_memory.md` | 세션 기억 (대화 로그, 활성 작업) |
| `dashboard.html` | 대시보드 HTML |
| `threads_storage.json` | Threads 세션 (쿠키/스토리지) |
| `team_playbook.md` | 에이전트 배치 가이드 |

## 메모리 시스템

- `data/permanent_memory.md` — 영구 기억. 세션을 넘어 유지되는 핵심 결정과 교훈.
- `data/session_memory.md` — 세션 기억. 현재 대화 맥락과 활성 작업.
- `workspaces/{name}/context.md` — 프로젝트별 컨텍스트.
- `tasks/msg_{id}/` — 작업별 메모리와 결과물.

## 라이선스

Apache License 2.0 — 자세한 내용은 [LICENSE](LICENSE) 파일 참조.
