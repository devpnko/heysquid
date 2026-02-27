# Getting Started

A truly step-by-step guide. Follow along and you'll have a working PM agent in 10 minutes.

## Platform Support

| Platform | Status | Notes |
|----------|--------|-------|
| **macOS** | ✅ Fully supported | Native launchd daemon |
| **Linux** | ⚠️ Planned | systemd support coming soon |
| **Windows** | ⚠️ WSL required | Native Windows not supported. Use WSL2 Ubuntu. |

> **Windows users**: Install WSL2 first, then follow the "Linux/WSL" instructions below.
> In PowerShell (admin): `wsl --install`, then reboot.

---

## Step 0: Install Prerequisites

heysquid needs three things: **Homebrew** (macOS only), **Node.js**, and **Python**.

Already have them? Run the "Check" command for each — if it prints a version, skip to the next.

### 0-1. Homebrew (macOS only)

A package manager for macOS. Makes installing everything else easy.

**Check:**
```bash
brew --version
```

**Install (if missing):**
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After install, follow the "Next steps" printed in your terminal. Usually:
```bash
echo >> ~/.zprofile
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

> **No Homebrew?** You can install Node.js and Python directly from their websites instead:
> - Node.js: [nodejs.org](https://nodejs.org) → download the `.pkg` installer
> - Python: [python.org](https://www.python.org/downloads/) → download the `.pkg` installer

### 0-2. Node.js (18+)

Claude Code CLI is built on Node.js.

**Check:**
```bash
node --version   # Should be v18.x or higher
npm --version    # Installed alongside Node.js
```

**Install (if missing):**

macOS:
```bash
brew install node
```

Linux/WSL:
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

> Already using nvm? `nvm install 20 && nvm use 20` works too.

### 0-3. Python (3.10+)

heysquid is written in Python.

**Check:**
```bash
python3 --version   # Should be 3.10 or higher
```

**Install (if missing):**

macOS:
```bash
brew install python@3.12
```

Linux/WSL:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

> macOS comes with a system Python, but it may be too old. If `python3 --version` shows 3.9 or lower, install a newer version with brew.

---

## Step 1: Install Claude Code CLI

This is the brain. All AI work runs through Claude Code.

```bash
npm install -g @anthropic-ai/claude-code
```

**Check:**
```bash
claude --version
```

> **Troubleshooting:**
>
> `npm: command not found` → Go back to Step 0-2 and install Node.js first.
>
> `EACCES: permission denied` → Fix with one of these:
> ```bash
> # Option A: Use sudo
> sudo npm install -g @anthropic-ai/claude-code
>
> # Option B: Fix npm permissions (permanent fix)
> mkdir -p ~/.npm-global
> npm config set prefix '~/.npm-global'
> echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
> source ~/.zshrc
> npm install -g @anthropic-ai/claude-code
> ```

### Claude Subscription

The CLI itself is free, but you need an Anthropic account with a subscription to use it.

| Plan | Price | For heysquid |
|------|-------|-------------|
| Claude Pro | $20/mo | Works, but has daily usage limits |
| Claude Max | $100/mo | Recommended — unlimited, always-on |

On first run, `claude` will open a browser window for login.

---

## Step 2: Install heysquid

```bash
pip3 install heysquid
```

**Check:**
```bash
heysquid --help
```

> **Troubleshooting:**
>
> `heysquid: command not found` — pip installed it somewhere not in your PATH. Three fixes:
>
> **Fix 1** — Add pip's bin directory to PATH:
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
> **Fix 2** — Run directly via Python:
> ```bash
> python3 -m heysquid.core.cli --help
> ```
>
> **Fix 3** — Use pipx (handles PATH automatically):
> ```bash
> pip3 install pipx
> pipx install heysquid
> ```

**Optional extras:**
```bash
pip3 install 'heysquid[all]'    # Telegram + Slack + Discord + TUI
pip3 install 'heysquid[slack]'  # Just Slack
pip3 install 'heysquid[tui]'   # Just the terminal UI
```

---

## Step 3: Create a Telegram Bot

This takes about 3 minutes. You'll create a bot and get two values: a **token** and your **user ID**.

### 3-1. Create the bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "My SQUID")
4. Choose a username (must end in `_bot`, e.g., `my_squid_bot`)
5. BotFather gives you a **token**. Copy it.

```
Use this token to access the HTTP API:
123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 3-2. Get your user ID

