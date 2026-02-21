# 스킬 작성 가이드

## 구조

```
heysquid/skills/
├── _base.py          # 프레임워크 (discover, run_skill)
├── _http.py          # HTTP 유틸리티 (get_secret, http_get, http_post_json, ...)
├── __init__.py       # exports
├── GUIDE.md          # 이 파일
├── briefing/         # 스킬 예시 (스케줄)
│   └── __init__.py
└── 새_스킬/          # ← 폴더 만들면 자동 감지
    └── __init__.py
```

## 새 스킬 만들기 (3단계)

### 1. 폴더 + `__init__.py` 생성

```python
# heysquid/skills/my_skill/__init__.py

SKILL_META = {
    "name": "my_skill",
    "description": "이 스킬이 뭘 하는지",
    "trigger": "manual",       # "manual" | "schedule"
    "enabled": True,
    "icon": "🔧",              # 대시보드 아이콘 (선택)
}

def execute(**kwargs):
    # 여기에 로직
    return {"done": True}
```

### 2. (외부 API면) `.env`에 키 추가

```
# heysquid/.env
MY_API_TOKEN=xxxxx
```

### 3. 끝

스케줄러가 `discover_skills()`로 자동 감지합니다.

---

## SKILL_META 필드

| 필드 | 필수 | 설명 |
|------|------|------|
| `name` | O | 스킬 식별자 (폴더명과 동일) |
| `description` | O | 설명 |
| `trigger` | O | `"manual"` 또는 `"schedule"` |
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
        dict 또는 아무 값. run_skill()이 {"ok": True, "result": 반환값}으로 감싸줌.
        예외 발생 시 {"ok": False, "error": 메시지}로 자동 처리.
    """
```

`**kwargs`를 반드시 넣어야 SkillContext에 필드가 추가돼도 기존 스킬이 안 깨집니다.

---

## HTTP 유틸리티 (`_http.py`)

외부 API 호출 시 직접 `requests` 쓰지 말고 이걸 사용:

```python
from heysquid.skills._http import get_secret, http_get, http_post_json, http_post_form

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

공통으로 타임아웃(30초), 인증 헤더, 에러 핸들링이 적용됩니다.

---

## 실행 방법 4가지

### 1. 스케줄러 (자동)
`trigger: "schedule"`, `schedule: "09:00"` → 매일 9시 자동 실행

### 2. TUI 수동
```
/skill my_skill
/skill my_skill 인자
```

### 3. PM이 직접
```python
from heysquid.skills import run_skill, SkillContext
ctx = SkillContext(triggered_by="pm", chat_id=12345, args="인자")
result = run_skill("my_skill", ctx)
```

### 4. Webhook (외부 트리거)
```bash
curl -X POST http://localhost:8585/webhook/my_skill \
  -H "X-Webhook-Secret: 시크릿" \
  -H "Content-Type: application/json" \
  -d '{"args": "인자", "chat_id": 12345}'
```

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

---

## 예시: 외부 API 스킬

```python
# heysquid/skills/buffer_post/__init__.py

from heysquid.skills._http import get_secret, http_post_form

SKILL_META = {
    "name": "buffer_post",
    "description": "Buffer에 소셜 미디어 포스트 예약",
    "trigger": "manual",
    "enabled": True,
    "icon": "📱",
}

def execute(args="", payload=None, **kwargs):
    token = get_secret("BUFFER_ACCESS_TOKEN")
    profile_id = get_secret("BUFFER_PROFILE_ID")
    text = args or (payload or {}).get("text", "")
    if not text:
        return {"error": "텍스트 없음"}

    result = http_post_form(
        "https://api.bufferapp.com/1/updates/create.json",
        data={"profile_ids[]": profile_id, "text": text},
        token=token,
    )
    return {"posted": True}
```

## 예시: n8n 워크플로우 트리거

```python
# heysquid/skills/n8n_trigger/__init__.py

from heysquid.skills._http import get_secret, http_post_json

SKILL_META = {
    "name": "n8n_trigger",
    "description": "n8n 워크플로우 웹훅 트리거",
    "trigger": "manual",
    "enabled": True,
    "icon": "🔗",
}

def execute(args="", payload=None, **kwargs):
    base_url = get_secret("N8N_BASE_URL")
    workflow = args.split()[0] if args else (payload or {}).get("workflow", "")
    if not workflow:
        return {"error": "워크플로우 이름 없음"}

    data = (payload or {}).copy()
    result = http_post_json(f"{base_url}/webhook/{workflow}", payload=data)
    return result
```
