"""
뉴스 스코어링/선별 — heysquid

순수 로직 모듈. HTTP 호출 없음.
뉴스 아이템 리스트를 받아 스코어링, 랭킹, 기준별 선별, 스레드 선별.
"""

import re
import time

from ._news_fetcher import AI_KEYWORDS


def _title_similarity(a, b):
    """두 제목의 단어 겹침 비율 (Jaccard 유사도)"""
    words_a = set(re.findall(r'\w+', a.lower()))
    words_b = set(re.findall(r'\w+', b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def score_and_rank_news(all_items, top_n=5):
    """
    5가지 기준으로 뉴스 스코어링 후 상위 N개 반환.

    기준:
    1. 최신성 (recency): 24시간 이내 우선, 12시간 이내 보너스
    2. 소스 다양성 (cross_source): 여러 소스에 비슷한 제목이면 가산
    3. 인기도 (popularity): points 기반
    4. AI 관련성 (ai_relevance): 제목에 AI 키워드 포함
    5. 토론성 (discussion): comments 수 기반
    """
    now_ts = time.time()
    max_points = max((item["points"] for item in all_items), default=1) or 1
    max_comments = max((item["comments"] for item in all_items), default=1) or 1

    # RSS 소스(TC/MIT)는 points=0이므로, 비-제로 아이템의 중간값으로 보정
    nonzero_points = [i["points"] for i in all_items if i["points"] > 0]
    median_points = sorted(nonzero_points)[len(nonzero_points) // 2] if nonzero_points else 0
    nonzero_comments = [i["comments"] for i in all_items if i["comments"] > 0]
    median_comments = sorted(nonzero_comments)[len(nonzero_comments) // 2] if nonzero_comments else 0

    for item in all_items:
        score = 0.0

        # 1. 최신성 (0~25점)
        age_hours = (now_ts - item["timestamp"]) / 3600 if item["timestamp"] > 0 else 48
        if age_hours <= 6:
            score += 25
        elif age_hours <= 12:
            score += 20
        elif age_hours <= 24:
            score += 15
        elif age_hours <= 48:
            score += 5

        # 2. 소스 다양성 (0~20점)
        cross_count = 0
        seen_sources = {item["source"]}
        for other in all_items:
            if other["source"] in seen_sources:
                continue
            if _title_similarity(item["title"], other["title"]) > 0.3:
                cross_count += 1
                seen_sources.add(other["source"])
        score += min(cross_count * 10, 20)

        # 3. 인기도 (0~25점) — RSS 소스(points=0)는 중간값으로 보정
        effective_points = item["points"] if item["points"] > 0 else median_points
        score += (effective_points / max_points) * 25

        # 4. AI 관련성 (0~20점)
        ai_matches = len(AI_KEYWORDS.findall(item["title"]))
        if ai_matches >= 2:
            score += 20
        elif ai_matches == 1:
            score += 15

        # 5. 토론성 (0~10점) — RSS 소스(comments=0)는 중간값으로 보정
        effective_comments = item["comments"] if item["comments"] > 0 else median_comments
        score += (effective_comments / max_comments) * 10

        item["_score"] = round(score, 2)

    # 점수 내림차순 정렬
    ranked = sorted(all_items, key=lambda x: x["_score"], reverse=True)

    # 중복 제거 (유사도 > 0.4인 경우 낮은 점수 것 제거)
    deduped = []
    for item in ranked:
        is_dup = False
        for selected in deduped:
            if _title_similarity(item["title"], selected["title"]) > 0.4:
                is_dup = True
                break
        if not is_dup:
            deduped.append(item)
        if len(deduped) >= top_n:
            break

    return deduped


def pick_best_per_criterion(all_items):
    """
    방법2: 기준별 1픽 (5개 세트)
    각 기준에서 최고점 1개씩 선별.

    Returns:
        list[dict]: [{"criterion": ..., "item": ...}, ...]
    """
    now_ts = time.time()
    max_points = max((item["points"] for item in all_items), default=1) or 1
    max_comments = max((item["comments"] for item in all_items), default=1) or 1

    # RSS 소스 보정용 중간값
    nonzero_points = [i["points"] for i in all_items if i["points"] > 0]
    _median_pts = sorted(nonzero_points)[len(nonzero_points) // 2] if nonzero_points else 0
    nonzero_comments = [i["comments"] for i in all_items if i["comments"] > 0]
    _median_cmt = sorted(nonzero_comments)[len(nonzero_comments) // 2] if nonzero_comments else 0

    criteria = {
        "최신성": lambda item: 25 - min((now_ts - item["timestamp"]) / 3600, 48) * 0.52 if item["timestamp"] > 0 else 0,
        "소스 다양성": lambda item: sum(
            1 for other in all_items
            if other["source"] != item["source"] and _title_similarity(item["title"], other["title"]) > 0.3
        ),
        "반응/인기": lambda item: item["points"] if item["points"] > 0 else _median_pts,
        "AI 관련성": lambda item: len(AI_KEYWORDS.findall(item["title"])) * 10 + (5 if AI_KEYWORDS.search(item.get("url", "")) else 0),
        "토론성": lambda item: item["comments"] if item["comments"] > 0 else _median_cmt,
    }

    picks = []
    used_titles = set()

    for criterion_name, score_fn in criteria.items():
        best = None
        best_score = -1
        for item in all_items:
            is_dup = any(_title_similarity(item["title"], t) > 0.4 for t in used_titles)
            if is_dup:
                continue
            s = score_fn(item)
            if s > best_score:
                best_score = s
                best = item
        if best:
            picks.append({"criterion": criterion_name, "item": best})
            used_titles.add(best["title"])

    return picks


def select_thread_worthy(all_items, top_n=5):
    """
    스레드 인기글 패턴 분석 기반 기사 선별.

    패턴 (우선순위):
    1. 전문지식/경험 공유형 — 기술 깊이가 있는 글
    2. 토론/논쟁 유도형 — 댓글 많은 글
    3. 충격 숫자/반전형 — 구체적 숫자가 있는 글
    4. 트렌드 속보형 — 최신 뉴스
    5. 공감형 — 직장인/개발자 감정 터치

    Returns:
        list[dict]: [{"pattern": ..., "item": ..., "reason": ...}, ...]
    """
    now_ts = time.time()
    has_number = re.compile(r'\d+[%$억만천]|\$\d|billion|million')
    debate_words = re.compile(r'(vs|versus|debate|controversy|ban|block|concern|risk|danger|threat|ethical|privacy|layoff|replace|kill|die|end|crisis|scandal|fired)', re.I)
    empathy_words = re.compile(r'(developer|engineer|worker|employee|job|career|salary|burnout|remote|work|hire|fired|layoff)', re.I)

    patterns = []

    # 1. 전문지식형: AI관련 + points 높은 것
    tech_items = [i for i in all_items if AI_KEYWORDS.search(i["title"]) and i["points"] > 0]
    tech_items.sort(key=lambda x: x["points"], reverse=True)

    # 2. 토론형: 댓글 많은 것
    debate_items = sorted(all_items, key=lambda x: x["comments"], reverse=True)

    # 3. 충격 숫자형: 숫자가 있는 제목
    number_items = [i for i in all_items if has_number.search(i["title"])]
    number_items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    # 4. 속보형: 가장 최신
    recent_items = [i for i in all_items if i["timestamp"] > 0]
    recent_items.sort(key=lambda x: x["timestamp"], reverse=True)

    # 5. 공감형: 직장/커리어 관련
    empathy_items = [i for i in all_items if empathy_words.search(i["title"])]
    empathy_items.sort(key=lambda x: x.get("_score", 0), reverse=True)

    used_titles = set()

    def pick_first_unused(candidates, pattern_name, reason):
        for item in candidates:
            is_dup = any(_title_similarity(item["title"], t) > 0.4 for t in used_titles)
            if not is_dup:
                used_titles.add(item["title"])
                patterns.append({"pattern": pattern_name, "item": item, "reason": reason})
                return True
        return False

    pick_first_unused(tech_items, "전문지식 공유형", "기술 깊이 + 높은 관심")
    pick_first_unused(debate_items, "토론/논쟁 유도형", "댓글 폭발 → 알고리즘 부스트")
    pick_first_unused(number_items, "충격 숫자형", "구체적 숫자 → 체류시간 증가")
    pick_first_unused(recent_items, "트렌드 속보형", "24시간 내 빠른 반응")
    pick_first_unused(empathy_items, "공감형", "직장인/개발자 감정 터치")

    # 5개 미만이면 나머지를 스코어 기준으로 채움
    if len(patterns) < top_n:
        remaining = sorted(all_items, key=lambda x: x.get("_score", 0), reverse=True)
        for item in remaining:
            if len(patterns) >= top_n:
                break
            is_dup = any(_title_similarity(item["title"], t) > 0.4 for t in used_titles)
            if not is_dup:
                used_titles.add(item["title"])
                patterns.append({"pattern": "추가 선별", "item": item, "reason": "종합 스코어 상위"})

    return patterns[:top_n]
