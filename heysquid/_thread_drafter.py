"""
스레드 글 초안 생성 — heysquid

기사 팩트 추출 + context.md 공식 기반 3단 구조 초안 생성 + 파일 저장.
"""

import os
import re
from datetime import datetime

from ._news_fetcher import scrape_article
from .config import TASKS_DIR_STR as TASKS_DIR


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
        if number_pattern.search(s):
            score += 3
        if re.search(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)+', s):
            score += 1
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

    # 본문에 사용할 팩트 문장들
    fact_lines = []
    for s in key_sentences[:3]:
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
    dir_path = os.path.join(TASKS_DIR, f"briefing_{today}")
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
