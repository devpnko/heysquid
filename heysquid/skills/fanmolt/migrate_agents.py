#!/usr/bin/env python3
"""Migrate FanMolt agent JSONs from flat v1 structure to new 9-section v2 structure.

Sections: who | soul | what | whom | mind | do | beat | where | _now

Usage:
    cd /Users/hyuk/heysquid
    python -m heysquid.skills.fanmolt.migrate_agents [--dry-run]
    python heysquid/skills/fanmolt/migrate_agents.py [--dry-run]
"""

import json
import sys
from datetime import datetime
from pathlib import Path

AGENTS_DIR = Path(__file__).parent / "agents"

CATEGORY_CREATURES = {
    "create": "크리에이터",
    "build": "빌더",
    "money": "금융 분석가",
    "learn": "교육 전문가",
    "life": "라이프스타일 전문가",
    "entertainment": "엔터테인먼트 크리에이터",
    "health": "건강 전문가",
    "tech": "테크 전문가",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def migrate_one(old: dict) -> dict:
    """Convert one agent from flat v1 to 9-section v2 structure."""
    bp = old.get("blueprint") or {}
    bp_persona = bp.get("persona") or {}
    bp_expertise = bp.get("expertise") or {}
    bp_engagement = bp.get("engagement") or {}
    bp_recipes = bp.get("recipes") or []
    bp_rules = bp.get("rules") or []

    category = old.get("category", "build")
    creature = CATEGORY_CREATURES.get(category, "AI 크리에이터")

    # soul.core: prefer blueprint.persona.system_prompt (no duplication), else top-level persona
    soul_core = bp_persona.get("system_prompt") or old.get("persona", "")

    new = {
        "who": {
            "handle": old.get("handle", ""),
            "name": old.get("name", ""),
            "emoji": "",
            "creature": creature,
            "born_at": old.get("created_at", _now()),
        },
        "soul": {
            "core": soul_core,
            "tone": bp_persona.get("tone", []),
            "boundaries": bp_rules,
            "updated_at": old.get("created_at", _now()),
        },
        "what": {
            "domain": bp_expertise.get("domain", category),
            "topics": bp_expertise.get("topics", old.get("tags", [])),
            "languages": bp_persona.get("languages", ["ko"]),
            "sources": bp_expertise.get("sources", []),
        },
        "whom": {
            "pm": {"name": "상혁", "notes": ""},
            "audience": {
                "who": "",
                "wants": [],
                "topics": bp_engagement.get("engage_topics", old.get("tags", [])),
            },
        },
        "mind": {
            "events": [],
            "lessons": [],
        },
        "do": {
            "recipes": bp_recipes,
            "engagement": {
                "reply_style": bp_engagement.get("reply_style", "helpful"),
                "browse_feed": bp_engagement.get("browse_feed", True),
            },
        },
        "beat": old.get("activity") or {
            "schedule_hours": 1,
            "min_post_interval_hours": 0,
            "min_comment_interval_sec": 3,
            "max_comments_per_beat": 10,
            "max_replies_per_beat": 20,
            "post_ratio_free": 70,
        },
        "where": {
            "platform": "fanmolt",
            "api_key": old.get("api_key", ""),
            "category": category,
            "tags": old.get("tags", []),
        },
        "_now": {
            "stats": old.get("stats", {"posts": 0, "comments": 0, "replies": 0}),
            "last_post_at": old.get("last_post_at"),
            "last_heartbeat_at": old.get("last_heartbeat_at"),
            "recipe_states": old.get("recipe_states", {}),
            "commented_posts": old.get("commented_posts", []),
            "replied_comments": old.get("replied_comments", []),
            **({"last_notification_id": old["last_notification_id"]}
               if "last_notification_id" in old else {}),
        },
    }
    return new


def main(dry_run: bool = False):
    paths = [p for p in sorted(AGENTS_DIR.glob("*.json")) if not p.name.startswith("_")]
    migrated = skipped = failed = 0

    for path in paths:
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ERROR reading {path.name}: {e}")
            failed += 1
            continue

        # Already migrated?
        if "who" in old:
            print(f"  SKIP {path.name} — already v2")
            skipped += 1
            continue

        new = migrate_one(old)
        handle = new["who"]["handle"]

        if dry_run:
            print(f"  DRY-RUN {path.name} → {handle} ({new['who']['creature']})")
            migrated += 1
            continue

        # Backup original
        bak_path = path.with_suffix(".json.bak")
        bak_path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")

        # Write new structure
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  OK {path.name} → {handle} ({new['who']['creature']})  [backup: {bak_path.name}]")
        migrated += 1

    print(f"\nDone: {migrated} migrated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN (no files will be written) ===")
    print(f"Target: {AGENTS_DIR}\n")
    main(dry_run=dry_run)
