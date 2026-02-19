"""
일일 브리핑 생성기 — heysquid

매일 아침 프로젝트 상태를 분석하여 텔레그램으로 전송.

분석 대상:
- 각 워크스페이스의 git log (최근 24h)
- tasks/ 디렉토리 (미처리 작업)
- workspaces/{name}/progress.md
- 멀티소스 IT/AI 뉴스 TOP 5
- 스레드 글 초안 자동 생성

사용법:
    python briefing.py          # 수동 실행
    (launchd로 매일 09:00 자동 실행)
"""

import os
import sys
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError
from dotenv import load_dotenv

# 경로 설정
from .config import PROJECT_ROOT_STR as PROJECT_ROOT, get_env_path

# .env 로드
load_dotenv(get_env_path())

CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()


def get_git_summary(repo_path):
    """
    Git 저장소의 최근 24시간 커밋 요약

    Args:
        repo_path: Git 저장소 경로

    Returns:
        str: 커밋 요약 텍스트
    """
    if not os.path.exists(os.path.join(repo_path, ".git")):
        return "(git 저장소 아님)"

    try:
        since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={since}", "--no-merges"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return "(git log 오류)"

        lines = result.stdout.strip().split("\n")
        lines = [l for l in lines if l.strip()]

        if not lines:
            return "최근 24시간 커밋 없음"

        return f"최근 24시간 커밋 {len(lines)}건:\n" + "\n".join(f"  - {l}" for l in lines[:10])

    except subprocess.TimeoutExpired:
        return "(git log 타임아웃)"
    except Exception as e:
        return f"(git 오류: {e})"


