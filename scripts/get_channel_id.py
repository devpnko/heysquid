#!/usr/bin/env python3
"""채널 ID 확인용 — getUpdates 대신 최근 업데이트에서 channel_post 탐색"""
import os, sys, asyncio
from dotenv import load_dotenv
from telegram import Bot
from telegram.request import HTTPXRequest

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "heysquid", ".env"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def main():
    request = HTTPXRequest(connect_timeout=10.0, read_timeout=15.0)
    bot = Bot(token=BOT_TOKEN, request=request)

    # 방법 1: getUpdates에서 channel_post 찾기
    # listener가 message만 consume하므로 channel_post는 남아있을 수 있음
    try:
        updates = await bot.get_updates(
            timeout=5,
            allowed_updates=["channel_post"]
        )
        for u in updates:
            if u.channel_post:
                ch = u.channel_post.chat
                print(f"[찾음] 채널명: {ch.title}")
                print(f"[찾음] 채널 ID: {ch.id}")
                print(f"\n.env에 추가하세요:")
                print(f"TELEGRAM_AGENTBOX_CHANNEL_ID={ch.id}")
                return
    except Exception as e:
        print(f"getUpdates 실패: {e}")

    # 방법 2: 채널에 테스트 메시지 전송 시도 (채널 username 필요)
    print("channel_post를 찾지 못했습니다.")
    print()
    print("대안: 채널 username이나 초대 링크를 알려주세요.")
    print("또는 @userinfobot 을 채널에 추가하면 채널 ID를 알려줍니다.")
    print()
    print("가장 쉬운 방법:")
    print("1. 텔레그램에서 @RawDataBot 을 채널에 추가")
    print("2. 채널에 메시지 보내면 봇이 채널 ID를 알려줌")
    print("3. 확인 후 @RawDataBot 제거")

asyncio.run(main())
