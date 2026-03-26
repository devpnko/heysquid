# SQUID Tips & Tricks

SQUID를 더 잘 쓰는 방법 모음.

---

## 옵시디언에서 런타임 데이터 보기

SQUID의 런타임 데이터(`data/`)는 프로젝트 내부에 있어서 옵시디언 Vault와 직접 연결이 안 됨.

**심링크로 연결하기:**

```bash
ln -s /Users/hyuk/heysquid/data /path/to/your/vault/heysquid/_data
```

이러면 옵시디언에서 `_data/` 폴더로 session_memory, permanent_memory, kanban 등 런타임 파일을 바로 열어볼 수 있음.

> 💡 `_data`처럼 언더스코어 prefix를 쓰면 옵시디언 검색에서 제외하기 편함.

---

## LIVE vs STANDBY 차이

TUI 헤더에 `● LIVE`와 `● STANDBY`가 표시됨.

| 상태 | 의미 | 응답 속도 |
|------|------|----------|
| **LIVE** | executor가 실행 중. 5초마다 새 메시지 확인 | 빠름 (5~10초) |
| **STANDBY** | executor 꺼져있음. 메시지 오면 listener가 깨움 | 보통 (~10초, 콜드스타트) |

- STANDBY는 에러가 아님! 메시지 보내면 자동으로 LIVE가 됨
- 수동으로 켜려면: `bash scripts/run.sh start`
- LIVE 상태에서 일정 시간 메시지가 없으면 자동으로 STANDBY로 전환

---

## 주요 경로

```
/Users/hyuk/heysquid/
├── data/           → 런타임 데이터 (session_memory, permanent_memory, kanban, schedule...)
├── tasks/          → 작업 메모리 (msg별 task_info, 결과물)
├── workspaces/     → 프로젝트별 컨텍스트
├── logs/           → 실행 로그
└── scripts/run.sh  → 데몬 시작/중지/상태 확인
```

---

## TUI 단축키

| 키 | 기능 |
|----|------|
| `Ctrl+1~5` | 화면 전환 (Chat, Kanban, Squad, Log, Auto) |
| `Shift+Tab` | 다음 탭으로 이동 (Ctrl+숫자가 안 될 때 대안) |
| `Ctrl+←/→` | 이전/다음 화면 |
| `Tab` | 입력창 포커스 |
| `q` | 종료 (입력창에 텍스트 없을 때) |
| `Ctrl+C` | 선택 텍스트 복사 |

### AUTO 화면 (Ctrl+5)

| 키 | Level 0 (Automations) | Level 2 (FanMolt Agents) |
|----|----------------------|--------------------------|
| `↑↓` | 항목 선택 | 에이전트 선택 |
| `Enter` | fanmolt → 드릴다운 | - |
| `Esc` | - | Level 0 복귀 |
| `r` | automation 실행 | 에이전트 heartbeat |
| `t` | enable/disable 토글 | - |
| `p` | - | force post |

### AUTO 명령어 (하단 입력창)

```
run <name>              automation 또는 에이전트 실행
toggle <name>           automation 활성/비활성 토글
post <handle> [recipe]  에이전트 강제 포스팅
stats                   FanMolt 전체 통계
```

---

## WSL2 환경 Playwright 주의사항

Mac과 달리 WSL2에는 물리 모니터가 없어서 `headless=False`로 실행하면 크롬이 뜨지 않음.

### 증상

```
Looks like you launched a headed browser without having a XServer running.
Set either 'headless: true' or use 'xvfb-run <your-playwright-app>'
playwright._impl._errors.TargetClosedError: BrowserType.launch_persistent_context
```

### 규칙

| 파일 | 설정 | 이유 |
|------|------|------|
| `scripts/threads_cron.py` | `headless=True` | cron 환경, X서버 없음 |
| `scripts/threads_engage.py` | `headless=True` | cron 환경, X서버 없음 |
| `scripts/threads_upload.py` | `headless=True`로 바꿔야 함 | 현재 False (수동 실행 시에만 사용) |

> Mac에서 테스트할 때는 `headless=False`도 됨. WSL2(에코비/리눅스 서버)에 배포할 땐 반드시 `True`로.

### 첫댓글(first_reply) 방식

게시 직후 피드에서 입력창을 찾으면 엉뚱한 입력창이 잡힘.
→ 반드시 **프로필 이동 후 최신 글에서 Reply 버튼** 클릭 방식으로.

```python
# ✅ 올바른 방식
page.goto(f"https://www.threads.net/@{account}")
btns = page.query_selector_all('svg[aria-label="Reply"]')
btns[0].click()  # 최신 글의 첫 번째 reply 버튼

# ❌ 게시 직후 피드에서 찾는 방식 (실패함)
page.wait_for_selector('[contenteditable="true"]')  # 작성창이 잡힘
```

### xvfb-run 대안

어쩔 수 없이 headed가 필요하면 `xvfb-run` 사용:

```bash
xvfb-run -a python3 scripts/threads_engage.py collect
```
