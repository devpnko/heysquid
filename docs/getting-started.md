# Getting Started

진짜로 처음부터 끝까지, 따라만 하면 되는 설치 가이드입니다.

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | ✅ Fully supported | launchd 기반 데몬, 네이티브 지원 |
| **Linux** | ⚠️ Planned | systemd 지원 개발 예정 |
| **Windows** | ⚠️ WSL required | 네이티브 Windows는 미지원. WSL2 Ubuntu에서 사용 가능 |

> **Windows 유저**: WSL2를 설치한 후 Ubuntu 터미널에서 아래 "Linux/WSL" 가이드를 따르세요.
> WSL2 설치법: `wsl --install` (PowerShell 관리자 모드에서 실행)

---

## Step 0: 기본 도구 설치

heysquid를 설치하기 전에 3가지가 필요합니다: **Homebrew** (macOS만), **Node.js**, **Python**.

이미 설치되어 있다면 각 "확인" 명령어로 버전만 체크하고 넘어가세요.

### 0-1. Homebrew (macOS만)

macOS에서 프로그램을 설치하는 패키지 매니저입니다.

**확인:**
```bash
brew --version
```

**없으면 설치:**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

설치 후 터미널에 나오는 "Next steps" 안내대로 PATH를 추가하세요. 보통 이렇게 나옵니다:
```bash
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### 0-2. Node.js (18 이상)

Claude Code CLI가 Node.js로 만들어져 있어서 필요합니다.

**확인:**
```bash
node --version   # v18.x 이상이면 OK
npm --version    # 같이 설치됨
```

**없으면 설치:**

macOS:
```bash
brew install node
```

Linux/WSL:
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

> 💡 nvm을 쓰고 있다면 `nvm install 20 && nvm use 20`으로도 됩니다.

### 0-3. Python (3.10 이상)

heysquid가 Python으로 만들어져 있습니다.

**확인:**
```bash
python3 --version   # 3.10 이상이면 OK
```

**없으면 설치:**

macOS:
```bash
brew install python@3.12
```

Linux/WSL:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

> 💡 macOS에는 시스템 Python이 있지만 버전이 낮을 수 있습니다. `python3 --version`이 3.10 미만이면 brew로 설치하세요.

---

## Step 1: Claude Code CLI 설치

heysquid의 두뇌입니다. 모든 AI 작업이 Claude Code를 통해 실행됩니다.

```bash
npm install -g @anthropic-ai/claude-code
```

**확인:**
```bash
claude --version
```

> ⚠️ `npm: command not found` → Step 0-2로 돌아가서 Node.js를 먼저 설치하세요.
>
> ⚠️ `EACCES: permission denied` → macOS에서 발생 시:
> ```bash
> sudo npm install -g @anthropic-ai/claude-code
> ```
> 또는 npm 글로벌 디렉토리 권한을 수정하세요:
> ```bash
> mkdir -p ~/.npm-global
> npm config set prefix '~/.npm-global'
> echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
> source ~/.zshrc
> ```

### Claude 구독

Claude Code CLI 자체는 무료이지만, 실제 사용하려면 Anthropic 계정 + 구독이 필요합니다.

| Plan | 가격 | heysquid 사용 |
|------|------|--------------|
| Claude Pro | $20/mo | ⚠️ 일일 한도 있음 (테스트용) |
| Claude Max | $100/mo | ✅ 추천 (무제한, 항상 켜기 가능) |

첫 실행 시 `claude` 명령어를 입력하면 브라우저에서 로그인 화면이 열립니다.

---

## Step 2: heysquid 설치

```bash
pip3 install heysquid
```

**확인:**
```bash
heysquid --help
```

> ⚠️ `heysquid: command not found` 가 나오면:
>
> **방법 1** — pip가 설치한 위치를 PATH에 추가:
> ```bash
> # macOS
> echo 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"' >> ~/.zshrc
> source ~/.zshrc
>
> # Linux/WSL
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
> source ~/.bashrc
> ```
>
> **방법 2** — python 모듈로 직접 실행:
> ```bash
> python3 -m heysquid.core.cli --help
> ```
>
> **방법 3** — pipx 사용 (경로 문제 없음):
> ```bash
> pip3 install pipx
> pipx install heysquid
> ```

**선택: 추가 채널 설치**
```bash
pip3 install 'heysquid[all]'    # Telegram + Slack + Discord + TUI 전부
pip3 install 'heysquid[slack]'  # Slack만 추가
pip3 install 'heysquid[tui]'   # 터미널 UI만 추가
```

---

## Step 3: Telegram 봇 만들기

heysquid와 대화할 채널을 만듭니다. 3분이면 됩니다.

### 3-1. 봇 생성

1. 핸드폰(또는 PC)에서 Telegram을 열고 **@BotFather**를 검색
2. `/newbot` 입력
3. 봇 이름 입력 (예: `My SQUID`)
4. 봇 사용자명 입력 (예: `my_squid_bot` — 반드시 `_bot`으로 끝나야 함)
5. **토큰**이 나옵니다. 복사해두세요.

```
Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 3-2. 내 User ID 확인