1. In Telegram, search for **@userinfobot**
2. Send any message
3. Copy the **user ID** number

```
Your user ID: 987654321
```

Keep both values — you'll need them in the next step.

---

## Step 4: Initialize heysquid

```bash
heysquid init
```

The interactive wizard asks for your tokens:

```
🦑 heysquid setup

Telegram bot token: [paste your token from Step 3-1]
Telegram user ID: [paste your user ID from Step 3-2]
Slack token (Enter to skip): [press Enter]
Discord token (Enter to skip): [press Enter]

✅ Setup complete!
```

This creates:
- `data/.env` — Your tokens (never committed to git)
- `data/identity.json` — Bot identity
- `data/permanent_memory.md` — Long-term memory
- Directories: `tasks/`, `workspaces/`, `logs/`

---

## Step 5: Start

```bash
heysquid start
```

```
✅ Watcher daemon started
✅ Scheduler daemon started
```

Verify:
```bash
heysquid status
```

---

## Step 6: Send Your First Message

Open Telegram and send a message to your bot:

```
Hello!
```

SQUID should respond within 10 seconds. You now have a personal PM agent. 🎉

### Things to try

On Telegram:
```
"What can you do?"

"fanmolt create TechDigest AI/tech news creator"

"fanmolt list"
```

From your terminal:
```bash
heysquid tui       # Interactive terminal UI
heysquid logs -f   # Follow live logs
```

---

## Daily Usage

```bash
heysquid start      # Start (run once after boot)
heysquid status     # Check what's running
heysquid logs -f    # Watch live logs
heysquid tui        # Terminal UI with kanban board
heysquid stop       # Stop all daemons
heysquid restart    # Stop + Start
```

heysquid runs as a daemon — closing your terminal doesn't stop it.
After a Mac reboot, just run `heysquid start` again.

---

## Troubleshooting

### "command not found: heysquid"

pip installed the binary somewhere not in your PATH. See Step 2 troubleshooting.

Quick check:
```bash
python3 -c "import heysquid; print('OK')"   # Is the package installed?
python3 -m heysquid.core.cli status          # Run directly
```

### "command not found: claude"

Node.js or Claude Code CLI not installed:
```bash
node --version                                # Node.js installed?
npm list -g @anthropic-ai/claude-code         # Claude Code installed?
```

If missing, go back to Step 0-2 and Step 1.

### "command not found: brew"

Homebrew not installed. See Step 0-1, or install Node.js/Python directly from their websites.

### "permission denied" or "EACCES"

npm global install permission issue:
```bash
sudo npm install -g @anthropic-ai/claude-code
```

Or for pip:
```bash
pip3 install --user heysquid
```

### Bot doesn't respond

1. Check daemon: `heysquid status`
2. Check logs: `heysquid logs -f`
3. Verify token in `data/.env`
4. Verify your user ID is in `TELEGRAM_ALLOWED_USERS`
5. Check Claude login: run `claude` in terminal

### "ModuleNotFoundError: No module named 'telegram'"

The telegram dependency didn't install properly:
```bash
pip3 install --force-reinstall heysquid
```

### Windows

heysquid uses macOS launchd, so it doesn't run natively on Windows.

**Use WSL2:**
1. PowerShell (admin): `wsl --install`
2. Reboot
3. Open the Ubuntu terminal
4. Follow the "Linux/WSL" install commands in this guide
5. Run `heysquid start` inside WSL

Native Linux (systemd) support is planned.

---

## What's Next

- **[FanMolt Guide](fanmolt-guide.md)** — Create AI content creators that auto-post and earn revenue
- **[Plugin Guide](../heysquid/skills/GUIDE.md)** — Build your own skills and automations
- **[Contributing](../CONTRIBUTING.md)** — Help improve heysquid
