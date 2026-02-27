"""Heartbeat 러너 — 에이전트 활동 1사이클."""

import logging
import random
import time
from datetime import datetime, timedelta

from .agent_manager import load_agent, save_agent, list_agents
from .api_client import FanMoltClient
from .content_gen import generate_post, generate_reply, generate_comment

logger = logging.getLogger(__name__)

# 쿨다운 (보수적 — API rate limit의 2배)
MIN_POST_INTERVAL_HOURS = 2
MIN_COMMENT_INTERVAL_SEC = 30
MAX_COMMENTS_PER_BEAT = 3
MAX_REPLIES_PER_BEAT = 5
MAX_COMMENTED_POSTS_CACHE = 100  # ring buffer 최대 크기
DEFAULT_SCHEDULE_HOURS = 4  # 에이전트별 기본 heartbeat 주기


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hours_since(iso_str: str | None) -> float:
    if not iso_str:
        return 999
    try:
        dt = datetime.fromisoformat(iso_str)
        return (datetime.now() - dt).total_seconds() / 3600
    except Exception:
        return 999


def run_heartbeat(handle: str) -> dict:
    """에이전트 1명의 heartbeat 1사이클.

    우선순위: 댓글 답변 > 피드 참여 > 글 작성
    """
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"에이전트 없음: {handle}", "handle": handle}

    client = FanMoltClient(agent["api_key"])
    persona = agent.get("persona", "")
    result = {"handle": handle, "replies": 0, "comments": 0, "posted": False}

    llm_failed = False

    # 1. 알림 확인 → 댓글 답변 (최우선, MAX_REPLIES_PER_BEAT 상한)
    try:
        last_noti_id = agent.get("last_notification_id")
        noti_params = {"since": agent.get("last_heartbeat_at")}
        if last_noti_id:
            noti_params = {"after_id": last_noti_id}
        notifications = client.get_notifications(
            since=noti_params.get("since"),
            after_id=noti_params.get("after_id"),
        )
        replied = 0
        for n in notifications:
            if replied >= MAX_REPLIES_PER_BEAT:
                break
            if n.get("type") in ("comment.created", "comment.reply"):
                try:
                    reply = generate_reply(persona, n)
                    client.create_comment(n["post_id"], reply, parent_id=n.get("comment_id"))
                    replied += 1
                    time.sleep(MIN_COMMENT_INTERVAL_SEC)
                except RuntimeError:
                    llm_failed = True
                    logger.warning("%s: LLM 불가 — 답변 스킵", handle)
                    break
                except Exception as e:
                    logger.warning("답변 실패: %s", e)
            # cursor 갱신 (처리 여부와 무관하게)
            if n.get("id"):
                agent["last_notification_id"] = n["id"]
        result["replies"] = replied
    except Exception as e:
        logger.warning("알림 조회 실패: %s", e)

    # 2. 피드 탐색 → 댓글 달기 (이미 댓글 단 포스트 스킵)
    if not llm_failed:
        try:
            feed = client.get_feed(sort="new", limit=15)
            commented = 0
            commented_posts = set(agent.get("commented_posts", []))
            for post in feed:
                if commented >= MAX_COMMENTS_PER_BEAT:
                    break
                post_id = post.get("id", "")
                # 내 글 또는 이미 댓글 단 포스트 스킵
                creator = post.get("creator", {})
                if creator.get("handle") == handle:
                    continue
                if post_id in commented_posts:
                    continue
                try:
                    comment = generate_comment(persona, post)
                    if comment:
                        client.create_comment(post_id, comment)
                        commented += 1
                        commented_posts.add(post_id)
                        time.sleep(MIN_COMMENT_INTERVAL_SEC)
                except RuntimeError:
                    llm_failed = True
                    logger.warning("%s: LLM 불가 — 댓글 스킵", handle)
                    break
                except Exception as e:
                    logger.warning("댓글 실패: %s", e)
            result["comments"] = commented
            # ring buffer: 최근 100개만 유지
            agent["commented_posts"] = list(commented_posts)[-MAX_COMMENTED_POSTS_CACHE:]
        except Exception as e:
            logger.warning("피드 조회 실패: %s", e)

    # 3. 글 작성 (쿨다운 체크, LLM 실패 시 스킵)
    if not llm_failed and _hours_since(agent.get("last_post_at")) >= MIN_POST_INTERVAL_HOURS:
        try:
            prev_titles = _get_prev_titles(client)
            post_data = generate_post(persona, agent.get("category", "build"), prev_titles)
            # post_ratio_free 적용 (LLM 판단 대신 확률 기반)
            ratio = agent.get("post_ratio_free", 70)
            post_data["is_free"] = random.random() * 100 < ratio
            client.create_post(**post_data)
            result["posted"] = True
            agent["last_post_at"] = _now()
        except RuntimeError:
            llm_failed = True
            logger.warning("%s: LLM 불가 — 글 작성 스킵", handle)
        except Exception as e:
            logger.warning("글 작성 실패: %s", e)

    if llm_failed:
        result["llm_unavailable"] = True

    # 4. 상태 저장
    agent["last_heartbeat_at"] = _now()
    stats = agent.get("stats", {})
    stats["replies"] = stats.get("replies", 0) + result["replies"]
    stats["comments"] = stats.get("comments", 0) + result["comments"]
    if result["posted"]:
        stats["posts"] = stats.get("posts", 0) + 1
    agent["stats"] = stats
    save_agent(handle, agent)

    result["ok"] = True
    return result


def run_all() -> list[dict]:
    """모든 에이전트 순회 heartbeat (스케줄 무시, 전부 실행)."""
    agents = list_agents()
    results = []
    for agent in agents:
        try:
            r = run_heartbeat(agent["handle"])
            results.append(r)
        except Exception as e:
            results.append({"handle": agent.get("handle", "?"), "ok": False, "error": str(e)})
    return results


def run_due_agents() -> list[dict]:
    """schedule_hours 기반으로 시간이 된 에이전트만 heartbeat.

    에이전트 JSON의 schedule_hours (기본 4) 경과 시에만 실행.
    """
    agents = list_agents()
    results = []
    for agent in agents:
        handle = agent.get("handle", "?")
        interval = agent.get("schedule_hours", DEFAULT_SCHEDULE_HOURS)
        elapsed = _hours_since(agent.get("last_heartbeat_at"))
        if elapsed < interval:
            continue
        try:
            r = run_heartbeat(handle)
            results.append(r)
        except Exception as e:
            results.append({"handle": handle, "ok": False, "error": str(e)})
    return results


def force_post(handle: str) -> dict:
    """쿨다운 무시, 즉시 글 1개 작성."""
    agent = load_agent(handle)
    if not agent:
        return {"ok": False, "error": f"에이전트 없음: {handle}"}

    client = FanMoltClient(agent["api_key"])
    persona = agent.get("persona", "")

    try:
        prev_titles = _get_prev_titles(client)
        post_data = generate_post(persona, agent.get("category", "build"), prev_titles)
        resp = client.create_post(**post_data)
        agent["last_post_at"] = _now()
        stats = agent.get("stats", {})
        stats["posts"] = stats.get("posts", 0) + 1
        agent["stats"] = stats
        save_agent(handle, agent)
        return {"ok": True, "title": post_data.get("title"), "response": resp}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _get_prev_titles(client: FanMoltClient) -> list[str]:
    """이전 글 제목 조회 (중복 방지용)."""
    try:
        posts = client.list_posts(limit=10)
        return [p.get("title", "") for p in posts]
    except Exception:
        return []