def get_pending_tasks():
    """미처리 텔레그램 메시지 수 확인"""
    messages_file = os.path.join(PROJECT_ROOT, "data", "telegram_messages.json")

    if not os.path.exists(messages_file):
        return 0

    try:
        with open(messages_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        pending = [m for m in messages if not m.get("processed", False) and m.get("type") == "user"]
        return len(pending)

    except Exception:
        return 0


def get_recent_progress(name):
    """최근 진행 기록 (마지막 3개 항목)"""
    progress_file = os.path.join(PROJECT_ROOT, "workspaces", name, "progress.md")

    if not os.path.exists(progress_file):
        return "진행 기록 없음"

    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            content = f.read()

        # ### 으로 시작하는 항목 추출
        entries = content.split("### ")
        entries = [e.strip() for e in entries if e.strip() and not e.startswith("#")]

        if not entries:
            return "진행 기록 없음"

        # 마지막 3개
        recent = entries[-3:]
        return "\n".join(f"  - {e.split(chr(10))[0]}" for e in recent)

    except Exception:
        return "진행 기록 없음"


def fetch_geeknews_top(count=10):
    """GeekNews(news.hada.io) 메인 페이지에서 포인트 기준 인기 뉴스 추출"""
    try:
        req = Request(
            "https://news.hada.io/",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")

        # <h1>제목</h1> ... topic?id=ID ... id='tpID'>POINTS</span> point
        pattern = r"<h1>(.*?)</h1>.*?topic\?id=(\d+).*?id='tp\d+'>(\d+)</span>\s*point"
        matches = re.findall(pattern, html, re.DOTALL)

        news_items = []
        for title, topic_id, points in matches:
            title = re.sub(r'<[^>]+>', '', title).strip()
            if not title:
                continue
            news_items.append({
                "title": title,
                "url": f"https://news.hada.io/topic?id={topic_id}",
                "points": int(points)
            })

        # 포인트 기준 내림차순 정렬
        news_items.sort(key=lambda x: x["points"], reverse=True)
        return news_items[:count]

    except (URLError, Exception) as e:
        print(f"[WARN] GeekNews 크롤링 오류: {e}")
        return []


def format_geeknews(news_items):
    """GeekNews 뉴스를 텔레그램 포맷으로 변환"""
    if not news_items:
        return "GeekNews 뉴스를 가져오지 못했어요."

    lines = [f"GeekNews 오늘의 핫 뉴스 TOP {len(news_items)}", ""]
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"⭐ {item['url']}")
        lines.append("")

    return "\n".join(lines).strip()


# ============================================================
# 멀티소스 뉴스 수집 + TOP 5 + 스레드 글 생성
# ============================================================

AI_KEYWORDS = re.compile(
    r'\b(ai|a\.i\.|artificial intelligence|llm|gpt|chatgpt|openai|claude|anthropic|'
    r'gemini|copilot|diffusion|stable diffusion|midjourney|machine learning|deep learning|'
    r'neural|transformer|hugging\s?face|langchain|rag|agent|fine.?tun|sora|groq|mistral|'
    r'llama|generative|gen\s?ai)\b',
    re.IGNORECASE
)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def fetch_hackernews_top(count=30):
    """Hacker News API에서 상위 스토리 가져오기"""
    try:
        req = Request(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            headers={"User-Agent": _UA}
        )
        with urlopen(req, timeout=10) as resp:
            story_ids = json.loads(resp.read().decode("utf-8"))

        items = []
        for sid in story_ids[:count]:
            try:
                req = Request(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    headers={"User-Agent": _UA}
                )
                with urlopen(req, timeout=5) as resp:
                    story = json.loads(resp.read().decode("utf-8"))

                if not story or story.get("type") != "story":
                    continue

                items.append({
                    "title": story.get("title", ""),
                    "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    "points": story.get("score", 0),
                    "comments": story.get("descendants", 0),
                    "timestamp": story.get("time", 0),
                    "source": "HackerNews",
                })
            except Exception:
                continue

        return items

    except (URLError, Exception) as e:
        print(f"[WARN] HackerNews API 오류: {e}")
        return []


def _parse_rss(url, source_name, timeout=10):
    """RSS 피드를 파싱하여 뉴스 아이템 리스트 반환"""
    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read().decode("utf-8")

        root = ET.fromstring(xml_data)

        items = []
        # RSS 2.0 형식
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pubdate_el = item.find("pubDate")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link = link_el.text.strip() if link_el is not None and link_el.text else ""

            if not title:
                continue

            ts = 0
            if pubdate_el is not None and pubdate_el.text:
                ts = _parse_rss_date(pubdate_el.text)

            items.append({
                "title": title,
                "url": link,
                "points": 0,
                "comments": 0,
                "timestamp": ts,
                "source": source_name,
            })

        return items

    except (URLError, ET.ParseError, Exception) as e:
        print(f"[WARN] {source_name} RSS 오류: {e}")
        return []


def _parse_rss_date(date_str):
    """RFC 822 날짜 문자열을 Unix timestamp로 변환"""
    # 흔한 RSS 날짜 형식들
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return int(dt.timestamp())
        except ValueError:
            continue
    # fallback: 날짜 파싱 실패 시 0
    return 0


def fetch_techcrunch_rss(count=20):
    """TechCrunch RSS에서 뉴스 가져오기"""
    items = _parse_rss("https://techcrunch.com/feed/", "TechCrunch")
    return items[:count]


def fetch_mit_tech_review_rss(count=20):
    """MIT Technology Review RSS에서 뉴스 가져오기"""
    items = _parse_rss(
        "https://www.technologyreview.com/feed/", "MIT Tech Review"
    )
    return items[:count]


def fetch_all_news_sources():
    """모든 소스에서 뉴스를 수집하여 통합 리스트 반환"""
    all_items = []

    # GeekNews (기존 함수 활용, 통합 스코어링용 필드 추가)
    geeknews = fetch_geeknews_top(20)
    for item in geeknews:
        item.setdefault("source", "GeekNews")
        item.setdefault("comments", 0)
        item.setdefault("timestamp", int(time.time()))  # 시간 정보 없으므로 현재
        all_items.append(item)

    # Hacker News
    all_items.extend(fetch_hackernews_top(30))

    # TechCrunch
    all_items.extend(fetch_techcrunch_rss(20))

    # MIT Technology Review
    all_items.extend(fetch_mit_tech_review_rss(20))

    print(f"[INFO] 뉴스 수집 완료: 총 {len(all_items)}건 "
          f"(GN:{len(geeknews)}, HN:{len([i for i in all_items if i['source']=='HackerNews'])}, "
          f"TC:{len([i for i in all_items if i['source']=='TechCrunch'])}, "
          f"MIT:{len([i for i in all_items if i['source']=='MIT Tech Review'])})")

    return all_items


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
        # 48시간 이상: 0점

        # 2. 소스 다양성 (0~20점): 다른 소스에 비슷한 제목이 있으면 가산
        cross_count = 0
        seen_sources = {item["source"]}
        for other in all_items:
            if other["source"] in seen_sources:
                continue
            if _title_similarity(item["title"], other["title"]) > 0.3:
                cross_count += 1
                seen_sources.add(other["source"])
        score += min(cross_count * 10, 20)

        # 3. 인기도 (0~25점)
        score += (item["points"] / max_points) * 25

        # 4. AI 관련성 (0~20점)
        ai_matches = len(AI_KEYWORDS.findall(item["title"]))
        if ai_matches >= 2:
            score += 20
        elif ai_matches == 1:
            score += 15

        # 5. 토론성 (0~10점)
        score += (item["comments"] / max_comments) * 10

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

    criteria = {
        "최신성": lambda item: 25 - min((now_ts - item["timestamp"]) / 3600, 48) * 0.52 if item["timestamp"] > 0 else 0,
        "소스 다양성": lambda item: sum(
            1 for other in all_items
            if other["source"] != item["source"] and _title_similarity(item["title"], other["title"]) > 0.3
        ),
        "반응/인기": lambda item: item["points"],
        "AI 관련성": lambda item: len(AI_KEYWORDS.findall(item["title"])) * 10 + (5 if AI_KEYWORDS.search(item.get("url", "")) else 0),
        "토론성": lambda item: item["comments"],
    }

    picks = []
    used_titles = set()

    for criterion_name, score_fn in criteria.items():
        best = None
        best_score = -1
        for item in all_items:
            # 이미 선택된 것과 중복 방지
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
    # 숫자가 포함된 제목 감지
    has_number = re.compile(r'\d+[%$억만천]|\$\d|billion|million')

    # 논쟁 키워드
    debate_words = re.compile(r'(vs|versus|debate|controversy|ban|block|concern|risk|danger|threat|ethical|privacy|layoff|replace|kill|die|end|crisis|scandal|fired)', re.I)

    # 공감 키워드
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


def _scrape_summary(url, max_sentences=2):
    """기사 URL에서 핵심 요약 1-2문장 추출"""
    text = scrape_article(url, timeout=8)
    if not text or len(text) < 50:
        return ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    key = [s.strip() for s in sentences if 20 < len(s.strip()) < 200][:max_sentences]
    if not key:
        return ""
    summary = " ".join(key)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary


def format_top_news(top_items, label="방법1: 가중치 통합 랭킹", with_scrape=True):
    """종합 뉴스를 텔레그램 포맷으로 변환. 기사 요약 포함."""
    if not top_items:
        return f"{label}을 생성하지 못했어요."

    lines = [f"📌 {label}", ""]
    for i, item in enumerate(top_items, 1):
        src = item.get("source", "")
        score = item.get("_score", 0)
        badge = ""
        if AI_KEYWORDS.search(item["title"]):
            badge = " [AI]"
        lines.append(f"{i}. {item['title']}{badge} ({score}점)")
        lines.append(f"   [{src}] {item['url']}")
        if with_scrape:
            summary = _scrape_summary(item["url"])
            if summary:
                lines.append(f"   → {summary}")
        lines.append("")

    return "\n".join(lines).strip()


def format_criterion_picks(picks, with_scrape=True):
    """기준별 1픽을 텔레그램 포맷으로 변환. 기사 요약 포함."""
    if not picks:
        return "기준별 1픽을 생성하지 못했어요."

    lines = ["📌 방법2: 기준별 1픽 (5개 세트)", ""]
    for p in picks:
        item = p["item"]
        lines.append(f"{p['criterion']} → {item['title']}")
        lines.append(f"   [{item.get('source', '')}] {item['url']}")
        if with_scrape:
            summary = _scrape_summary(item["url"])
            if summary:
                lines.append(f"   → {summary}")
        lines.append("")

    return "\n".join(lines).strip()


def format_thread_picks(thread_picks):
    """스레드 맞춤 기사를 텔레그램 포맷으로 변환"""
    if not thread_picks:
        return "스레드 맞춤 기사를 선별하지 못했어요."

    lines = ["🎯 스레드 맞춤 기사 (패턴 분석 기반)", ""]
    for i, p in enumerate(thread_picks, 1):
        item = p["item"]
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   → {p['pattern']}. {p['reason']}")
        lines.append(f"   {item['url']}")
        lines.append("")

    return "\n".join(lines).strip()


def scrape_article(url, timeout=10):
    """
    기사 URL에서 본문 텍스트 추출.

    소스별 특화 파싱 + 범용 fallback.
    네비게이션, 광고, 쿠키 알림 등 노이즈 제거.

    Returns:
        str: 깨끗한 기사 본문 (최대 2000자) 또는 빈 문자열
    """
    try:
        req = Request(url, headers={"User-Agent": _UA})
        with urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # 노이즈 태그 제거
        for tag in ['script', 'style', 'nav', 'header', 'footer', 'aside',
                     'noscript', 'iframe', 'form', 'svg', 'button']:
            html = re.sub(rf'<{tag}[^>]*>.*?</{tag}>', '', html, flags=re.DOTALL | re.I)

        # HTML 주석 제거
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

        # 소스별 특화 파싱
        text = ""

        if "news.hada.io" in url:
            # GeekNews: topictextbox 클래스 안의 본문
            match = re.search(r'class="topictextbox"[^>]*>(.*?)</div>', html, re.DOTALL | re.I)
            if match:
                text = _clean_html_text(match.group(1))

        elif "techcrunch.com" in url:
            # TechCrunch: article 태그 안의 p 태그
            match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.I)
            if match:
                text = _extract_paragraphs(match.group(1))

        elif "technologyreview.com" in url:
            # MIT Tech Review: article body
            match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.I)
            if match:
                text = _extract_paragraphs(match.group(1))

        elif "news.ycombinator.com" in url:
            # HN 토론 페이지: 제목만 (본문은 외부 링크)
            match = re.search(r'class="titleline"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL | re.I)
            if match:
                text = _clean_html_text(match.group(1))

        # 범용 fallback: <article> → <main> → <p> 태그
        if not text or len(text) < 100:
            for container_tag in ['article', 'main', r'div[^>]*class="[^"]*(?:content|post|entry|story|body)[^"]*"']:
                match = re.search(rf'<{container_tag}[^>]*>(.*?)</{container_tag.split("[")[0]}>', html, re.DOTALL | re.I)
                if match:
                    extracted = _extract_paragraphs(match.group(1))
                    if len(extracted) > len(text):
                        text = extracted

        # 최후 fallback: 전체 <p> 태그
        if not text or len(text) < 100:
            text = _extract_paragraphs(html)

        return text[:2000]

    except Exception as e:
        print(f"[WARN] 기사 스크래핑 실패 ({url}): {e}")
        return ""


def _clean_html_text(html_fragment):
    """HTML 조각에서 태그 제거 후 깨끗한 텍스트 반환"""
    text = re.sub(r'<[^>]+>', ' ', html_fragment)
    text = re.sub(r'&[a-z]+;', ' ', text)  # HTML entities
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# 노이즈 텍스트 패턴 (네비게이션, 광고, 쿠키 등)
_NOISE_PATTERNS = re.compile(
    r'(?:cookie|subscribe|newsletter|sign up|log in|logged in|loading|'
    r'advertisement|sponsored|share this|follow us|read more|click here|'
    r'terms of|privacy policy|copyright|all rights reserved|'
    r'댓글|구독|로그인|회원가입|광고|공유하기|이전 기사|다음 기사)',
    re.I
)


def _extract_paragraphs(html_fragment):
    """HTML 조각에서 <p> 태그 본문만 추출. 노이즈 필터링 포함."""
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html_fragment, re.DOTALL | re.I)
    text_parts = []
    for p in paragraphs:
        clean = re.sub(r'<[^>]+>', '', p).strip()
        clean = re.sub(r'&[a-z]+;', ' ', clean)
        clean = re.sub(r'&#\d+;', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # 노이즈 필터링
        if len(clean) < 30:
            continue
        if _NOISE_PATTERNS.search(clean):
            continue
        text_parts.append(clean)
    return "\n\n".join(text_parts)


def generate_thread_drafts(thread_picks):
    """
    스레드 맞춤 기사를 기반으로 context.md 공식에 따라 완성형 글 초안 생성.

    3단 구조:
    1. 훅 — 첫 줄에서 스크롤을 멈추게
    2. 본문 — 공감 + 구체적 사실 + 반전
    3. 참여 유도 — 댓글을 쓰게 만드는 마무리

    Returns:
        list[dict]: [{"title": ..., "draft": ..., "url": ..., "pattern": ...}, ...]
    """
    drafts = []

    # 해시태그 매핑
    tag_map = {
        "ai": "#AI", "openai": "#OpenAI", "gpt": "#GPT", "chatgpt": "#ChatGPT",
        "claude": "#Claude", "anthropic": "#Anthropic", "gemini": "#Gemini",
        "llm": "#LLM", "apple": "#Apple", "google": "#Google",
        "microsoft": "#Microsoft", "meta": "#Meta", "nvidia": "#NVIDIA",
        "copilot": "#Copilot", "mistral": "#Mistral", "llama": "#Llama",
    }

    for i, pick in enumerate(thread_picks):
        item = pick["item"]
        pattern = pick.get("pattern", "추가 선별")
        title = item["title"]
        url = item["url"]

        # 기사 본문 스크래핑
        print(f"[INFO] 기사 스크래핑 중: {title[:50]}...")
        article_text = scrape_article(url)

        # 해시태그 추출 (1개만)
        title_lower = title.lower()
        tag = "#AI"  # 기본
        for keyword, t in tag_map.items():
            if keyword in title_lower:
                tag = t
                break

        # 기사에서 핵심 요소 추출
        facts = _extract_key_facts(article_text, title)

        # context.md 3단 구조 기반 초안 생성
        draft = _build_draft_from_pattern(pattern, title, facts, tag)

        drafts.append({
            "title": title,
            "draft": draft,
            "url": url,
            "source": item.get("source", ""),
            "pattern": pattern,
            "reason": pick.get("reason", ""),
            "article_summary": facts.get("summary", "")[:300],
        })

    return drafts


def _extract_key_facts(article_text, title):
    """
    기사 본문에서 초안 작성에 필요한 핵심 요소 추출.

    Returns:
        dict: {summary, numbers, key_sentences, entities, has_controversy}
    """
    facts = {
        "summary": "",
        "numbers": [],
        "key_sentences": [],
        "entities": [],
        "has_controversy": False,
    }

    if not article_text:
        return facts

    # 숫자/데이터 추출
    number_pattern = re.compile(
        r'(?:\$[\d,.]+\s?(?:billion|million|trillion|B|M|T)?|'
        r'[\d,.]+\s?(?:billion|million|trillion|percent|%|달러|억|만|천|조|명|건|개|배))',
        re.I
    )
    facts["numbers"] = list(set(number_pattern.findall(title + " " + article_text)))[:5]

    # 문장 분리 후 핵심 문장 선별
    sentences = re.split(r'(?<=[.!?])\s+', article_text)
    scored_sentences = []
    for s in sentences:
        s = s.strip()
        if len(s) < 20 or len(s) > 300:
            continue
        score = 0
        # 숫자가 있으면 가산
        if number_pattern.search(s):
            score += 3
        # 인명/회사명 있으면 가산
        if re.search(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)+', s):
            score += 1
        # 짧은 문장 선호
        if len(s) < 100:
            score += 1
        scored_sentences.append((score, s))

    scored_sentences.sort(key=lambda x: x[0], reverse=True)
    facts["key_sentences"] = [s for _, s in scored_sentences[:5]]

    # 요약 (상위 3문장)
    if facts["key_sentences"]:
        facts["summary"] = " ".join(facts["key_sentences"][:3])

    # 논쟁성 체크
    controversy_words = re.compile(r'(controversy|debate|ban|block|concern|risk|danger|threat|privacy|layoff|replace|fired|criticism|backlash|oppose)', re.I)
    facts["has_controversy"] = bool(controversy_words.search(article_text))

    return facts


def _build_draft_from_pattern(pattern, title, facts, tag):
    """
    패턴 + 기사 팩트를 기반으로 3단 구조 초안 생성.

    context.md의 공식:
    - 훅: 숫자/충격 사실/결론 숨기기로 시작
    - 본문: 짧은 문단, 2-3줄씩, 전환어 사용
    - 개인 의견: 한 줄
    - 마무리: 열린 질문 or 양자택일
    """
    numbers = facts.get("numbers", [])
    key_sentences = facts.get("key_sentences", [])
    has_summary = bool(key_sentences)

    # 본문에 사용할 팩트 문장들 (가독성을 위해 짧게 정리)
    fact_lines = []
    for s in key_sentences[:3]:
        # 영어 문장은 그대로 사용 (번역은 PM이 컨펌 시 수정)
        if len(s) > 150:
            s = s[:147] + "..."
        fact_lines.append(s)

    if pattern == "전문지식 공유형":
        hook = f"이거 좀 흥미로운 얘긴데"
        if numbers:
            body_intro = f"\n{title}\n"
        else:
            body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(기사 핵심 내용 2-3줄)"
        opinion = "이쪽으로 좀 파봤는데 생각보다 깊음"
        cta = "궁금한 거 있으면 물어봐 💬"

    elif pattern == "토론/논쟁 유도형":
        hook = f"솔직히 이거 논란이 될 만한데"
        body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(양쪽 시각 정리 2-3줄)"
        opinion = "솔직히 이건 의견 좀 갈릴 듯"
        cta = "이건 규제가 답이야 기술로 막을 수 있는 문제야?"

    elif pattern == "충격 숫자형":
        if numbers:
            hook = f"숫자만 보면 진짜 미쳤다"
        else:
            hook = f"이건 좀 충격인데"
        body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(구체적 숫자/데이터 강조 2-3줄)"
        opinion = "근데 진짜 포인트는 따로 있음"
        cta = "이게 진짜 현실이 될 것 같아?"

    elif pattern == "트렌드 속보형":
        hook = f"방금 터진 뉴스인데"
        body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(빠른 요약 + 왜 중요한지 2-3줄)"
        opinion = "이거 파급력 클 것 같은데"
        cta = "앞으로 어떻게 될지 지켜봐야겠다"

    elif pattern == "공감형":
        hook = f"솔직히 좀 불안한 얘긴데"
        body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(공감 포인트 + 불안 요소 2-3줄)"
        opinion = "나도 요즘 이거 때문에 좀 생각이 많아"
        cta = "다들 비슷한 경험 있을 것 같은데"

    else:
        hook = f"이거 한번 봐봐"
        body_intro = f"\n{title}\n"
        body_facts = "\n\n".join(fact_lines) if fact_lines else "(기사 핵심 내용 2-3줄)"
        opinion = "개인적으로 좀 흥미로움"
        cta = "어떻게 생각해?"

    # 3단 구조로 조립
    draft = f"""{hook}

{body_intro}
{body_facts}

{opinion}

{cta}

{tag}"""

    # 연속 빈 줄 정리
    draft = re.sub(r'\n{3,}', '\n\n', draft).strip()
    return draft


def format_thread_drafts(drafts):
    """스레드 글 초안을 텔레그램 포맷으로 변환"""
    if not drafts:
        return "스레드 글 초안을 생성하지 못했어요."

    lines = ["**스레드 글 초안 5개**", "(컨펌하면 게시할게요!)", ""]
    for i, d in enumerate(drafts, 1):
        lines.append(f"--- 초안 {i} ---")
        lines.append(d["draft"])
        lines.append("")

    return "\n".join(lines).strip()


def save_thread_drafts(drafts):
    """
    스레드 글 초안을 tasks/briefing_{날짜}/threads_drafts.md에 저장.

    Returns:
        str: 저장된 파일 경로 (또는 빈 문자열)
    """
    if not drafts:
        return ""

    today = datetime.now().strftime("%Y%m%d")
    dir_path = os.path.join(PROJECT_ROOT, "tasks", f"briefing_{today}")
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, "threads_drafts.md")

    lines = [
        f"# 스레드 글 초안 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "아래 초안 중 게시할 글을 선택해주세요.",
        "컨펌하면 threads_poster.py로 자동 게시합니다.",
        "",
    ]

    for i, d in enumerate(drafts, 1):
        lines.append(f"## 초안 {i} [{d['source']}]")
        lines.append("")
        lines.append(f"- 패턴: {d.get('pattern', '')}")
        lines.append(f"- URL: {d.get('url', '')}")
        lines.append(f"상태: 대기")
        lines.append("")
        lines.append("### 글 초안")
        lines.append("```")
        lines.append(d["draft"])
        lines.append("```")
        lines.append("")
        # 기사 요약 (PM이 글 완성 시 참고)
        summary = d.get("article_summary", "")
        if summary:
            lines.append("### 기사 요약 (참고용)")
            lines.append(f"> {summary}")
            lines.append("")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[OK] 스레드 초안 저장: {file_path}")
        return file_path
    except Exception as e:
        print(f"[WARN] 스레드 초안 저장 실패: {e}")
        return ""


