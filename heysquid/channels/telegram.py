"""
Telegram response sender — heysquid Mac port

Responsibilities:
- Send Claude Code task results to Telegram
- Support text messages and file attachments
- Support Markdown formatting

Usage:
    from telegram_sender import send_message, send_files

    await send_message(chat_id, "message content")
    await send_files(chat_id, "message content", ["file1.txt", "file2.png"])
"""

import os
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
import asyncio

from ..config import get_env_path

# Load .env file
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Bot singleton
_bot = None


def _get_bot():
    """Reuse Bot instance (avoid creating one per call)"""
    global _bot
    if _bot is None:
        _bot = Bot(token=BOT_TOKEN)
    return _bot


async def send_message(chat_id, text, parse_mode="Markdown"):
    """
    Send a Telegram message

    Args:
        chat_id: Chat ID (user ID)
        text: Message to send
        parse_mode: Parse mode (Markdown, HTML, None)

    Returns:
        bool: Success status
    """
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN not set.")
        print("   Run 'python telegram_listener.py' first to set up the token.")
        return False

    try:
        bot = _get_bot()
        last_sent_id = None

        # Telegram message length limit (4096 chars)
        if len(text) > 4000:
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)
                try:
                    sent = await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=parse_mode
                    )
                    last_sent_id = sent.message_id
                except Exception as e:
                    if parse_mode and "parse" in str(e).lower():
                        sent = await bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode=None
                        )
                        last_sent_id = sent.message_id
                    else:
                        raise
        else:
            try:
                sent = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
                last_sent_id = sent.message_id
            except Exception as e:
                if parse_mode and "parse" in str(e).lower():
                    sent = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=None
                    )
                    last_sent_id = sent.message_id
                else:
                    raise

        return last_sent_id or True  # int(msg_id) or True

    except Exception as e:
        print(f"[ERROR] Message send failed: {e}")
        return False


async def send_file(chat_id, file_path, caption=None):
    """
    Send a file via Telegram

    Args:
        chat_id: Chat ID
        file_path: File path
        caption: File description (optional)

    Returns:
        bool: Success status
    """
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN not set.")
        return False

    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return False

    try:
        bot = _get_bot()

        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            print(f"[WARN] File too large ({file_size / 1024 / 1024:.1f}MB). Only files up to 50MB can be sent.")
            return False

        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                caption=caption,
                filename=os.path.basename(file_path)
            )

        return True

    except Exception as e:
        print(f"[ERROR] File send failed: {e}")
        return False


async def send_files(chat_id, text, file_paths):
    """
    Send a Telegram message + multiple files

    Args:
        chat_id: Chat ID
        text: Message content
        file_paths: List of file paths

    Returns:
        bool: Success status
    """
    success = await send_message(chat_id, text)

    if not success:
        return False

    if not file_paths:
        return True

    for i, file_path in enumerate(file_paths):
        if i > 0:
            await asyncio.sleep(0.5)

        file_name = os.path.basename(file_path)
        print(f"[FILE] Sending file: {file_name}")

        success = await send_file(chat_id, file_path, caption=f"[FILE] {file_name}")

        if success:
            print(f"[OK] File sent: {file_name}")
        else:
            print(f"[ERROR] File send failed: {file_name}")

    return True


def run_async_safe(coro):
    """Run in a separate thread if an event loop is already running"""
    try:
        asyncio.get_running_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# Synchronous wrapper functions
def send_message_sync(chat_id, text, parse_mode="Markdown", _save=True):
    """
    Synchronous message send

    On each message send:
    1. Auto-save to messages.json (when _save=True)
    2. Update last_activity in working.json
    3. Check for and save new messages (only while working)
    """
    # Start typing indicator (signals "still talking")
    try:
        from ._typing import start as _typing_start
        _typing_start(chat_id)
    except Exception:
        pass

    result = run_async_safe(send_message(chat_id, text, parse_mode))

    if result:
        sent_message_id = result if isinstance(result, int) else None
        if _save:
            try:
                import time
                from ._msg_store import save_bot_response
                msg_id = f"bot_progress_{int(time.time() * 1000)}"
                save_bot_response(chat_id, text, [msg_id], channel="telegram",
                                  sent_message_id=sent_message_id)
            except Exception as e:
                print(f"[WARN] Failed to save bot response: {e}")
        try:
            from .._working_lock import update_working_activity
            update_working_activity()
        except Exception as e:
            print(f"[WARN] working lock update failed: {e}")

    return result


def send_files_sync(chat_id, text, file_paths, _save=True):
    """Synchronous file send — also saves to messages.json"""
    result = run_async_safe(send_files(chat_id, text, file_paths))

    if result and _save:
        try:
            import time
            from ._msg_store import save_bot_response
            msg_id = f"bot_file_{int(time.time() * 1000)}"
            files_meta = [
                {"type": "photo", "name": os.path.basename(p), "path": p}
                for p in (file_paths or [])
            ]
            save_bot_response(chat_id, text, [msg_id], files=files_meta, channel="telegram")
        except Exception as e:
            print(f"[WARN] Failed to save file response: {e}")
    if result:
        try:
            from .._working_lock import update_working_activity
            update_working_activity()
        except Exception:
            pass

    return result


async def send_message_with_stop_button(chat_id, text, parse_mode="Markdown"):
    """Send message with 'Stop' inline button"""
    try:
        bot = _get_bot()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Stop", callback_data="stop")]
        ])
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=keyboard
            )
        except Exception as e:
            if parse_mode and "parse" in str(e).lower():
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=None,
                    reply_markup=keyboard
                )
            else:
                raise
        return True
    except Exception as e:
        print(f"[ERROR] Button message send failed: {e}")
        return False


def send_message_with_stop_button_sync(chat_id, text, parse_mode="Markdown"):
    """Synchronous message + stop button send"""
    return run_async_safe(send_message_with_stop_button(chat_id, text, parse_mode))


async def register_bot_commands():
    """Register bot command menu (/ menu)"""
    try:
        bot = _get_bot()
        commands = [
            BotCommand("stop", "Stop the current task"),
        ]
        await bot.set_my_commands(commands)
        print("[CMD] Bot command menu registered: /stop")
        return True
    except Exception as e:
        print(f"[ERROR] Bot command registration failed: {e}")
        return False


def register_bot_commands_sync():
    """Synchronous bot command registration"""
    return run_async_safe(register_bot_commands())


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python telegram_sender.py <chat_id> <message>")
        print("Example: python telegram_sender.py 1234567890 'test message'")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    message = sys.argv[2]

    print(f"Sending message: {chat_id}")
    success = send_message_sync(chat_id, message)

    if success:
        print("[OK] Send successful!")
    else:
        print("[ERROR] Send failed!")
