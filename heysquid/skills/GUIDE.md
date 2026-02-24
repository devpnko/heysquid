# 스킬 & Automation 작성 가이드

## Automation vs Skill

| | Automation | Skill |
|--|-----------|-------|
| **위치** | `heysquid/automations/` | `heysquid/skills/` |
| **성격** | 자동 반복 (schedule/interval) | 수동 호출 역량 |
| **트리거** | `schedule`, `interval` | `manual`, `webhook` |
| **예시** | briefing, threads_post | deep_work, marketing, saju_fortune |
| **대시보드** | Kanban Automation 컬럼 | - |

## 구조

```
heysquid/
├── core/
│   ├── plugin_loader.py  # 공유 discovery + runner 엔진
│   └── http_utils.py     # HTTP 유틸리티 (get_secret, http_get, ...)
├── automations/           # 자동 반복 (schedule/interval)
│   ├── __init__.py
│   ├── briefing/
│   └── threads_post/
├── skills/                # 수동 호출 역량
│   ├── __init__.py
│   ├── _base.py           # core/plugin_loader 위임
│   ├── _http.py           # core/http_utils 위임 (backward compat)
│   ├── GUIDE.md           # 이 파일
│   ├── deep_work/
│   ├── marketing/
│   └── saju_fortune/
```

## 새 Automation 만들기

```python
# heysquid/automations/my_automation/__init__.py

SKILL_META = {
    "name": "my_automation",
    "description": "매일 9시에 실행되는 자동 작업",
    "trigger": "schedule",      # "schedule" | "interval"
    "schedule": "09:00",        # trigger=schedule일 때 HH:MM
    "enabled": True,
    "icon": "⏰",
}

def execute(**kwargs):
    # 여기에 로직
    return {"done": True}
```

## 새 Skill 만들기

```python
# heysquid/skills/my_skill/__init__.py

SKILL_META = {
    "name": "my_skill",
    "description": "이 스킬이 뭘 하는지",
    "trigger": "manual",       # "manual" | "webhook"
    "enabled": True,
    "icon": "🔧",
}

def execute(**kwargs):
    # 여기에 로직
    return {"done": True}
```

## SKILL_META 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | O | 식별자 (폴더명과 동일) |
| `description` | O | 설명 |
| `trigger` | O | `"manual"`, `"schedule"`, `"interval"`, `"webhook"` |
| `schedule` | trigger=schedule일 때 | `"HH:MM"` 형식 (예: `"09:00"`) |
| `enabled` | - | 기본 `True`. `False`면 비활성화 |
| `icon` | - | 대시보드 Machine Room 아이콘 |
| `workspace` | - | 연결 워크스페이스 이름 |

---

## execute() 함수

```python
def execute(triggered_by="scheduler", chat_id=0, args="",
            payload=None, callback_url="", **kwargs):
    """
    Args:
        triggered_by: 누가 실행했는지 ("scheduler" | "manual" | "pm" | "webhook")
        chat_id: 텔레그램 chat_id (알림 보낼 때 사용)
        args: 문자열 인자 (TUI에서 `/skill my_skill 인자`)
        payload: dict (webhook에서 받은 JSON body)
        callback_url: 완료 후 POST할 URL (n8n 등)
        **kwargs: 미래 확장용 — 반드시 받아야 함

    Returns:
        dict 또는 아무 값. run_skill()/run_automation()이 {"ok": True, "result": 반환값}으로 감싸줌.
        예외 발생 시 {"ok": False, "error": 메시지}로 자동 처리.
    """
```

`**kwargs`를 반드시 넣어야 PluginContext에 필드가 추가돼도 기존 플러그인이 안 깨집니다.

---

## HTTP 유틸리티

외부 API 호출 시 직접 `requests` 쓰지 말고 이걸 사용:

```python
from heysquid.core.http_utils import get_secret, http_get, http_post_json, http_post_form

# 환경변수에서 시크릿 로드
token = get_secret("MY_API_TOKEN")

# GET
data = http_get("https://api.example.com/data", token=token)

# POST JSON
result = http_post_json("https://api.example.com/create",
                        payload={"key": "value"}, token=token)

# POST form-encoded (레거시 API용)
result = http_post_form("https://api.example.com/submit",
                        data={"field": "value"}, token=token)
```

기존 `from heysquid.skills._http import ...` 도 여전히 동작합니다 (backward compat).

---

## 실행 방법

### 1. 스케줄러 (Automation 자동)
`trigger: "schedule"`, `schedule: "09:00"` → 매일 9시 자동 실행

### 2. TUI 수동
```
/skill my_skill
/skill my_skill 인자
```

### 3. PM이 직접
```python
# Automation
from heysquid.automations import run_automation
from heysquid.core.plugin_loader import PluginContext
ctx = PluginContext(triggered_by="pm", chat_id=12345)
result = run_automation("briefing", ctx)

# Skill
from heysquid.skills import run_skill, SkillContext
ctx = SkillContext(triggered_by="pm", chat_id=12345, args="인자")
result = run_skill("my_skill", ctx)
```

### 4. Webhook (외부 트리거)
```bash
curl -X POST http://localhost:8585/webhook/briefing \
  -H "X-Webhook-Secret: 시크릿" \
  -H "Content-Type: application/json" \
  -d '{"args": "인자", "chat_id": 12345}'
```

Webhook은 automations 먼저 찾고, 없으면 skills에서 찾습니다.

---

## config 오버라이드

`data/skills_config.json`으로 코드 수정 없이 설정 변경:

```json
{
  "briefing": {
    "schedule": "08:30",
    "enabled": false
  }
}
```

automations와 skills 모두 동일한 config 파일 사용.
