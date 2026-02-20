"""
텔레그램 응답 전송기 (Sender) — heysquid Mac 포팅

역할:
- Claude Code 작업 결과를 텔레그램으로 전송
- 텍스트 메시지 및 파일 첨부 지원
- 마크다운 포맷 지원

사용법:
    from telegram_sender import send_message, send_files

    await send_message(chat_id, "메시지 내용")
    await send_files(chat_id, "메시지 내용", ["파일1.txt", "파일2.png"])
"""

import os
from dotenv import load_dotenv
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
import asyncio

from ..config import get_env_path

# .env 파일 로드
load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Bot 싱글턴
_bot = None


def _get_bot():
    """Bot 인스턴스 재사용 (매 호출마다 생성 방지)"""
    global _bot
    if _bot is None:
        _bot = Bot(token=BOT_TOKEN)
    return _bot


async def send_message(chat_id, text, parse_mode="Markdown"):
    """
    텔레그램 메시지 전송

    Args:
        chat_id: 채팅 ID (사용자 ID)
        text: 전송할 메시지
        parse_mode: 파싱 모드 (Markdown, HTML, None)

    Returns:
        bool: 성공 여부
    """
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN 미설정.")
        print("   먼저 'python telegram_listener.py'를 실행하여 토큰을 설정해주세요.")
        return False

    try:
        bot = _get_bot()

        # 텔레그램 메시지 길이 제한 (4096자)
        if len(text) > 4000:
            chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=parse_mode
                    )
                except Exception as e:
                    if parse_mode and "parse" in str(e).lower():
                        await bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode=None
                        )
                    else:
                        raise
        else:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
            except Exception as e:
                if parse_mode and "parse" in str(e).lower():
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=None
                    )
                else:
                    raise

        return True

    except Exception as e:
        print(f"[ERROR] 메시지 전송 실패: {e}")
        return False


async def send_file(chat_id, file_path, caption=None):
    """
    텔레그램 파일 전송

    Args:
        chat_id: 채팅 ID
        file_path: 파일 경로
        caption: 파일 설명 (선택)

    Returns:
        bool: 성공 여부
    """
    if not BOT_TOKEN or BOT_TOKEN in ("your_bot_token_here", "YOUR_BOT_TOKEN"):
        print("[ERROR] TELEGRAM_BOT_TOKEN 미설정.")
        return False

    if not os.path.exists(file_path):
        print(f"[ERROR] 파일을 찾을 수 없습니다: {file_path}")
        return False

    try:
        bot = _get_bot()

        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            print(f"[WARN] 파일이 너무 큽니다 ({file_size / 1024 / 1024:.1f}MB). 50MB 이하만 전송 가능합니다.")
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
        print(f"[ERROR] 파일 전송 실패: {e}")
        return False


async def send_files(chat_id, text, file_paths):
    """
    텔레그램 메시지 + 여러 파일 전송

    Args:
        chat_id: 채팅 ID
        text: 메시지 내용
        file_paths: 파일 경로 리스트

    Returns:
        bool: 성공 여부
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
        print(f"[FILE] 파일 전송 중: {file_name}")

        success = await send_file(chat_id, file_path, caption=f"[FILE] {file_name}")

        if success:
            print(f"[OK] 파일 전송 완료: {file_name}")
        else:
            print(f"[ERROR] 파일 전송 실패: {file_name}")

    return True


def run_async_safe(coro):
    """이벤트 루프가 이미 실행 중이면 별도 스레드에서 실행"""
    try:
        asyncio.get_running_loop()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


# 동기 함수 래퍼
def send_message_sync(chat_id, text, parse_mode="Markdown", _save=True):
    """
    동기 방식 메시지 전송

    메시지 전송 시마다:
    1. messages.json에 자동 저장 (_save=True일 때)
    2. working.json의 last_activity 갱신
    3. 새 메시지 확인 및 저장 (작업 중일 때만)
    """
    result = run_async_safe(send_message(chat_id, text, parse_mode))

    if result:
        if _save:
            try:
                import time
                from ._msg_store import save_bot_response
                msg_id = f"bot_progress_{int(time.time() * 1000)}"
                save_bot_response(chat_id, text, [msg_id], channel="telegram")
            except Exception:
                pass
        try:
            from .._working_lock import (
                update_working_activity,
                check_new_messages_during_work,
                save_new_instructions
            )

            update_working_activity()

            new_msgs = check_new_messages_during_work()
            if new_msgs:
                save_new_instructions(new_msgs)

                alert_text = f"**새로운 요청 {len(new_msgs)}개 확인**\n\n"
                for i, msg in enumerate(new_msgs, 1):
                    alert_text += f"{i}. {msg['instruction'][:50]}...\n"
                alert_text += "\n진행 중인 작업에 반영하겠습니다."

                run_async_safe(send_message(chat_id, alert_text, parse_mode))

        except Exception:
            pass

    return result


def send_files_sync(chat_id, text, file_paths):
    """동기 방식 파일 전송"""
    return run_async_safe(send_files(chat_id, text, file_paths))


async def send_message_with_stop_button(chat_id, text, parse_mode="Markdown"):
    """메시지 + '중단' 인라인 버튼 전송"""
    try:
        bot = _get_bot()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("중단", callback_data="stop")]
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
        print(f"[ERROR] 버튼 메시지 전송 실패: {e}")
        return False


def send_message_with_stop_button_sync(chat_id, text, parse_mode="Markdown"):
    """동기 방식 메시지 + 중단 버튼 전송"""
    return run_async_safe(send_message_with_stop_button(chat_id, text, parse_mode))


async def register_bot_commands():
    """봇 커맨드 메뉴 등록 (/ 메뉴)"""
    try:
        bot = _get_bot()
        commands = [
            BotCommand("stop", "진행 중인 작업 중단"),
        ]
        await bot.set_my_commands(commands)
        print("[CMD] 봇 커맨드 메뉴 등록 완료: /stop")
        return True
    except Exception as e:
        print(f"[ERROR] 봇 커맨드 등록 실패: {e}")
        return False


def register_bot_commands_sync():
    """동기 방식 봇 커맨드 등록"""
    return run_async_safe(register_bot_commands())


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("사용법: python telegram_sender.py <chat_id> <message>")
        print("예: python telegram_sender.py 1234567890 '테스트 메시지'")
        sys.exit(1)

    chat_id = int(sys.argv[1])
    message = sys.argv[2]

    print(f"메시지 전송 중: {chat_id}")
    success = send_message_sync(chat_id, message)

    if success:
        print("[OK] 전송 성공!")
    else:
        print("[ERROR] 전송 실패!")