def generate_briefing():
    """일일 브리핑 생성"""
    now = datetime.now()
    briefing_parts = []

    briefing_parts.append(f"**heysquid 일일 브리핑**")
    briefing_parts.append(f"{now.strftime('%Y-%m-%d %A')}")
    briefing_parts.append("")

    # 미처리 메시지
    pending = get_pending_tasks()
    if pending > 0:
        briefing_parts.append(f"**미처리 메시지: {pending}개**")
    else:
        briefing_parts.append("미처리 메시지: 없음")
    briefing_parts.append("")

    # 워크스페이스별 상태
    workspaces_file = os.path.join(PROJECT_ROOT, "data", "workspaces.json")

    if os.path.exists(workspaces_file):
        try:
            with open(workspaces_file, "r", encoding="utf-8") as f:
                workspaces = json.load(f)
        except Exception:
            workspaces = {}
    else:
        workspaces = {}

    if workspaces:
        briefing_parts.append("**프로젝트 현황:**")
        briefing_parts.append("")

        for name, info in workspaces.items():
            ws_path = info.get("path", "")
            description = info.get("description", "")
            last_active = info.get("last_active", "N/A")

            briefing_parts.append(f"--- {name} ---")
            briefing_parts.append(f"  {description}")
            briefing_parts.append(f"  최근 활동: {last_active}")

            # Git 요약
            if os.path.exists(ws_path):
                git_summary = get_git_summary(ws_path)
                briefing_parts.append(f"  {git_summary}")

            # 진행 기록
            progress = get_recent_progress(name)
            if progress != "진행 기록 없음":
                briefing_parts.append(f"  최근 진행:")
                briefing_parts.append(f"  {progress}")

            briefing_parts.append("")

    else:
        briefing_parts.append("등록된 프로젝트 없음")
        briefing_parts.append("")

    # 멀티소스 뉴스 수집 + 분석
    try:
        all_news = fetch_all_news_sources()

        # 방법1: 가중치 통합 랭킹 TOP 10
        top10 = score_and_rank_news(all_news, top_n=10)
        if top10:
            briefing_parts.append(format_top_news(top10, "방법1: 가중치 통합 랭킹 TOP 10"))
            briefing_parts.append("")

        # 방법2: 기준별 1픽 (5개 세트)
        criterion_picks = pick_best_per_criterion(all_news)
        if criterion_picks:
            briefing_parts.append(format_criterion_picks(criterion_picks))
            briefing_parts.append("")

        # 스레드 맞춤 기사 선별 (인기글 패턴 기반)
        thread_picks = select_thread_worthy(all_news, top_n=5)
        if thread_picks:
            briefing_parts.append(format_thread_picks(thread_picks))
            briefing_parts.append("")

            # 스레드 글 초안 (자연스러운 톤)
            drafts = generate_thread_drafts(thread_picks)
            if drafts:
                briefing_parts.append(format_thread_drafts(drafts))
                briefing_parts.append("")
                save_thread_drafts(drafts)

    except Exception as e:
        print(f"[WARN] 종합 뉴스/스레드 생성 오류: {e}")
        import traceback
        traceback.print_exc()
        briefing_parts.append("(종합 뉴스 수집 중 오류 발생)")
        briefing_parts.append("")

    # GeekNews TOP 10 (별도 섹션)
    news_items = fetch_geeknews_top(10)
    if news_items:
        briefing_parts.append(format_geeknews(news_items))
        briefing_parts.append("")

    briefing_parts.append("---")
    briefing_parts.append("_heysquid 자동 브리핑_")

    return "\n".join(briefing_parts)


def send_briefing():
    """브리핑 생성 후 텔레그램으로 전송"""
    if not CHAT_ID:
        print("[ERROR] TELEGRAM_ALLOWED_USERS가 설정되지 않았습니다.")
        return False

    briefing = generate_briefing()
    print(briefing)
    print()

    try:
        from .telegram_sender import send_message_sync
        success = send_message_sync(int(CHAT_ID), briefing)

        if success:
            print("[OK] 브리핑 전송 완료!")
        else:
            print("[ERROR] 브리핑 전송 실패!")

        return success

    except Exception as e:
        print(f"[ERROR] 브리핑 전송 오류: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("heysquid 일일 브리핑")
    print("=" * 60)
    print()

    send_briefing()
