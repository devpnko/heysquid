"""
Threads 게시 모듈 — instagrapi 기반

Instagram 아이디/비번으로 로그인 후 Threads에 글을 게시한다.
"""

import os
import json
from dotenv import load_dotenv

# .env 로드
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH)

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "threads_session.json")


def _get_client():
    """instagrapi Client 생성 및 로그인"""
    from instagrapi import Client

    cl = Client()

    # 세션 파일이 있으면 재사용
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(
                os.environ["THREADS_USERNAME"],
                os.environ["THREADS_PASSWORD"],
            )
            cl.get_timeline_feed()  # 세션 유효성 확인
            print("[THREADS] 기존 세션으로 로그인 성공")
            return cl
        except Exception as e:
            print(f"[THREADS] 기존 세션 만료, 새로 로그인: {e}")

    # 새 로그인
    cl.login(
        os.environ["THREADS_USERNAME"],
        os.environ["THREADS_PASSWORD"],
    )

    # 세션 저장
    os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
    cl.dump_settings(SESSION_FILE)
    print("[THREADS] 새 로그인 성공, 세션 저장 완료")

    return cl


def login_test():
    """로그인 테스트 — 성공하면 유저 정보 반환"""
    cl = _get_client()
    user_info = cl.account_info()
    return {
        "username": user_info.username,
        "full_name": user_info.full_name,
        "pk": user_info.pk,
        "is_private": user_info.is_private,
    }


def post_thread(text):
    """
    Threads에 텍스트 글 게시

    Args:
        text: 게시할 텍스트 (500자 이내)
    Returns:
        dict: 게시 결과 정보
    """
    cl = _get_client()

    # instagrapi의 Threads 게시 기능 사용
    result = cl.text_upload_to_thread(text)

    return {
        "success": True,
        "thread_id": str(result.pk) if result else None,
        "text": text[:50] + "..." if len(text) > 50 else text,
    }


if __name__ == "__main__":
    print("=== Threads 로그인 테스트 ===")
    try:
        info = login_test()
        print(f"로그인 성공!")
        print(f"  Username: {info['username']}")
        print(f"  Full Name: {info['full_name']}")
        print(f"  PK: {info['pk']}")
    except Exception as e:
        print(f"로그인 실패: {e}")
