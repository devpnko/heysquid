"""
HYPERS 마케팅 콘텐츠 템플릿 — 40개 완성 콘텐츠

카테고리:
- ai_tip (20개): AI 활용 팁으로 팔로워 확보
- host_recruit (5개): 은둔 고수 호스트 섭외
- participant (10개): 참여자 유입 유도
- fomo (5개): 기대감 증폭 (FOMO)
"""

HYPERS_CONTEXT = {
    "name": "HYPERS",
    "tagline": "호스트와 참여자가 공존하는 AI 커뮤니티",
    "launch_date": "2026-03-16",
    "location": "성수 상상 플래닛",
    "landing_url": "",  # 사용자 제공 예정
    "features": ["통합 입장권", "뷔페식 강의", "은둔 고수 호스트"],
    "team": {
        "윤상혁": "마케팅/홍보",
        "손창균": "프로그램/가이드/상세페이지",
        "세훈": "내부 호스트 (Suno AI 음악)",
    },
    "price": {
        "online_pass": "55,000원",
        "earlybird": "33,000원",
        "offline_addon": "99,000원",
    },
    "host_benefits": [
        "성수 장소 무료 제공",
        "홍보 대행",
        "상세 페이지 제작",
        "GPT 익명 프로필 지원",
    ],
}


# --- 콘텐츠 40개 ---

