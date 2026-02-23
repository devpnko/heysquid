"""
마케팅 콘텐츠 생성기 — 패턴 기반 콘텐츠 포맷팅

_templates.py의 완성된 콘텐츠를 플랫폼별로 포맷팅하고,
drafts 파일로 저장하는 역할.
"""

import os
import random
from datetime import datetime

from ...core.config import DATA_DIR

from ._patterns import HASHTAG_SETS, HASHTAG_RULES, POSTING_RULES
from ._templates import CONTENTS, HYPERS_CONTEXT, get_contents_by_category


def select_daily_contents(n: int = 3, category: str | None = None) -> list[dict]:
    """일일 게시용 콘텐츠 n개 선택.

    카테고리 비율 (기본):
    - ai_tip: 60%
    - participant: 25%
    - host_recruit / fomo: 15%
    """
    if category:
        pool = get_contents_by_category(category)
        return random.sample(pool, min(n, len(pool)))

    # 비율 기반 선택
    tips = get_contents_by_category("ai_tip")
    parts = get_contents_by_category("participant")
    others = get_contents_by_category("host_recruit") + get_contents_by_category("fomo")

    selected = []
    tip_count = max(1, round(n * 0.6))
    part_count = max(1, round(n * 0.25))
    other_count = max(0, n - tip_count - part_count)

    selected.extend(random.sample(tips, min(tip_count, len(tips))))
    selected.extend(random.sample(parts, min(part_count, len(parts))))
    if other_count > 0 and others:
        selected.extend(random.sample(others, min(other_count, len(others))))

    random.shuffle(selected)
    return selected[:n]


def format_for_threads(content: dict) -> str:
    """스레드용 포맷팅: 1태그, 150-500자 최적화"""
    text = content["content"]
    rules = POSTING_RULES["threads"]

    # 해시태그 1개 선택 (niche 우선)
    tags = content.get("hashtags", [])
    niche_tags = [t for t in tags if t in HASHTAG_SETS["niche"]]
    tag = niche_tags[0] if niche_tags else (tags[0] if tags else "#HYPERS")

    # 스레드 태그는 # 없이 사용 가능하지만 관례상 유지
    formatted = f"{text}\n\n{tag}"

    # 글자수 체크
    if len(formatted) > rules["max_chars"]:
        # 본문 축소 (마지막 줄 제거 등은 수동 편집 영역)
        pass

    return formatted


def format_for_x(content: dict) -> str:
    """X(Twitter)용 포맷팅: 280자 제한, 해시태그 2-3개"""
    text = content["content"]
    rules = POSTING_RULES["x"]

    # 해시태그 최대 3개
    tags = content.get("hashtags", [])[:rules.get("hashtag_max", 3)]
    tag_str = " ".join(tags)

    # 280자 제한 처리
    max_text_len = rules["max_chars"] - len(tag_str) - 2  # 줄바꿈 여유

    if len(text) > max_text_len:
        # 훅(첫 줄) + CTA(마지막 줄) 유지, 중간 축약
        lines = text.strip().split("\n")
        hook = lines[0]
        cta = lines[-1] if len(lines) > 1 else ""

        # 훅 + ... + CTA + 태그
        remaining = max_text_len - len(hook) - len(cta) - 5
        if remaining > 20:
            middle = text[len(hook):len(text) - len(cta)].strip()
            middle_truncated = middle[:remaining] + "..."
            text = f"{hook}\n{middle_truncated}\n{cta}"
        else:
            text = f"{hook}\n\n{cta}"

    formatted = f"{text}\n\n{tag_str}"
    return formatted


def format_content(content: dict, platform: str = "threads") -> str:
    """플랫폼별 콘텐츠 포맷팅"""
    if platform == "threads":
        return format_for_threads(content)
    elif platform == "x":
        return format_for_x(content)
    return content["content"]


def generate_drafts(n: int = 3, category: str | None = None,
                    platform: str = "both") -> list[dict]:
    """n개 콘텐츠를 선택하고 플랫폼별 포맷된 초안 생성.

    Returns:
        list[dict]: [{
            "id": str,
            "category": str,
            "threads_draft": str,
            "x_draft": str,
            "original": dict,
        }]
    """
    selected = select_daily_contents(n, category)
    drafts = []

    for content in selected:
        draft = {
            "id": content["id"],
            "category": content["category"],
            "threads_draft": format_for_threads(content),
            "x_draft": format_for_x(content),
            "original": content,
        }
        drafts.append(draft)

    return drafts


def format_drafts_for_telegram(drafts: list[dict]) -> str:
    """텔레그램 미리보기용 포맷"""
    if not drafts:
        return "생성된 콘텐츠가 없습니다."

    lines = [
        f"**HYPERS 마케팅 콘텐츠 {len(drafts)}개**",
        "(컨펌하면 스레드/X에 게시합니다)",
        "",
    ]

    for i, d in enumerate(drafts, 1):
        cat_label = {
            "ai_tip": "AI 팁",
            "host_recruit": "호스트 모집",
            "participant": "참여자 유입",
            "fomo": "FOMO",
        }.get(d["category"], d["category"])

        lines.append(f"--- 초안 {i} [{cat_label}] ---")
        lines.append(d["threads_draft"])
        lines.append("")

    return "\n".join(lines).strip()


def save_drafts(drafts: list[dict], output_dir: str | None = None) -> str:
    """초안을 마크다운 파일로 저장.

    Returns:
        str: 저장된 파일 경로
    """
    if not drafts:
        return ""

    if output_dir is None:
        output_dir = str(DATA_DIR / "marketing_drafts")

    os.makedirs(output_dir, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    file_path = os.path.join(output_dir, f"drafts_{today}.md")

    lines = [
        f"# HYPERS 마케팅 콘텐츠 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "아래 초안을 확인 후 컨펌해주세요.",
        f"컨펌 시 스레드/X에 동시 게시됩니다.",
        "",
    ]

    for i, d in enumerate(drafts, 1):
        lines.append(f"## 초안 {i} [{d['category']}] (ID: {d['id']})")
        lines.append("")
        lines.append("### Threads 버전")
        lines.append("```")
        lines.append(d["threads_draft"])
        lines.append("```")
        lines.append("")
        lines.append("### X 버전")
        lines.append("```")
        lines.append(d["x_draft"])
        lines.append("```")
        lines.append("")
        lines.append(f"상태: 대기")
        lines.append("")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[OK] 마케팅 초안 저장: {file_path}")
        return file_path
    except Exception as e:
        print(f"[WARN] 마케팅 초안 저장 실패: {e}")
        return ""
