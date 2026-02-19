"""
뉴스 수집 + 기사 스크래핑 — heysquid

4소스(GeekNews, HN, TechCrunch, MIT Tech Review) 뉴스 수집,
RSS 파싱, 기사 본문 스크래핑.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError


# ============================================================
# 공유 상수
# ============================================================

AI_KEYWORDS = re.compile(
    r'\b(ai|a\.i\.|artificial intelligence|llm|gpt|chatgpt|openai|claude|anthropic|'
    r'gemini|copilot|diffusion|stable diffusion|midjourney|machine learning|deep learning|'
    r'neural|transformer|hugging\s?face|langchain|rag|agent|fine.?tun|sora|groq|mistral|'
    r'llama|generative|gen\s?ai)\b',
    re.IGNORECASE
)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ============================================================
# 뉴스 수집
# ============================================================

def fetch_geeknews_top(count=10):
    """GeekNews(news.hada.io) 메인 페이지에서 포인트 기준 인기 뉴스 추출"""
    try:
        req = Request(
            "https://news.hada.io/",
            headers={"User-Agent": _UA}
        )
        with urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")

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

        news_items.sort(key=lambda x: x["points"], reverse=True)
        return news_items[:count]

    except (URLError, Exception) as e:
        print(f"[WARN] GeekNews 크롤링 오류: {e}")
        return []


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

    geeknews = fetch_geeknews_top(20)
    for item in geeknews:
        item.setdefault("source", "GeekNews")
        item.setdefault("comments", 0)
        item.setdefault("timestamp", int(time.time()))
        all_items.append(item)

    all_items.extend(fetch_hackernews_top(30))
    all_items.extend(fetch_techcrunch_rss(20))
    all_items.extend(fetch_mit_tech_review_rss(20))

    print(f"[INFO] 뉴스 수집 완료: 총 {len(all_items)}건 "
          f"(GN:{len(geeknews)}, HN:{len([i for i in all_items if i['source']=='HackerNews'])}, "
          f"TC:{len([i for i in all_items if i['source']=='TechCrunch'])}, "
          f"MIT:{len([i for i in all_items if i['source']=='MIT Tech Review'])})")

    return all_items


# ============================================================
# 기사 스크래핑
# ============================================================

# 노이즈 텍스트 패턴 (네비게이션, 광고, 쿠키 등)
_NOISE_PATTERNS = re.compile(
    r'(?:cookie|subscribe|newsletter|sign up|log in|logged in|loading|'
    r'advertisement|sponsored|share this|follow us|read more|click here|'
    r'terms of|privacy policy|copyright|all rights reserved|'
    r'댓글|구독|로그인|회원가입|광고|공유하기|이전 기사|다음 기사)',
    re.I
)


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
            match = re.search(r'class="topictextbox"[^>]*>(.*?)</div>', html, re.DOTALL | re.I)
            if match:
                text = _clean_html_text(match.group(1))

        elif "techcrunch.com" in url:
            match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.I)
            if match:
                text = _extract_paragraphs(match.group(1))

        elif "technologyreview.com" in url:
            match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.I)
            if match:
                text = _extract_paragraphs(match.group(1))

        elif "news.ycombinator.com" in url:
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


def _extract_paragraphs(html_fragment):
    """HTML 조각에서 <p> 태그 본문만 추출. 노이즈 필터링 포함."""
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html_fragment, re.DOTALL | re.I)
    text_parts = []
    for p in paragraphs:
        clean = re.sub(r'<[^>]+>', '', p).strip()
        clean = re.sub(r'&[a-z]+;', ' ', clean)
        clean = re.sub(r'&#\d+;', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if len(clean) < 30:
            continue
        if _NOISE_PATTERNS.search(clean):
            continue
        text_parts.append(clean)
    return "\n\n".join(text_parts)


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
