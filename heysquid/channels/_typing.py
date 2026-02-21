"""
heysquid.channels._typing — Telegram "typing..." indicator daemon thread.

Sends sendChatAction(TYPING) every 4 seconds while active.
Daemon thread — auto-terminates when the process dies.
"""

import threading

_stop_event = threading.Event()
_thread = None
_lock = threading.Lock()


def start(chat_id):
    """Start sending typing indicator to *chat_id* every 4 seconds."""
    global _thread
    if chat_id is None:
        return

    with _lock:
        stop()  # kill any previous thread
        _stop_event.clear()
        _thread = threading.Thread(
            target=_loop,
            args=(int(chat_id),),
            daemon=True,
        )
        _thread.start()


def stop():
    """Signal the daemon to stop (returns immediately)."""
    global _thread
    _stop_event.set()
    _thread = None


def _loop(chat_id):
    """Worker: send TYPING action every 4 s until stopped."""
    from .telegram import _get_bot, run_async_safe

    bot = _get_bot()
    while not _stop_event.is_set():
        try:
            run_async_safe(bot.send_chat_action(chat_id=chat_id, action="typing"))
        except Exception:
            pass  # best-effort
        _stop_event.wait(4)
