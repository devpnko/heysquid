"""Content generation — create posts/comments via Claude Code CLI."""

import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

_claude_path: str | None = None


def _get_claude() -> str:
    """Return path to claude CLI."""
    global _claude_path
    if _claude_path is None:
        _claude_path = shutil.which("claude")
    if not _claude_path:
        raise RuntimeError("Claude Code CLI is not installed")
    return _claude_path


def _call_llm(system: str, user: str) -> str:
    """Call LLM via Claude Code CLI (`claude -p`)."""
    claude = _get_claude()
    prompt = f"{system}\n\n---\n\n{user}"

    # Remove CLAUDECODE env var to bypass nested session check
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    result = subprocess.run(
        [claude, "-p", prompt, "--output-format", "text"],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Claude CLI returned empty response")
    return output


def generate_post_from_recipe(persona_prompt: str, recipe: dict,
                              rules: list = None, prev_titles: list = None) -> dict:
    """Generate post based on a blueprint recipe.

    recipe: {name, trigger, gather, process, output}
    """
    # system = persona + rules
    system_parts = [persona_prompt]
    if rules:
        system_parts.append("\n\n## Rules to follow\n" + "\n".join(f"- {r}" for r in rules))
    system = "\n".join(system_parts)

    # gather step
    gather_instructions = []
    for g in recipe.get("gather", []):
        gather_instructions.append(f"[{g.get('type', 'info')}] {g.get('instruction', '')}")

    # output settings
    output = recipe.get("output", {})
    title_tpl = output.get("title_template", "{topic}")
    fmt = output.get("format", "markdown, 500-1500 chars")
    tags = output.get("tags", [])

    prev = ""
    if prev_titles:
        prev = "\n\nPrevious posts (no duplicates):\n" + "\n".join(f"- {t}" for t in prev_titles[-10:])

    user_msg = (
        f"## Recipe: {recipe.get('name', 'post')}\n\n"
        f"### Step 1 — Gather\n"
        + "\n".join(f"- {g}" for g in gather_instructions)
        + f"\n\n### Step 2 — Process\n{recipe.get('process', 'Summarize the key points concisely')}"
        + f"\n\n### Step 3 — Output\n"
        f"- Title template: {title_tpl}\n"
        f"- Format: {fmt}\n"
        f"- Tags: {', '.join(tags) if tags else 'none'}"
        f"{prev}\n\n"
        "You must respond ONLY in the following JSON format:\n"
        '{"title": "title", "content": "body (markdown)", "tags": ["tag1"]}'
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
    """Generate post. Returns {"title": ..., "content": ..., "is_free": True/False}."""
    prev = ""
    if prev_titles:
        prev = "\n\nPrevious posts (no duplicates):\n" + "\n".join(f"- {t}" for t in prev_titles[-10:])

    user_msg = (
        f"Category: {category}\n"
        f"{prev}\n\n"
        "Write a new post. You must respond ONLY in the following JSON format:\n"
        '{"title": "title", "content": "body (markdown, 500-1500 chars)", "is_free": true}'
    )

    raw = _call_llm(persona, user_msg)

    # JSON parsing
    try:
        # Extract ```json ... ``` block
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
        # Parse failed -> use entire output as body
        return {"title": "New Post", "content": raw, "is_free": True}


def generate_reply(persona: str, notification: dict, reply_style: str = None) -> str:
    """Generate a reply to a comment."""
    comment_text = notification.get("content", "")
    post_title = notification.get("post_title", "")

    style_hint = ""
    if reply_style:
        style_hint = f"\nReply style: {reply_style}"

    user_msg = (
        f"Someone left this comment on my post '{post_title}':\n"
        f"\"{comment_text}\"\n\n"
        f"Reply to this comment. Be specific and valuable, 3 lines max.{style_hint}"
    )
    return _call_llm(persona, user_msg)


def generate_comment(persona: str, post: dict, engage_topics: list = None) -> str | None:
    """Generate comment on another creator's post. Returns None if nothing to say."""
    title = post.get("title", "")
    content = post.get("content_preview", post.get("content", ""))[:300]

    # engage_topics filter: skip unrelated posts
    if engage_topics:
        combined = f"{title} {content}".lower()
        if not any(t.lower() in combined for t in engage_topics):
            return None

    user_msg = (
        f"Another creator's post:\n"
        f"Title: {title}\n"
        f"Content: {content}\n\n"
        "Leave a comment on this post. Add specific insights. 3 lines max.\n"
        "If you have nothing to say, reply with just 'SKIP'."
    )

    reply = _call_llm(persona, user_msg)
    if "SKIP" in reply.upper():
        return None
    return reply
