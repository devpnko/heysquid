"""콘텐츠 생성 — Claude Code CLI로 글/댓글 생성."""

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

_claude_path: str | None = None


def _get_claude() -> str:
    """claude CLI 경로 반환."""
    global _claude_path
    if _claude_path is None:
        _claude_path = shutil.which("claude")
    if not _claude_path:
        raise RuntimeError("Claude Code CLI가 설치되지 않았습니다")
    return _claude_path


def _call_llm(system: str, user: str) -> str:
    """LLM 호출 — Claude Code CLI (`claude -p`) 사용."""
    claude = _get_claude()
    prompt = f"{system}\n\n---\n\n{user}"

    # CLAUDECODE 환경변수 제거 — 중첩 세션 방지 체크 우회
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        [claude, "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI 실패: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Claude CLI 응답 없음")
    return output


def generate_post_from_recipe(persona_prompt: str, recipe: dict,
                              rules: list = None, prev_titles: list = None) -> dict:
    """Blueprint 레시피 기반 글 생성.

    recipe: {name, trigger, gather, process, output}
    """
    # system = persona + rules
    system_parts = [persona_prompt]
    if rules:
        system_parts.append("\n\n## 반드시 지켜야 할 규칙\n" + "\n".join(f"- {r}" for r in rules))
    system = "\n".join(system_parts)

    # gather 단계
    gather_instructions = []
    for g in recipe.get("gather", []):
        gather_instructions.append(f"[{g.get('type', 'info')}] {g.get('instruction', '')}")

    # output 설정
    output = recipe.get("output", {})
    title_tpl = output.get("title_template", "{topic}")
    fmt = output.get("format", "마크다운, 500~1500자")
    tags = output.get("tags", [])

    prev = ""
    if prev_titles:
        prev = "\n\n이전에 쓴 글 (중복 금지):\n" + "\n".join(f"- {t}" for t in prev_titles[-10:])

    user_msg = (
        f"## 레시피: {recipe.get('name', 'post')}\n\n"
        f"### 1단계 — 수집 (gather)\n"
        + "\n".join(f"- {g}" for g in gather_instructions)
        + f"\n\n### 2단계 — 가공 (process)\n{recipe.get('process', '핵심을 간결하게 정리')}"
        + f"\n\n### 3단계 — 출력 (output)\n"
        f"- 제목 템플릿: {title_tpl}\n"
        f"- 형식: {fmt}\n"
        f"- 태그: {', '.join(tags) if tags else '없음'}"
        f"{prev}\n\n"
        "반드시 아래 JSON 형식으로만 답해:\n"
        '{"title": "제목", "content": "본문 (마크다운)", "tags": ["태그1"]}'
    )

    raw = _call_llm(system, user_msg)

    try:
        if "```" in raw:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            raw = raw[start:end]
        data = json.loads(raw)
        return {
            "title": data.get("title", "Untitled"),
            "content": data.get("content", ""),
            "is_free": output.get("is_free", True),
        }
    except (json.JSONDecodeError, ValueError):
        return {"title": "New Post", "content": raw, "is_free": output.get("is_free", True)}


def generate_post(persona: str, category: str, prev_titles: list = None) -> dict:
    """글 생성. {"title": ..., "content": ..., "is_free": True/False} 반환."""
    prev = ""
    if prev_titles:
        prev = "\n\n이전에 쓴 글 (중복 금지):\n" + "\n".join(f"- {t}" for t in prev_titles[-10:])

    user_msg = (
        f"카테고리: {category}\n"
        f"{prev}\n\n"
        "새 글을 작성해. 반드시 아래 JSON 형식으로만 답해:\n"
        '{"title": "제목", "content": "본문 (마크다운, 500~1500자)", "is_free": true}'
    )

    raw = _call_llm(persona, user_msg)

    # JSON 파싱
    try:
        # ```json ... ``` 블록 추출
        if "```" in raw:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            raw = raw[start:end]
        data = json.loads(raw)
        return {
            "title": data.get("title", "Untitled"),
            "content": data.get("content", ""),
            "is_free": data.get("is_free", True),
        }
    except (json.JSONDecodeError, ValueError):
        # 파싱 실패 → 전체를 본문으로
        return {"title": "New Post", "content": raw, "is_free": True}


def generate_reply(persona: str, notification: dict, reply_style: str = None) -> str:
    """댓글에 대한 답변 생성."""
    comment_text = notification.get("content", "")
    post_title = notification.get("post_title", "")

    style_hint = ""
    if reply_style:
        style_hint = f"\n답변 스타일: {reply_style}"

    user_msg = (
        f"내 글 '{post_title}'에 이런 댓글이 달렸어:\n"
        f"\"{comment_text}\"\n\n"
        f"이 댓글에 답해줘. 구체적이고 가치 있게, 3줄 이내로.{style_hint}"
    )
    return _call_llm(persona, user_msg)


def generate_comment(persona: str, post: dict, engage_topics: list = None) -> str | None:
    """다른 크리에이터 글에 댓글 생성. 할 말 없으면 None."""
    title = post.get("title", "")
    content = post.get("content_preview", post.get("content", ""))[:300]

    # engage_topics 필터: 관련 없는 포스트 스킵
    if engage_topics:
        combined = f"{title} {content}".lower()
        if not any(t.lower() in combined for t in engage_topics):
            return None

    user_msg = (
        f"다른 크리에이터의 글:\n"
        f"제목: {title}\n"
        f"내용: {content}\n\n"
        "이 글에 댓글을 달아줘. 구체적인 인사이트를 추가해. 3줄 이내.\n"
        "할 말이 없으면 'SKIP'이라고만 답해."
    )

    reply = _call_llm(persona, user_msg)
    if "SKIP" in reply.upper():
        return None
    return reply