CONTENTS = [
    # ==============================
    # ai_tip (20개) — 팔로워 확보용
    # ==============================
    {
        "id": "tip-01",
        "category": "ai_tip",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "ChatGPT에 이 한 줄만 추가하면 답변 퀄리티가 달라집니다\n\n"
            "\"내가 모르는 게 있으면 모른다고 말해줘\"\n\n"
            "이거 하나로 헛소리(할루시네이션) 확 줄어듦\n"
            "프롬프트 100개보다 이 한 줄이 더 강력합니다\n\n"
            "저장해두고 써보세요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#AI활용", "#ChatGPT", "#프롬프트"],
    },
    {
        "id": "tip-02",
        "category": "ai_tip",
        "hook_type": "리스트형",
        "platform": "both",
        "content": (
            "2026년 무료 AI 도구 TOP 5 (진짜 쓸만한 것만)\n\n"
            "1. ChatGPT — 만능 비서\n"
            "2. Claude — 긴 문서 분석\n"
            "3. Perplexity — AI 검색\n"
            "4. Gamma — 발표자료 자동 생성\n"
            "5. Suno — AI 음악 제작\n\n"
            "하나도 안 써봤으면 오늘 당장 시작하세요\n"
            "북마크 필수"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#AI도구", "#무료AI", "#생성형AI"],
    },
    {
        "id": "tip-03",
        "category": "ai_tip",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "ChatGPT 쓰면서 '이거 맞아?' 하고 의심해본 적 있나요?\n\n"
            "AI 답변을 100% 믿으면 안 되는 이유:\n"
            "→ 최신 정보가 아닐 수 있음\n"
            "→ 그럴듯하게 지어내기도 함\n"
            "→ 맥락을 잘못 이해할 수 있음\n\n"
            "AI는 도구입니다. 최종 판단은 사람이 해야 해요\n\n"
            "여러분은 AI 답변 어디까지 믿으시나요?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI", "#ChatGPT", "#AI활용법"],
    },
    {
        "id": "tip-04",
        "category": "ai_tip",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "프롬프트 잘 쓰는 사람들의 공통점 하나\n\n"
            "\"역할을 먼저 준다\"\n\n"
            "❌ \"마케팅 전략 짜줘\"\n"
            "✅ \"너는 10년차 마케팅 디렉터야. 예산 0원으로 SNS 마케팅 전략을 짜줘\"\n\n"
            "이것만 해도 결과물이 2배는 좋아집니다\n\n"
            "저장해두고 다음에 써보세요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#프롬프트", "#AI활용", "#GPT활용법"],
    },
    {
        "id": "tip-05",
        "category": "ai_tip",
        "hook_type": "충격형",
        "platform": "both",
        "content": (
            "솔직히 말할게요\n"
            "AI 강의 90%는 구글링하면 나오는 내용입니다\n\n"
            "진짜 실력이 느는 건:\n"
            "→ 직접 써보면서 삽질하기\n"
            "→ 잘 쓰는 사람 옆에서 배우기\n"
            "→ 실전 프로젝트에 적용하기\n\n"
            "강의 모으기만 하지 말고 일단 써보세요"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI공부", "#자기계발", "#AI"],
    },
    {
        "id": "tip-06",
        "category": "ai_tip",
        "hook_type": "공감형",
        "platform": "both",
        "content": (
            "AI 배우고 싶은데 혼자 하니까 작심삼일인 분?\n\n"
            "저도 그랬어요\n"
            "유튜브 켜놓고 따라하다 3일 만에 포기\n\n"
            "그런데 같이 하는 사람이 생기니까 달라졌어요\n"
            "→ 질문할 사람이 있으니까 막히는 게 줄었고\n"
            "→ 서로 진도 체크하니까 안 빠지게 됨\n\n"
            "혼자 말고 같이 하세요. 진짜 다릅니다"
        ),
        "cta_type": "공유유도",
        "hashtags": ["#AI공부", "#AI커뮤니티", "#자기계발"],
    },
    {
        "id": "tip-07",
        "category": "ai_tip",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "AI로 하루 2시간 아끼는 직장인 루틴 3가지\n\n"
            "1. 이메일 초안 → ChatGPT (15분 → 3분)\n"
            "2. 회의록 정리 → Clova Note (30분 → 5분)\n"
            "3. 보고서 초안 → Claude (1시간 → 20분)\n\n"
            "이거 안 하면 매일 2시간 손해보는 겁니다\n\n"
            "직장인 친구한테 공유해주세요"
        ),
        "cta_type": "공유유도",
        "hashtags": ["#직장인", "#AI활용", "#생산성"],
    },
    {
        "id": "tip-08",
        "category": "ai_tip",
        "hook_type": "도발형",
        "platform": "both",
        "content": (
            "\"AI 자격증 따야 하나요?\"\n\n"
            "솔직히? 아직은 별로입니다\n\n"
            "지금 AI 시장은 자격증보다:\n"
            "→ 실제로 뭘 만들어봤는지\n"
            "→ 어떤 문제를 풀어봤는지\n"
            "→ 포트폴리오가 있는지\n\n"
            "가 100배 중요해요\n\n"
            "자격증 vs 실전, 어떻게 생각하세요?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI", "#자기계발", "#커리어"],
    },
    {
        "id": "tip-09",
        "category": "ai_tip",
        "hook_type": "스토리형",
        "platform": "both",
        "content": (
            "ChatGPT 처음 썼을 때 충격받은 경험\n\n"
            "3시간 걸리던 기획서를 30분 만에 끝냈거든요\n\n"
            "근데 진짜 충격은 그 다음이었어요\n"
            "AI가 제안한 아이디어 중 하나가 실제로 채택됨\n\n"
            "AI를 잘 쓰면 '일 잘하는 사람'이 될 수 있습니다\n"
            "아직 안 써봤으면 오늘 시작하세요"
        ),
        "cta_type": "팔로우유도",
        "hashtags": ["#ChatGPT", "#AI활용", "#직장인"],
    },
    {
        "id": "tip-10",
        "category": "ai_tip",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "AI로 부업하는 사람들은 뭘 하고 있을까?\n\n"
            "→ 블로그 글 대필 (월 50-100만원)\n"
            "→ AI 이미지 생성 (상세페이지, 썸네일)\n"
            "→ 프롬프트 판매 (해외 마켓플레이스)\n"
            "→ AI 음악 제작 (BGM, 유튜브)\n"
            "→ 자동화 대행 (업무 자동화 세팅)\n\n"
            "시작이 어려우면 하나만 골라서 이번 주에 해보세요\n\n"
            "관심 있는 분야 댓글로 알려주세요"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI부업", "#부업", "#사이드프로젝트"],
    },
    {
        "id": "tip-11",
        "category": "ai_tip",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "Claude가 ChatGPT보다 나은 딱 한 가지\n\n"
            "긴 문서 분석\n\n"
            "계약서, 논문, 보고서 같은 긴 글 넣으면\n"
            "Claude가 압도적으로 정확함\n\n"
            "팁: \"이 문서에서 리스크 요인 5가지 뽑아줘\"\n"
            "이런 식으로 구체적으로 물어보면 진짜 잘함\n\n"
            "저장해두고 다음에 써보세요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#Claude", "#AI활용", "#생산성"],
    },
    {
        "id": "tip-12",
        "category": "ai_tip",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "프롬프트 3줄 공식 (이것만 외우세요)\n\n"
            "1줄: 역할 부여 — \"너는 ~전문가야\"\n"
            "2줄: 맥락 설명 — \"상황은 이러해\"\n"
            "3줄: 구체적 요청 — \"~형식으로 ~개 만들어줘\"\n\n"
            "이 구조로 물어보면 아무렇게나 물어보는 것보다\n"
            "결과물이 확실히 다릅니다\n\n"
            "스크린샷 찍어두세요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#프롬프트", "#ChatGPT", "#AI활용법"],
    },
    {
        "id": "tip-13",
        "category": "ai_tip",
        "hook_type": "공감형",
        "platform": "both",
        "content": (
            "AI 시대에 불안한 거 당연합니다\n\n"
            "근데 불안해만 하고 있으면 진짜 뒤처져요\n\n"
            "지금 당장 할 수 있는 거:\n"
            "→ ChatGPT 무료 가입 (5분)\n"
            "→ 오늘 할 일 정리해달라고 해보기 (1분)\n"
            "→ 결과물 보고 '오' 하기 (10초)\n\n"
            "여기서 시작하면 됩니다\n"
            "완벽하게 배우려 하지 마세요. 일단 써보세요"
        ),
        "cta_type": "공유유도",
        "hashtags": ["#AI", "#자기계발", "#인공지능"],
    },
    {
        "id": "tip-14",
        "category": "ai_tip",
        "hook_type": "리스트형",
        "platform": "both",
        "content": (
            "AI 입문자가 첫 주에 할 일 체크리스트\n\n"
            "□ ChatGPT 가입하고 3가지 질문하기\n"
            "□ Claude 가입하고 문서 하나 분석해보기\n"
            "□ Perplexity로 궁금한 거 검색해보기\n"
            "□ AI로 이메일 초안 하나 써보기\n"
            "□ 결과물 스크린샷 찍어서 기록하기\n\n"
            "이거 다 하면 이미 상위 20%입니다\n\n"
            "저장해두고 하나씩 체크해보세요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#AI입문", "#AI공부", "#ChatGPT"],
    },
    {
        "id": "tip-15",
        "category": "ai_tip",
        "hook_type": "충격형",
        "platform": "both",
        "content": (
            "AI로 음악 만드는 시대가 진짜 왔습니다\n\n"
            "Suno AI에 \"신나는 K-pop\" 한 줄 치면\n"
            "3분짜리 노래가 30초 만에 나옴\n\n"
            "가사도, 멜로디도, 보컬도 전부 AI가\n\n"
            "음악 전공 아니어도 됩니다\n"
            "한번 들어보면 소름 돋을 겁니다\n\n"
            "써본 적 있나요?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#SunoAI", "#AI음악", "#생성형AI"],
    },
    {
        "id": "tip-16",
        "category": "ai_tip",
        "hook_type": "도발형",
        "platform": "both",
        "content": (
            "\"AI 공부는 나중에 해야지\"\n\n"
            "이 말 하는 사람들 특징:\n"
            "→ 1년 후에도 똑같은 말 함\n"
            "→ 남들이 AI로 일하는 거 보고 부러워함\n"
            "→ 결국 급해져서 비싼 강의 지름\n\n"
            "나중은 없습니다\n"
            "오늘 ChatGPT 한 번 열어보세요\n"
            "그게 시작입니다"
        ),
        "cta_type": "공유유도",
        "hashtags": ["#AI", "#자기계발", "#동기부여"],
    },
    {
        "id": "tip-17",
        "category": "ai_tip",
        "hook_type": "스토리형",
        "platform": "both",
        "content": (
            "AI로 유튜브 썸네일 만들어봤는데\n"
            "디자이너한테 맡기던 것보다 나음\n\n"
            "쓴 도구: Midjourney + Canva\n"
            "소요 시간: 5분\n"
            "비용: 0원\n\n"
            "디자인 감각 없어도 됩니다\n"
            "AI한테 \"유튜브 썸네일, 밝은 톤, 한국어 텍스트\" 하면 끝\n\n"
            "다음에 방법 자세히 올릴게요\n"
            "팔로우 해두세요"
        ),
        "cta_type": "팔로우유도",
        "hashtags": ["#AI디자인", "#유튜브", "#Midjourney"],
    },
    {
        "id": "tip-18",
        "category": "ai_tip",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "회사에서 AI 쓰는 거 눈치 보이시나요?\n\n"
            "솔직히 많은 분들이 그렇더라고요\n"
            "\"AI로 했다고 하면 능력 없어 보일까 봐\"\n\n"
            "근데 생각해보세요\n"
            "엑셀 쓴다고 능력 없다고 안 하잖아요\n"
            "AI도 도구입니다\n\n"
            "잘 쓰는 게 능력이에요\n\n"
            "회사에서 AI 쓰는 거 오픈하시나요? 숨기시나요?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#직장인", "#AI활용", "#커리어"],
    },
    {
        "id": "tip-19",
        "category": "ai_tip",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "AI한테 피드백 받는 방법 (이거 진짜 꿀팁)\n\n"
            "자기가 쓴 글이나 기획서를 AI한테 넣고\n"
            "\"이 글의 약점 3가지와 개선안을 알려줘\" 하면\n\n"
            "솔직한 피드백이 바로 나옴\n\n"
            "사수 없는 분들한테 특히 유용합니다\n"
            "AI를 리뷰어로 쓰세요\n\n"
            "저장 필수"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#AI활용", "#생산성", "#직장인팁"],
    },
    {
        "id": "tip-20",
        "category": "ai_tip",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "AI 활용 능력, 5단계로 체크해보세요\n\n"
            "Lv.1 — 가입만 함\n"
            "Lv.2 — 가끔 질문함\n"
            "Lv.3 — 업무에 매일 씀\n"
            "Lv.4 — 자동화까지 활용\n"
            "Lv.5 — AI로 수익 창출\n\n"
            "대부분 Lv.2에서 멈춰요\n"
            "Lv.3으로 가는 게 가장 어렵고 가장 중요합니다\n\n"
            "지금 몇 레벨이세요?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI", "#자기계발", "#AI활용"],
    },

    # ==============================
    # host_recruit (5개) — 호스트 섭외용
    # ==============================
    {
        "id": "host-01",
        "category": "host_recruit",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "혹시 잘하는 게 있는데 알려줄 곳이 없으신 분?\n\n"
            "AI든 마케팅이든 디자인이든\n"
            "실력은 있는데 강의는 부담스러운 분들 많잖아요\n\n"
            "HYPERS에서는:\n"
            "→ 장소 무료 제공 (성수)\n"
            "→ 홍보 대행\n"
            "→ 상세 페이지 제작\n"
            "→ 얼굴 공개 안 해도 됨 (GPT 프로필)\n\n"
            "당신의 지식을 가볍게 공유해보세요\n"
            "관심 있으면 DM 주세요"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#호스트모집", "#AI커뮤니티", "#HYPERS"],
    },
    {
        "id": "host-02",
        "category": "host_recruit",
        "hook_type": "스토리형",
        "platform": "both",
        "content": (
            "스레드에서 좋은 글 쓰는 분들 보면 항상 생각해요\n\n"
            "\"이 사람 오프라인에서 만나서 배우고 싶다\"\n\n"
            "근데 대부분 강의 같은 건 안 하시더라고요\n"
            "이유를 물어보니:\n"
            "→ 장소 구하기 귀찮아서\n"
            "→ 홍보를 어떻게 해야 할지 몰라서\n"
            "→ 얼굴 까는 게 부담돼서\n\n"
            "이 3가지 다 해결해드립니다\n"
            "은둔 고수분들, DM 주세요"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#은둔고수", "#HYPERS", "#AI워크숍"],
    },
    {
        "id": "host-03",
        "category": "host_recruit",
        "hook_type": "공감형",
        "platform": "both",
        "content": (
            "솔직히 스레드에 글 올리면서\n"
            "\"이걸 강의로 만들면 어떨까?\" 생각해본 적 있지 않나요?\n\n"
            "근데 시작이 어려운 거잖아요\n"
            "장소는? 홍보는? 가격은? 사람은?\n\n"
            "그거 다 우리가 해드립니다\n"
            "당신은 지식만 가져오면 됩니다\n\n"
            "소프트 런칭이라 부담 없어요\n"
            "먼저 가볍게 이야기 나눠봐요"
        ),
        "cta_type": "링크유도",
        "hashtags": ["#호스트", "#AI커뮤니티", "#HYPERS"],
    },
    {
        "id": "host-04",
        "category": "host_recruit",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "잘 나가는 클래스 호스트들의 공통점\n\n"
            "→ 처음부터 완벽하게 안 했음\n"
            "→ 소규모로 먼저 테스트했음\n"
            "→ 누군가 세팅을 도와줬음\n\n"
            "HYPERS가 그 '누군가'가 되어드립니다\n\n"
            "3월 16일 런칭 예정\n"
            "호스트로 함께할 분 찾고 있어요\n\n"
            "DM으로 편하게 연락주세요"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#HYPERS", "#호스트모집", "#AI클래스"],
    },
    {
        "id": "host-05",
        "category": "host_recruit",
        "hook_type": "도발형",
        "platform": "both",
        "content": (
            "유료 강의 플랫폼의 문제점 아시나요?\n\n"
            "수수료 15%+ 떼감\n"
            "홍보는 알아서\n"
            "장소도 알아서\n\n"
            "호스트가 해야 할 일이 너무 많음\n\n"
            "HYPERS는 다릅니다:\n"
            "→ 수수료 10% 이하\n"
            "→ 홍보 대행\n"
            "→ 성수 장소 무료\n"
            "→ 상세 페이지 제작\n\n"
            "호스트가 '지식 전달'에만 집중할 수 있게\n"
            "관심 있으면 연락주세요"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#HYPERS", "#호스트", "#AI워크숍"],
    },

    # ==============================
    # participant (10개) — 참여자 유입용
    # ==============================
    {
        "id": "part-01",
        "category": "participant",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "AI 배우고 싶은데 어디서 시작해야 할지 모르겠다면\n\n"
            "유튜브? 너무 많아서 뭘 봐야 할지 모름\n"
            "유료 강의? 비싸고 질러놓고 안 봄\n"
            "독학? 혼자 하니까 작심삼일\n\n"
            "HYPERS는 다양한 분야 전문가를 한 곳에 모았어요\n"
            "통합 입장권 하나로 뷔페처럼 골라 들을 수 있음\n\n"
            "3월 16일 런칭\n"
            "관심 있으면 '나도' 댓글 남겨주세요"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#AI공부", "#AI커뮤니티", "#HYPERS"],
    },
    {
        "id": "part-02",
        "category": "participant",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "55,000원으로 AI 전문가 여러 명한테 배우는 방법\n\n"
            "보통 AI 강의 하나에 10-30만원인데\n"
            "HYPERS 통합 입장권이면\n"
            "여러 호스트의 강의를 뷔페처럼 수강 가능\n\n"
            "AI 음악, 프롬프트, 자동화, 마케팅...\n"
            "원하는 것만 골라 들으세요\n\n"
            "얼리버드 33,000원\n"
            "자세한 건 프로필 링크에서"
        ),
        "cta_type": "링크유도",
        "hashtags": ["#HYPERS", "#AI클래스", "#얼리버드"],
    },
    {
        "id": "part-03",
        "category": "participant",
        "hook_type": "공감형",
        "platform": "both",
        "content": (
            "AI 혼자 공부하다 지친 분 손\n\n"
            "→ 유튜브 알고리즘에 끌려다니고\n"
            "→ 뭘 배워야 할지 모르겠고\n"
            "→ 주변에 물어볼 사람이 없고\n\n"
            "커뮤니티의 힘이 여기서 나옵니다\n"
            "같이 배우면 빠르고, 같이 하면 안 빠지게 됨\n\n"
            "HYPERS 3기가 3월 16일 시작해요\n"
            "같이 하실 분?"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#AI공부", "#AI커뮤니티", "#HYPERS"],
    },
    {
        "id": "part-04",
        "category": "participant",
        "hook_type": "충격형",
        "platform": "both",
        "content": (
            "강의 하나 가격으로 강의 여러 개를 들을 수 있다면?\n\n"
            "HYPERS의 통합 입장권 구조:\n"
            "→ 하나의 입장권으로 모든 호스트 강의 수강\n"
            "→ AI 음악, 프롬프트, 자동화, 마케팅 등\n"
            "→ 온라인 기본 + 오프라인(성수) 추가 가능\n\n"
            "지식의 뷔페입니다\n"
            "관심 있으면 댓글 남겨주세요"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#HYPERS", "#AI강의", "#통합입장권"],
    },
    {
        "id": "part-05",
        "category": "participant",
        "hook_type": "스토리형",
        "platform": "both",
        "content": (
            "처음에 10명으로 시작한 모임이 있습니다\n\n"
            "AI에 관심 있는 사람들끼리 모여서\n"
            "각자 알고 있는 것을 나누기 시작했어요\n\n"
            "그게 지금 HYPERS가 됐습니다\n\n"
            "호스트는 자기 전문성을 공유하고\n"
            "참여자는 뷔페처럼 골라 배우는 구조\n\n"
            "3기 런칭 3월 16일\n"
            "함께 성장하고 싶은 분, 환영합니다"
        ),
        "cta_type": "링크유도",
        "hashtags": ["#HYPERS", "#AI커뮤니티", "#함께성장"],
    },
    {
        "id": "part-06",
        "category": "participant",
        "hook_type": "리스트형",
        "platform": "both",
        "content": (
            "HYPERS 3기에서 배울 수 있는 것들\n\n"
            "→ AI 음악 제작 (Suno 고급 활용)\n"
            "→ 프롬프트 엔지니어링 실전\n"
            "→ AI 자동화로 업무 효율화\n"
            "→ 마케팅에 AI 활용하기\n"
            "→ 그 외 은둔 고수들의 시크릿 세션\n\n"
            "하나의 입장권으로 전부 수강 가능\n\n"
            "3월 16일 성수에서 만나요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#HYPERS", "#AI클래스", "#성수"],
    },
    {
        "id": "part-07",
        "category": "participant",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "커뮤니티에서 배우는 게 왜 빠른지 아세요?\n\n"
            "혼자 공부: 삽질 → 포기 → 재시작 → 반복\n"
            "커뮤니티: 삽질 → 질문 → 해결 → 다음 단계\n\n"
            "중간에 끊기는 게 없어서 빠른 겁니다\n\n"
            "HYPERS는 다양한 분야 전문가가\n"
            "직접 답해주는 커뮤니티예요\n\n"
            "같이 하실 분 있나요?"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#AI커뮤니티", "#HYPERS", "#함께배우기"],
    },
    {
        "id": "part-08",
        "category": "participant",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "HYPERS 3기 핵심 정리\n\n"
            "언제: 3월 16일 런칭\n"
            "어디: 온라인 + 성수 오프라인\n"
            "뭘: AI 활용 전문가들의 뷔페식 강의\n"
            "얼마: 얼리버드 33,000원\n\n"
            "통합 입장권 하나로 모든 호스트 강의 수강\n"
            "한 번에 다양한 분야를 맛볼 수 있어요\n\n"
            "저장해두고 3월에 봐요"
        ),
        "cta_type": "저장유도",
        "hashtags": ["#HYPERS", "#3기", "#얼리버드"],
    },
    {
        "id": "part-09",
        "category": "participant",
        "hook_type": "도발형",
        "platform": "both",
        "content": (
            "AI 강의 10개 결제해놓고 1개도 안 본 사람?\n\n"
            "...저도요\n\n"
            "혼자 보는 VOD는 작심삼일이 당연합니다\n"
            "같이 하는 사람이 없으니까\n\n"
            "HYPERS는 라이브 + 커뮤니티 구조라\n"
            "같이 듣고, 같이 질문하고, 같이 성장합니다\n\n"
            "이번엔 진짜 끝까지 해보실 분?"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#AI공부", "#AI커뮤니티", "#HYPERS"],
    },
    {
        "id": "part-10",
        "category": "participant",
        "hook_type": "질문형",
        "platform": "both",
        "content": (
            "성수에서 AI 배우면서 네트워킹까지 할 수 있다면?\n\n"
            "HYPERS 오프라인 세션:\n"
            "→ 성수 상상 플래닛\n"
            "→ 소규모 워크숍 (직접 실습)\n"
            "→ 호스트와 1:1 대화 가능\n"
            "→ 참여자끼리 네트워킹\n\n"
            "온라인만으로는 얻을 수 없는 경험이에요\n\n"
            "성수에서 만나요"
        ),
        "cta_type": "링크유도",
        "hashtags": ["#성수", "#AI워크숍", "#HYPERS"],
    },

    # ==============================
    # fomo (5개) — 기대감/FOMO 증폭
    # ==============================
    {
        "id": "fomo-01",
        "category": "fomo",
        "hook_type": "충격형",
        "platform": "both",
        "content": (
            "HYPERS 3기 준비 중인데\n"
            "벌써 호스트 라인업이 미쳤습니다\n\n"
            "아직 공개 전인데\n"
            "한 분은 스레드 팔로워 5자리\n"
            "한 분은 현업 마케터\n"
            "한 분은 AI 음악으로 수익화 중\n\n"
            "3월 16일 공개됩니다\n"
            "얼리버드는 그 전에 마감될 수 있어요\n\n"
            "알림 설정해두세요"
        ),
        "cta_type": "팔로우유도",
        "hashtags": ["#HYPERS", "#3기", "#호스트라인업"],
    },
    {
        "id": "fomo-02",
        "category": "fomo",
        "hook_type": "숫자형",
        "platform": "both",
        "content": (
            "HYPERS 3기 런칭까지 D-24\n\n"
            "지금까지 준비된 것:\n"
            "→ 호스트 라인업 (비공개)\n"
            "→ 온라인/오프라인 프로그램 설계\n"
            "→ 성수 장소 확정\n"
            "→ 얼리버드 가격 확정 (33,000원)\n\n"
            "2기보다 완전히 달라진 구조\n"
            "기대해주세요\n\n"
            "얼리버드 놓치지 마세요"
        ),
        "cta_type": "링크유도",
        "hashtags": ["#HYPERS", "#D24", "#얼리버드"],
    },
    {
        "id": "fomo-03",
        "category": "fomo",
        "hook_type": "비밀공유형",
        "platform": "both",
        "content": (
            "HYPERS 3기 살짝 스포하면\n\n"
            "이번에는 '통합 입장권' 구조입니다\n"
            "= 하나의 입장권으로 모든 호스트 강의 수강\n\n"
            "좋아하는 것만 골라 듣는 뷔페 방식\n\n"
            "이거... 기존 AI 교육 시장에 없던 구조예요\n\n"
            "3월 16일 오픈\n"
            "먼저 알고 싶으면 팔로우해두세요"
        ),
        "cta_type": "팔로우유도",
        "hashtags": ["#HYPERS", "#통합입장권", "#AI커뮤니티"],
    },
    {
        "id": "fomo-04",
        "category": "fomo",
        "hook_type": "공감형",
        "platform": "both",
        "content": (
            "2기 참여자 중에 이런 분이 있었어요\n\n"
            "\"AI 아무것도 모르는데 괜찮을까요?\"\n\n"
            "지금은 본인이 다른 분한테 알려주고 있습니다\n\n"
            "시작할 때는 다 초보예요\n"
            "중요한 건 '같이 하는 환경'이었어요\n\n"
            "3기에서 그 환경 만들어드립니다\n"
            "3월 16일 런칭"
        ),
        "cta_type": "참여유도",
        "hashtags": ["#HYPERS", "#AI입문", "#AI커뮤니티"],
    },
    {
        "id": "fomo-05",
        "category": "fomo",
        "hook_type": "스토리형",
        "platform": "both",
        "content": (
            "HYPERS를 만들게 된 이유\n\n"
            "AI 교육 시장을 보면\n"
            "→ 비싼 VOD는 안 봄\n"
            "→ 무료 유튜브는 체계 없음\n"
            "→ 커뮤니티는 잡담방이 됨\n\n"
            "\"호스트가 지식을 나누고\n"
            "참여자가 골라 배우는 구조를 만들면 어떨까?\"\n\n"
            "그게 HYPERS입니다\n\n"
            "3월 16일, 성수에서 시작합니다\n"
            "함께해주실 분, 댓글 남겨주세요"
        ),
        "cta_type": "댓글유도",
        "hashtags": ["#HYPERS", "#AI커뮤니티", "#성수"],
    },
]


def get_contents_by_category(category: str) -> list[dict]:
    """카테고리별 콘텐츠 필터"""
    return [c for c in CONTENTS if c["category"] == category]


def get_content_by_id(content_id: str) -> dict | None:
    """ID로 콘텐츠 조회"""
    for c in CONTENTS:
        if c["id"] == content_id:
            return c
    return None
