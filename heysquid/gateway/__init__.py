"""heysquid.gateway — 단일 asyncio 텔레그램 게이트웨이 (Part A 재작성).

기존 구조의 문제:
- bash executor.sh IDLE loop + telegram_listener polling = 두 폴링 주체 race
- quick_check.py seen-skip + standby loop poll → seen 플래그 race condition → 메시지 씹힘
- _base.trigger_executor "already running → skip" → 연속 메시지 두 번째 유실

새 구조 (이 패키지):
- 단일 asyncio 프로세스가 polling + claude subprocess 오케스트레이션을 모두 담당
- per-chat 디바운스로 연속 메시지를 1배치로 합침
- claude 세션이 끝나면 즉시 미처리 메시지 재확인 → 씹힘 0
- telegram sender 만 register → broadcast 가 자동으로 reply-to-source

엔트리: python -m heysquid.gateway  (systemd ExecStart)
기존 채널 코드(channels/telegram.py, telegram_listener.py, _msg_store.py)는 재사용.
"""