1. Telegram에서 **@userinfobot**을 검색
2. 아무 메시지나 보내면 내 ID가 나옵니다

```
Your user ID: 987654321
```

이 두 값(토큰 + User ID)을 기억해두세요.

---

## Step 4: heysquid 초기 설정

```bash
heysquid init
```

대화형 마법사가 순서대로 물어봅니다:

```
🦑 heysquid setup

Telegram bot token: [Step 3에서 복사한 토큰 붙여넣기]
Telegram user ID: [Step 3에서 복사한 User ID 붙여넣기]
Slack token (Enter to skip): [엔터]
Discord token (Enter to skip): [엔터]

✅ Setup complete!
```

이 과정에서 생성되는 것들:
- `data/.env` — 토큰 저장
- `data/identity.json` — 봇 정체성
- `data/permanent_memory.md` — 장기 기억
- 각종 디렉토리 (`tasks/`, `workspaces/`, `logs/`)

---

## Step 5: 시작!

```bash
heysquid start
```

```
✅ Watcher daemon started
✅ Scheduler daemon started
```

상태 확인:
```bash
heysquid status
```

---

## Step 6: 첫 대화

Telegram에서 봇에게 메시지를 보내세요:

```
안녕!
```

10초 이내에 SQUID가 응답합니다. 축하합니다! 🎉

### 해볼 것들

```
# 간단한 작업 요청
"오늘 날씨 알려줘"

# FanMolt AI 크리에이터 만들기
"fanmolt create TechDigest AI/테크 뉴스 크리에이터"

# 상태 확인
"fanmolt list"
```

터미널 UI로 모니터링:
```bash
heysquid tui
```

---

## 일상 사용

```bash
# 시작 (부팅 후 1번)
heysquid start

# 상태 확인
heysquid status

# 로그 보기 (실시간)
heysquid logs -f

# 터미널 UI
heysquid tui

# 정지
heysquid stop

# 재시작
heysquid restart
```

heysquid는 데몬이라 `heysquid start` 후에는 터미널을 닫아도 계속 동작합니다.
맥을 재부팅하면 `heysquid start`를 다시 실행하면 됩니다.

---

## Troubleshooting

### "command not found: heysquid"

pip가 설치한 실행 파일이 PATH에 없는 경우. Step 2의 해결법 참고.

빠른 확인:
```bash
python3 -c "import heysquid; print('OK')"   # 패키지는 설치됨?
python3 -m heysquid.core.cli status          # 직접 실행
```

### "command not found: claude"

Node.js 또는 Claude Code CLI가 설치되지 않은 경우.

```bash
node --version     # Node.js 확인
npm --version      # npm 확인
npm list -g @anthropic-ai/claude-code   # Claude Code 확인
```

없으면 Step 0-2, Step 1로 돌아가세요.

### "command not found: brew"

macOS에 Homebrew가 없는 경우. Step 0-1 참고.
또는 brew 없이 직접 설치:
```bash
# Node.js — 공식 사이트에서 .pkg 다운로드
# https://nodejs.org

# Python — 공식 사이트에서 .pkg 다운로드
# https://www.python.org/downloads/
```

### "permission denied" 또는 "EACCES"

macOS에서 글로벌 npm 설치 시 권한 문제:
```bash
sudo npm install -g @anthropic-ai/claude-code
```

또는 pip에서:
```bash
pip3 install --user heysquid
```

### 봇이 응답하지 않음

1. 데몬 상태 확인: `heysquid status`
2. 로그 확인: `heysquid logs -f`
3. `.env` 파일에 토큰이 맞는지 확인
4. `TELEGRAM_ALLOWED_USERS`에 내 User ID가 있는지 확인
5. Claude Code 로그인 상태 확인: `claude --version`

### "ModuleNotFoundError: No module named 'telegram'"

python-telegram-bot이 설치되지 않은 경우:
```bash
pip3 install python-telegram-bot>=20.0
```

또는 heysquid를 재설치:
```bash
pip3 install --force-reinstall heysquid
```

### Windows에서 사용하고 싶어요

heysquid는 macOS launchd 기반이라 Windows에서 직접 실행이 안 됩니다.

**WSL2 사용 (권장):**
1. PowerShell (관리자)에서: `wsl --install`
2. 재부팅
3. Ubuntu 터미널이 열리면, 이 가이드의 "Linux/WSL" 명령어를 따르세요
4. WSL 안에서 `heysquid start` 실행

**참고**: WSL2에서는 launchd 대신 직접 프로세스를 실행하는 방식을 사용합니다.
Linux/systemd 네이티브 지원은 개발 예정입니다.

---

## What's Next

- **[FanMolt Guide](fanmolt-guide.md)** — AI 크리에이터를 만들어서 자동으로 콘텐츠 생성 + 수익화
- **[Plugin Guide](../heysquid/skills/GUIDE.md)** — 커스텀 스킬/자동화 만들기
- **[Contributing](../CONTRIBUTING.md)** — 개발에 기여하기
