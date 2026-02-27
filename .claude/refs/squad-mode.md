# Squad Mode (Squid / Kraken)

PM은 간단한 일은 혼자 처리하지만, 중요한 결정이나 여러 관점이 필요한 작업에서는
팀 토론(Squad)을 통해 더 좋은 결과를 만든다.

## 토론 트리거

1. **PM 판단** — 복잡도가 높거나 리스크가 있는 작업
   - 토론 계획을 사용자에게 먼저 알림
   - 사용자가 "그냥 해" → 토론 없이 바로 실행
2. **사용자 요청** — "팀 회의해줘" / `:squad` / `:kraken`
3. **자동 Squad Review** — PM이 계획 수립 후 실행 전에 관련 에이전트 피드백 수집
   - 결론을 사용자에게 보고 → 확인 후 실행

## Squid Mode — 선별 토론 (2-3명)

PM이 주제에 맞는 에이전트 2-3명을 선택하여 토론.
`:squid @researcher @developer 인증 방식` 또는 PM 자동 판단.

사용자가 `:squid @researcher @developer 인증 방식 결정` 또는 `/squid @researcher @developer 인증 방식` 명령 시:
1. `squad_log`가 초기화됨 (mode: squid)
2. PM은 지정된 에이전트(researcher, developer)의 관점에서 토론을 시뮬레이션
3. 각 발언을 `add_squad_entry(agent, entry_type, message)` 로 기록
   - entry_type: opinion | agree | disagree | risk | proposal | conclusion
4. PM이 최종 결론을 `conclude_squad(conclusion)`으로 기록

```python
from heysquid.dashboard import add_squad_entry, conclude_squad

# 에이전트 관점 시뮬레이션
add_squad_entry("researcher", "opinion", "OAuth2가 표준이고 라이브러리 지원이 좋아요")
add_squad_entry("developer", "disagree", "JWT가 서버 부하가 적어요, 스케일링에 유리")
add_squad_entry("researcher", "agree", "맞아요, 우리 규모에서는 JWT가 더 적합하네요")

# 결론
conclude_squad("JWT 기반 인증으로 결정. 리프레시 토큰은 Redis에 저장.")
```

## Kraken Mode — 총력 토론 (전원 + Kraken Crew)

`:kraken 프로젝트 방향성` — 5명 에이전트 전원 + 13명 Kraken Crew.
각 크루의 style 필드를 참고하여 발언 톤/관점 결정.

사용자가 `:kraken 프로젝트 방향성` 또는 `/kraken 프로젝트 방향성` 명령 시:
1. `squad_log`가 초기화됨 (mode: kraken, 전체 에이전트 + Kraken Crew)
2. PM은 모든 참가자의 관점에서 종합 평가를 시뮬레이션
3. 기존 에이전트: agent 이름 그대로 (예: "researcher")
4. Kraken Crew: `kraken:name` 형태 (예: "kraken:whale", "kraken:dolphin")
5. **각 크루의 `style` 필드를 참고**하여 발언 톤/관점 결정

```python
from heysquid.core.agents import KRAKEN_CREW
from heysquid.dashboard import add_squad_entry

# 크루별 style 확인
# KRAKEN_CREW["whale"]["style"] = "거시적 시각, 실용적 아키텍처, 확장성 트레이드오프, 검증된 기술"

add_squad_entry("kraken:whale", "opinion", "마이크로서비스보다 모놀리스가 현재 팀 규모에 적합합니다")
add_squad_entry("kraken:dolphin", "proposal", "MVP를 먼저 검증하고, 트래픽 증가 시 분리합시다")
add_squad_entry("kraken:crab", "opinion", "모놀리스라도 도메인 경계는 명확히 해야 합니다")
```

## PM 시뮬레이션 원칙

턴당 2-3명 원칙 (BMAD 인사이트):
- 모든 참가자가 매 턴 발언하지 않음
- PM이 맥락에 맞는 2-3명만 선택하여 발언
- 나머지는 다음 턴에 참여

각 에이전트의 role에 맞는 관점에서만 발언:
- researcher: 데이터/사실, 리스크 발견
- developer: 구현 난이도, 기술 제약, 대안
- reviewer: 품질, 보안, 엣지 케이스
- tester: 테스트 가능성, 검증 방법
- writer: 사용자 소통, 문서화, 명확성

## entry_type

opinion(의견), agree(동의), disagree(반대), risk(리스크), proposal(제안), conclusion(결론)

## Kraken Crew 레지스트리

`heysquid/core/agents.py`의 `KRAKEN_CREW` 딕셔너리에 13명의 가상 크루가 정의되어 있다.
크라켄이 소환하는 심해 전문가들 — 해양생물 습성이 역할과 매칭.

**Builders (개발/비즈니스 — 8명):**
🦭 seal(Analyst) / 🐋 whale(Architect) / 🦀 crab(Developer) / 🐬 dolphin(PM) / 🐟 sailfish(Solo Dev) / 🦦 otter(Scrum Master) / 🐚 nautilus(Tech Writer) / 🪸 coral(UX Designer)

**Dreamers (창의/혁신 — 5명):**
🐠 clownfish(Brainstorm Coach) / 🪼 jellyfish(Problem Solver) / 🦐 shrimp(Design Thinking) / 🐟 flyingfish(Innovation) / 🦑 cuttlefish(Presentation)
