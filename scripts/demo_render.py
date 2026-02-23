#!/usr/bin/env python3
"""Demo renderer for VHS recording — simulates heysquid CLI experience."""
import sys
import time

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

print("\033[2J\033[H", end="", flush=True)  # clear screen
time.sleep(0.3)

def typed(text, speed=0.03):
    """Simulate typing effect."""
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(speed)
    print()

def out(text=""):
    print(text)

def pause(s=0.5):
    time.sleep(s)

def prompt():
    sys.stdout.write(f"{GREEN}${RESET} ")
    sys.stdout.flush()

# === Scene 1: Install ===
prompt()
typed("pip install heysquid")
pause(0.8)
out(f"{DIM}Successfully installed heysquid-0.1.0{RESET}")
pause(1)

# === Scene 2: Init (abbreviated) ===
prompt()
typed("heysquid init")
pause(0.5)
out(f"{BOLD}heysquid init{RESET}")
out("=" * 40)
out()
out("[1/7] Environment check...")
out("  Python: 3.12.7")
out("  Claude CLI: /usr/local/bin/claude")
out()
out("[2/7] Creating directories...")
out("  data/ tasks/ workspaces/ logs/")
out()
out(f"[3/7] Telegram bot token: {GREEN}[OK]{RESET} Saved")
out(f"[4/7] Telegram user ID:   {GREEN}[OK]{RESET} Saved")
out(f"[5/7] Slack:   {DIM}[SKIP]{RESET}")
out(f"[6/7] Discord: {DIM}[SKIP]{RESET}")
out()
out(f"[7/7] {GREEN}Setup complete!{RESET}")
pause(2)

# === Scene 3: Start ===
prompt()
typed("heysquid start")
pause(0.5)
out("heysquid daemon starting...")
out()
out(f"  [watcher]   {GREEN}Installed + loaded{RESET}")
out(f"  [scheduler] {GREEN}Installed + loaded{RESET}")
out(f"  [slack]     {DIM}Skipped (no token){RESET}")
out(f"  [discord]   {DIM}Skipped (no token){RESET}")
out()
out(f"{GREEN}Daemon started.{RESET} Send a message to your bot!")
pause(2)

# === Scene 4: Status ===
prompt()
typed("heysquid status")
pause(0.5)
out(f"{BOLD}heysquid status{RESET}")
out("=" * 40)
out()
out("Services:")
out(f"  [watcher]   {GREEN}\u25cf running{RESET} (PID 48291)")
out(f"  [scheduler] {GREEN}\u25cf running{RESET} (PID 48305)")
out(f"  [slack]     {DIM}\u25cb not configured{RESET}")
out(f"  [discord]   {DIM}\u25cb not configured{RESET}")
out()
out(f"Claude PM: {GREEN}\u25cf active{RESET} (uptime 2h 31m)")
out(f"Mode:      {CYAN}standby{RESET} (polling every 30s)")
pause(2.5)

# === Scene 5: Conversation ===
out()
out(f"{CYAN}{'=' * 44}{RESET}")
out(f"{CYAN}  Meanwhile, on Telegram...{RESET}")
out(f"{CYAN}{'=' * 44}{RESET}")
out()
pause(1)

out(f" {YELLOW}You:{RESET}    Make a landing page for my new app")
pause(1.5)
out(f" {MAGENTA}SQUID:{RESET}  Got it! Here's my plan:")
pause(0.3)
out("          - React + Tailwind responsive page")
out("          - Hero, features, pricing sections")
out("          Shall I proceed?")
pause(1.5)

out(f" {YELLOW}You:{RESET}    Go ahead")
pause(1)
out(f" {MAGENTA}SQUID:{RESET}  On it! Dispatching \U0001f988developer...")
pause(1.5)
out(f" {MAGENTA}SQUID:{RESET}  Progress: components done, styling...")
pause(1.5)
out(f" {MAGENTA}SQUID:{RESET}  {GREEN}Done!{RESET} Landing page created (247 lines)")
pause(1)

out(f" {YELLOW}You:{RESET}    Add dark mode")
pause(1)
out(f" {MAGENTA}SQUID:{RESET}  \U0001f988developer on it...")
pause(1)
out(f" {MAGENTA}SQUID:{RESET}  {GREEN}Done!{RESET} Dark mode toggle added")
out()
pause(1.5)

out(f"{BOLD}{MAGENTA}\U0001f991 Your PM is always on.{RESET}")
pause(3)
