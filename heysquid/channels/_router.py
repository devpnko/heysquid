"""
heysquid.channels._router — 채널 라우팅 + 브로드캐스트.

전체 동기화 모델: 모든 채널은 하나의 대화방.
- broadcast_all(): PM 응답 → 전체 채널
- broadcast_user_message(): 사용자 메시지 릴레이 → 다른 채널
- broadcast_files(): 파일 → 전체 채널 (크기 초과 시 알림 폴백)
"""

import os
import threading

_SENDERS = {}  # {"telegram": module, "slack": module, "discord": module}
_SENDERS_LOCK = threading.Lock()  # H-10: thread-safe 등록

# 채널별 태그 (2글자)
CHANNEL_TAGS = {
    "telegram": "TG",
    "slack": "SL",
    "discord": "DC",
    "tui": "TUI",
}

# 채널별 파일 크기 제한 (bytes)
CHANNEL_LIMITS = {
    "discord": 25_000_000,
    "telegram": 50_000_000,
    "slack": 1_000_000_000,
}

# per-channel broadcast timeout (seconds)
BROADCAST_TIMEOUT = 5


def register_sender(channel_name, sender_module):
    """채널 sender 등록 (H-10: thread-safe)"""
    with _SENDERS_LOCK:
        _SENDERS[channel_name] = sender_module


def get_sender(channel_name):
    """등록된 sender 조회"""
    return _SENDERS.get(channel_name)


def get_active_channels():
    """현재 등록된 활성 채널 목록"""
    return list(_SENDERS.keys())


def _run_with_timeout(fn, timeout, channel_name):
    """H-1: per-channel timeout 적용 (계획서: broadcast에 per-channel timeout 5초 필수)"""
    result = [False]
    exc = [None]

    def _target():
        try:
            result[0] = fn()
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        print(f"[WARN] {channel_name} 전송 타임아웃 ({timeout}s)")
        return False
    if exc[0]:
        raise exc[0]
    return result[0]


def send_to_channel(channel, chat_id, text, **kwargs):
    """단일 채널로 메시지 전송 (내부 유틸, per-channel timeout 적용)"""
    sender = get_sender(channel)
    if sender:
        try:
            return _run_with_timeout(
                lambda: sender.send_message_sync(chat_id, text, _save=False, **kwargs),
                BROADCAST_TIMEOUT, channel,
            )
        except Exception as e:
            print(f"[WARN] {channel} 전송 실패: {e}")
            return False
    return False


def broadcast_all(text, exclude_channels=None):
    """모든 활성 채널에 브로드캐스트 — PM 응답의 기본 전송 방식.

    messages.json 저장은 호출자(broadcaster)가 담당.
    각 sender에는 _save=False로 중복 저장 방지.
    H-1: per-channel timeout 5초 적용.

    Returns:
        dict: {channel_name: success_bool}
    """
    exclude = set(exclude_channels or [])
    results = {}
    for name, sender in list(_SENDERS.items()):
        if name in exclude:
            continue
        try:
            default_id = _get_default_chat_id(name)
            if default_id:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id: s.send_message_sync(d, text, _save=False),
                    BROADCAST_TIMEOUT, name,
                )
            else:
                results[name] = False
        except Exception as e:
            print(f"[WARN] broadcast to {name} failed: {e}")
            results[name] = False
    return results


def broadcast_user_message(text, source_channel, sender_name=""):
    """사용자 메시지를 다른 채널에 릴레이 — 각 listener가 호출.

    Args:
        text: 원본 메시지 텍스트
        source_channel: 원본 채널 이름 ("telegram", "slack", "discord", "tui")
        sender_name: 보낸 사람 이름

    Returns:
        dict: {channel_name: success_bool}
    """
    tag = CHANNEL_TAGS.get(source_channel, source_channel.upper()[:2])
    prefix = f"[{tag}] {sender_name}: " if sender_name else f"[{tag}] "
    relay_text = prefix + text

    results = {}
    for name, sender in list(_SENDERS.items()):
        if name == source_channel:
            continue  # 원본 채널은 스킵
        try:
            default_id = _get_default_chat_id(name)
            if default_id:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id: s.send_message_sync(d, relay_text, _save=False),
                    BROADCAST_TIMEOUT, name,
                )
            else:
                results[name] = False
        except Exception as e:
            print(f"[WARN] relay to {name} failed: {e}")
            results[name] = False
    return results


def broadcast_files(file_paths, text="", exclude_channels=None):
    """모든 활성 채널에 파일 브로드캐스트 (크기 초과 시 알림 폴백).

    Returns:
        dict: {channel_name: success_bool}
    """
    exclude = set(exclude_channels or [])
    results = {}
    for name, sender in list(_SENDERS.items()):
        if name in exclude:
            continue
        try:
            default_id = _get_default_chat_id(name)
            if not default_id:
                continue
            limit = CHANNEL_LIMITS.get(name, 50_000_000)
            sendable = [f for f in file_paths if os.path.exists(f) and os.path.getsize(f) <= limit]
            oversized = [f for f in file_paths if os.path.exists(f) and os.path.getsize(f) > limit]
            if sendable:
                results[name] = _run_with_timeout(
                    lambda s=sender, d=default_id, sp=sendable: s.send_files_sync(d, text, sp),
                    BROADCAST_TIMEOUT * 6, name,  # 파일 전송은 6배 타임아웃 (30s)
                )
            if oversized:
                names_str = ", ".join(os.path.basename(f) for f in oversized)
                sender.send_message_sync(default_id, f"[FILE] 크기 초과 (채널 제한): {names_str}", _save=False)
        except Exception as e:
            print(f"[WARN] file broadcast to {name} failed: {e}")
            results[name] = False
    return results


def _get_default_chat_id(channel):
    """채널별 기본 응답 대상 ID (env에서 로드)"""
    mapping = {
        "telegram": "TELEGRAM_ALLOWED_USERS",  # 첫 번째 사용자
        "slack": "SLACK_DEFAULT_CHANNEL",
        "discord": "DISCORD_DEFAULT_CHANNEL",
    }
    key = mapping.get(channel)
    if not key:
        return None
    val = os.getenv(key, "")
    if channel == "telegram":
        val = val.split(",")[0].strip()
    return val or None


def _auto_register():
    """사용 가능한 sender를 자동 등록 (env 토큰 기반)"""
    # Telegram — 항상 시도
    try:
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            from . import telegram
            register_sender("telegram", telegram)
    except ImportError:
        pass

    # Slack — 토큰이 있을 때만
    try:
        if os.getenv("SLACK_BOT_TOKEN"):
            from . import slack  # noqa: F401
            register_sender("slack", slack)
    except ImportError:
        pass

    # Discord — 토큰이 있을 때만
    try:
        if os.getenv("DISCORD_BOT_TOKEN"):
            from . import discord_channel  # noqa: F401
            register_sender("discord", discord_channel)
    except ImportError:
        pass


# 모듈 임포트 시 자동 등록
_auto_register()
