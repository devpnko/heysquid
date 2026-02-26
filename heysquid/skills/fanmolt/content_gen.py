"""콘텐츠 생성 — LLM으로 글/댓글 생성."""

import json
import logging

logger = logging.getLogger(__name__)


def _call_llm(system: str, user: str) -> str:
    """LLM 호출. Claude API → 로컬 LLM 순으로 시도."""
    # 1) Anthropic API
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except Exception as e:
        logger.debug("Anthropic API 실패: %s", e)

    # 2) 로컬 LLM (LM Studio / Ollama — OpenAI 호환)
    try:
        import openai
        client = openai.OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")
        resp = client.chat.completions.create(
            model="local",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=2000,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.debug("로컬 LLM 실패: %s", e)

    raise RuntimeError("LLM 사용 불가 — Anthropic API 키 또는 로컬 LLM 필요")


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


def generate_reply(persona: str, notification: dict) -> str:
    """댓글에 대한 답변 생성."""
    comment_text = notification.get("content", "")
    post_title = notification.get("post_title", "")

    user_msg = (
        f"내 글 '{post_title}'에 이런 댓글이 달렸어:\n"
        f"\"{comment_text}\"\n\n"
        "이 댓글에 답해줘. 구체적이고 가치 있게, 3줄 이내로."
    )
    return _call_llm(persona, user_msg)


def generate_comment(persona: str, post: dict) -> str | None:
    """다른 크리에이터 글에 댓글 생성. 할 말 없으면 None."""
    title = post.get("title", "")
    content = post.get("content_preview", post.get("content", ""))[:300]

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
