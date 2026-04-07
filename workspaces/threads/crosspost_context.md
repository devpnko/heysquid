# 크로스포스팅 컨텍스트 (2026-04-03~)

> **이 파일은 Threads → X/Reddit/LinkedIn 크로스포스팅 규칙을 정의한다.**
> 작업 전 반드시 이 파일 + context.md를 먼저 읽을 것.
> **상세 문서**: 옵시디언 `TERA_AGENT.base/threads/크로스포스팅_마스터.md`
> (채널별 특이사항, 트러블슈팅, 교훈 등 세부 내용은 옵시디언에)

## 플랫폼별 자동화 환경

| 플랫폼 | 세션 경로 | 환경 | 스크립트 |
|---|---|---|---|
| Threads (dkbsqd) | WSL `data/threads_browser_data` | WSL headless | `threads_cron.py`, `threads_engage.py` |
| Threads (ambition) | WSL `data/threads_browser_data_ambition` | WSL headless | 동일 (`--account ambition_monkey`) |
| X | Windows `C:\Users\hyuk\heysquid_sessions\browser_x` | Windows headful | `C:\Users\hyuk\x_actions.py` |
| Reddit | WSL `data/browser_reddit` | WSL headless | `C:\Users\hyuk\crosspost.py` (미완성) |
| LinkedIn | Windows `C:\Users\hyuk\heysquid_sessions\browser_linkedin` | Windows headful | `C:\Users\hyuk\crosspost.py` (미완성) |

## ⚠️ 계정별 페르소나 (절대 분리)

> **게시, 첫 댓글, engage 댓글 모두 해당 계정 톤으로만 작성. 절대 섞지 않는다.**

### dkbsqd.official (도화)
- 톤: F감성, 반말, 친구처럼
- 일반 글 → 순수 공감만. 사주 언급 절대 안 함
- 사주/운세/MBTI 글 → 사주 살짝 섞기 OK
- 예: "어릴 때 보던 만화가 현실이 되는 순간 ㅋㅋㅋ"

### ambition_monkey
- 톤: AI 업계 친구, 반말, 실용적
- 일반 글 → 공감만
- AI/테크 글 → 인사이트 살짝 섞기 OK
- 예: "이거 Claude로 하면 5분컷인데 ㅋㅋ"

## engage 댓글 언어 규칙

- **영어 글에는 영어로**, **한글 글에는 한글로** 댓글
- X는 글로벌 피드 → 영어 댓글이 많음
- Threads는 한국어 피드 → 한글 댓글이 기본
- 원문 언어에 맞춰서 자연스럽게

## 공통 금지
- 홍보/CTA는 **첫 댓글에만**. engage 댓글에선 절대 안 함
- engage 댓글: 1~2줄 짧게, 이모지 0~1개, 존댓말 안 씀, 봇 티 금지

## 크로스포스팅 플로우

```
1. Threads에 원본 게시 (ambition_monkey)
2. 동시에 각 플랫폼별 각색본 게시
3. 각 플랫폼에서:
   - 자동 좋아요
   - 첫 댓글 (CTA + litt.ly/ambition_monkey 링크)
   - engage 댓글 (홈피드 글에 좋아요 + 댓글)
```

## 플랫폼별 각색 규칙

| | Threads | X | Reddit | LinkedIn |
|---|---|---|---|---|
| 톤 | 반말, 캐주얼 | 반말, 임팩트 | 반말, 토론형 | 존댓말, 전문가 |
| 글자수 | 500자 | 280자 (한글=2카운트) | 제한없음 | 제한없음 |
| 해시태그 | 1개 | 없음 | 없음 | 2-3개 |
| 이모지 | 1-2개 | 0-1개 | 없음 | 0-1개 |
| 첫 댓글 | CTA + 링크 | 리플 + 링크 | 댓글 + 링크 | 댓글 + 링크 |
| engage | 댓글 10개 | 리플 5개 | 댓글 10개 | 댓글 10개 |
| 마무리 | 뱅크 패턴 | 핵심 한줄 | "여러분은?" | "~하고 계신가요?" |
| 링크 | litt.ly/ambition_monkey | 동일 | 동일 | 동일 |

## X 특이사항

- 한글 입력: `pyperclip` 시스템 클립보드 + Ctrl+V (브라우저 clipboard API 차단됨)
- 게시: 홈 인라인 에디터 사용 (compose 모달은 불안정)
- 리플: 프로필 → 글 상세페이지 → 하단 에디터
- 글자수: `x_char_count()` — 한글 1자=2카운트, 280자 사전검증 필수
- engage: 상세페이지에서 좋아요 + 리플 (모달 리플은 에디터 안 뜸)

## 초안 파일 위치

- 옵시디언: `TERA_AGENT.base/threads/ambition_monkey/crosspost_draft_01~06.md`
- 각 파일에 4개 플랫폼 각색본 + CTA + 액션 정의

## 진행 상태 (2026-04-03)

| 플랫폼 | 초안#1 게시 | 좋아요 | 첫 댓글 | engage |
|---|---|---|---|---|
| Threads | ✅ | ✅ | ✅ | ✅ 4개 |
| X | ✅ (280자) | ✅ | ✅ | ✅ 5개 |
| Reddit | ❌ 세션풀림 | - | - | - |
| LinkedIn | ❌ 셀렉터수정필요 | - | - | - |
