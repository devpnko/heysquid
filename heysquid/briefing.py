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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)

# sys.path에 heysquid/ 추가
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# .env 로드
load_dotenv(os.path.join(BASE_DIR, ".env"))

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


def format_top5_news(top5):
    """종합 TOP 5 뉴스를 텔레그램 포맷으로 변환"""
    if not top5:
        return "종합 뉴스 TOP 5를 생성하지 못했어요."

    lines = ["**종합 AI/IT 뉴스 TOP 5**", ""]
    for i, item in enumerate(top5, 1):
        src = item.get("source", "")
        pts = item.get("points", 0)
        score = item.get("_score", 0)
        badge = ""
        if AI_KEYWORDS.search(item["title"]):
            badge = " [AI]"
        lines.append(f"{i}. {item['title']}{badge}")
        lines.append(f"   [{src}] {pts}pts | score:{score}")
        lines.append(f"   {item['url']}")
        lines.append("")

    return "\n".join(lines).strip()


def generate_thread_drafts(top5):
    """
    TOP 5 뉴스 각각에 대해 스레드용 짧은 글 초안 생성 (템플릿 기반).

    Returns:
        list[dict]: [{"title": ..., "draft": ..., "url": ...}, ...]
    """
    drafts = []

    # 해시태그 매핑
    tag_map = {
        "ai": "#AI", "openai": "#OpenAI", "gpt": "#GPT", "chatgpt": "#ChatGPT",
        "claude": "#Claude", "anthropic": "#Anthropic", "gemini": "#Gemini",
        "llm": "#LLM", "diffusion": "#StableDiffusion", "midjourney": "#Midjourney",
        "apple": "#Apple", "google": "#Google", "microsoft": "#Microsoft",
        "meta": "#Meta", "tesla": "#Tesla", "nvidia": "#NVIDIA",
        "copilot": "#Copilot", "langchain": "#LangChain",
        "mistral": "#Mistral", "llama": "#Llama", "groq": "#Groq",
        "sora": "#Sora", "transformer": "#Transformer",
    }

    templates = [
        "{title}\n\n{opinion}\n\n{tags}",
    ]

    opinions = [
        "이거 주목할 만한 소식이에요. 앞으로 어떤 변화가 올지 기대됩니다.",
        "기술 트렌드가 빠르게 움직이고 있네요. 여러분 생각은 어떤가요?",
        "개발자라면 한번쯤 살펴볼 만한 뉴스. 실무에 어떤 영향이 있을까요?",
        "흥미로운 발전이에요. 이 방향이 계속될지 지켜봐야겠습니다.",
        "이 소식, 놓치면 아쉬울 거예요. 핵심만 정리해봤어요.",
    ]

    for i, item in enumerate(top5):
        title = item["title"]
        url = item["url"]

        # 제목에서 매칭되는 해시태그 추출
        title_lower = title.lower()
        tags = set()
        for keyword, tag in tag_map.items():
            if keyword in title_lower:
                tags.add(tag)
        # 기본 태그
        if AI_KEYWORDS.search(title):
            tags.add("#AI")
        tags.add("#Tech")
        tags_str = " ".join(sorted(tags))

        opinion = opinions[i % len(opinions)]

        draft = f"{title}\n\n{opinion}\n\n{url}\n\n{tags_str}"

        drafts.append({
            "title": title,
            "draft": draft,
            "url": url,
            "source": item.get("source", ""),
        })

    return drafts


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
        lines.append(f"상태: 대기")
        lines.append("")
        lines.append("```")
        lines.append(d["draft"])
        lines.append("```")
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

    # GeekNews 뉴스 (기존 TOP 10 유지)
    news_items = fetch_geeknews_top(10)
    if news_items:
        briefing_parts.append(format_geeknews(news_items))
        briefing_parts.append("")

    # 종합 AI/IT 뉴스 TOP 5
    try:
        all_news = fetch_all_news_sources()
        top5 = score_and_rank_news(all_news, top_n=5)
        if top5:
            briefing_parts.append(format_top5_news(top5))
            briefing_parts.append("")

            # 스레드 글 초안
            drafts = generate_thread_drafts(top5)
            if drafts:
                briefing_parts.append(format_thread_drafts(drafts))
                briefing_parts.append("")
                save_thread_drafts(drafts)
    except Exception as e:
        print(f"[WARN] 종합 뉴스/스레드 생성 오류: {e}")
        briefing_parts.append("(종합 뉴스 수집 중 오류 발생)")
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
        from telegram_sender import send_message_sync
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
