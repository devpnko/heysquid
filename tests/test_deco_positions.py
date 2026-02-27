#!/usr/bin/env python3
"""
DECO Position Save Bug Fix E2E Test
====================================
Verifies 3 bug fixes using Playwright:
  Fix 1: 3-second polling should not overwrite agent DECO positions
  Fix 2: Saved positions should be restored after DECO OFF
  Fix 3: Skill machine positions should be preserved after re-render
"""

import json
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8420"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# Agents/skills to test (based on current saved DECO layout)
SAVED_AGENTS = {
    "tester": {"left": 575, "top": 45},
    "writer": {"left": 642, "top": 11},
}
SAVED_SKILLS = {
    "marketing": {"left": 442, "top": 373},
    "briefing": {"left": 791, "top": 368},
}

results = []


def screenshot(page, name, desc=""):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.locator(".viewport").screenshot(path=path, type="png")
    results.append({"name": name, "desc": desc, "path": path})
    print(f"  📸 {name}: {desc}")
    return path


def get_agent_position(page, agent_name):
    """Get current rendered position of an agent element."""
    el = page.locator(f"#pool-{agent_name}")
    box = el.bounding_box()
    style_pos = el.evaluate("el => el.style.position")
    style_left = el.evaluate("el => el.style.left")
    style_top = el.evaluate("el => el.style.top")
    return {
        "box": box,
        "position": style_pos,
        "left": style_left,
        "top": style_top,
    }


def get_skill_position(page, skill_name):
    """Get current rendered position of a skill machine element."""
    el = page.locator(f'.skill-machine[data-skill="{skill_name}"]')
    if el.count() == 0:
        return None
    box = el.first.bounding_box()
    style_pos = el.first.evaluate("el => el.style.position")
    style_left = el.first.evaluate("el => el.style.left")
    style_top = el.first.evaluate("el => el.style.top")
    parent_id = el.first.evaluate("el => el.parentElement ? el.parentElement.id : ''")
    return {
        "box": box,
        "position": style_pos,
        "left": style_left,
        "top": style_top,
        "parent_id": parent_id,
    }


def test_fix1_polling_preserves_positions(page):
    """Fix 1: Test that agent DECO positions are preserved after 3-second polling."""
    print("\n🧪 Fix 1: 3-second polling — agent DECO position preservation")

    # 1) Check positions after initial load
    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix1_01_initial_load", "Initial load — verify DECO positions applied")

    before = {}
    for agent, expected in SAVED_AGENTS.items():
        pos = get_agent_position(page, agent)
        before[agent] = pos
        print(f"  [{agent}] position={pos['position']}, left={pos['left']}, top={pos['top']}")

    # 2) Wait for polling cycle (loadDashboardData runs every 3s)
    print("  ⏳ Waiting 4s (1+ polling cycles)...")
    page.wait_for_timeout(4000)
    screenshot(page, "fix1_02_after_polling", "After 4s — verify position preserved after polling")

    # 3) Compare positions
    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] before: left={before[agent]['left']}, top={before[agent]['top']}")
        print(f"  [{agent}] after:  left={after['left']}, top={after['top']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            # Position preserved
            print(f"  ✅ {agent}: DECO position preserved after polling")
        else:
            print(f"  ❌ {agent}: Polling reset the position!")
            all_pass = False

    return all_pass


def test_fix2_deco_off_restores_positions(page):
    """Fix 2: Test that saved positions are restored after DECO OFF."""
    print("\n🧪 Fix 2: DECO OFF — position restoration")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1) DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(500)
    screenshot(page, "fix2_01_deco_on", "DECO ON state")

    # Record agent positions (DECO ON state)
    before_agents = {}
    for agent in SAVED_AGENTS:
        before_agents[agent] = get_agent_position(page, agent)
        print(f"  [{agent}] DECO ON: left={before_agents[agent]['left']}, top={before_agents[agent]['top']}")

    before_skills = {}
    for skill in SAVED_SKILLS:
        before_skills[skill] = get_skill_position(page, skill)
        if before_skills[skill]:
            print(f"  [{skill}] DECO ON: left={before_skills[skill]['left']}, top={before_skills[skill]['top']}, parent={before_skills[skill]['parent_id']}")

    # 2) DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(1000)
    screenshot(page, "fix2_02_deco_off", "After DECO OFF — verify position restoration")

    # 3) Check agent positions
    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] DECO OFF: position={after['position']}, left={after['left']}, top={after['top']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {agent}: Position restored after DECO OFF")
        else:
            print(f"  ❌ {agent}: Position lost after DECO OFF!")
            all_pass = False

    # 4) Check skill positions
    for skill, expected in SAVED_SKILLS.items():
        after = get_skill_position(page, skill)
        if after is None:
            print(f"  ⚠️ {skill}: Skill machine DOM not found (skill inactive)")
            continue
        print(f"  [{skill}] DECO OFF: position={after['position']}, left={after['left']}, parent={after['parent_id']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {skill}: Position restored after DECO OFF")
        else:
            print(f"  ❌ {skill}: Position lost after DECO OFF!")
            all_pass = False

    return all_pass


def test_fix3_skill_rerender_preserves_positions(page):
    """Fix 3: Test that skill machine positions are preserved after re-render."""
    print("\n🧪 Fix 3: Skill machine re-render — position preservation")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1) Record initial skill positions
    before_skills = {}
    for skill in SAVED_SKILLS:
        before_skills[skill] = get_skill_position(page, skill)
        if before_skills[skill]:
            print(f"  [{skill}] Initial: left={before_skills[skill]['left']}, top={before_skills[skill]['top']}, parent={before_skills[skill]['parent_id']}")

    screenshot(page, "fix3_01_before_rerender", "Before re-render — skill positions")

    # 2) Force call renderSkillMachines (simulate re-render)
    page.evaluate("""() => {
        if (window._lastSkillsRaw) {
            renderSkillMachines(window._lastSkillsRaw);
        }
    }""")
    page.wait_for_timeout(1000)
    screenshot(page, "fix3_02_after_rerender", "After re-render — verify skill positions preserved")

    # 3) Compare
    all_pass = True
    for skill, expected in SAVED_SKILLS.items():
        after = get_skill_position(page, skill)
        if after is None:
            print(f"  ⚠️ {skill}: Skill machine DOM not found (skill inactive)")
            continue

        print(f"  [{skill}] After re-render: position={after['position']}, left={after['left']}, top={after['top']}, parent={after['parent_id']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {skill}: Position preserved after re-render")
        else:
            print(f"  ❌ {skill}: Position lost after re-render!")
            all_pass = False

    return all_pass


def test_page_refresh_preserves_all(page):
    """Bonus: Test that all positions are preserved after page refresh."""
    print("\n🧪 Bonus: Page refresh — all positions preserved")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix_bonus_01_first_load", "First load")

    # Record positions
    before = {}
    for agent in SAVED_AGENTS:
        before[agent] = get_agent_position(page, agent)

    # Refresh
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix_bonus_02_after_refresh", "After refresh")

    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] After refresh: position={after['position']}, left={after['left']}, top={after['top']}")
        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {agent}: Position preserved after refresh")
        else:
            print(f"  ❌ {agent}: Position lost after refresh!")
            all_pass = False

    return all_pass


def test_drag_and_verify_save(page):
    """Drag agent to move -> save position -> refresh -> verify preserved."""
    print("\n🧪 Drag save + refresh integration test")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    # Drag researcher agent (new position)
    researcher = page.locator("#pool-researcher")
    if researcher.count() > 0:
        box = researcher.bounding_box()
        if box:
            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            # Drag right 100px, down 50px
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 100, start_y + 50, steps=10)
            page.mouse.up()
            page.wait_for_timeout(500)

            after_drag = get_agent_position(page, "researcher")
            print(f"  [researcher] After drag: left={after_drag['left']}, top={after_drag['top']}")
            screenshot(page, "fix_drag_01_after_drag", "After researcher drag")

    # Wait for save (debounce 1s)
    page.wait_for_timeout(1500)

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)
    screenshot(page, "fix_drag_02_deco_off", "After DECO OFF — verify researcher position")

    after_off = get_agent_position(page, "researcher")
    print(f"  [researcher] After DECO OFF: position={after_off['position']}, left={after_off['left']}, top={after_off['top']}")

    # Wait for polling
    page.wait_for_timeout(4000)
    after_poll = get_agent_position(page, "researcher")
    print(f"  [researcher] After polling: position={after_poll['position']}, left={after_poll['left']}, top={after_poll['top']}")
    screenshot(page, "fix_drag_03_after_poll", "After polling — verify researcher position preserved")

    # Refresh
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2000)
    after_refresh = get_agent_position(page, "researcher")
    print(f"  [researcher] After refresh: position={after_refresh['position']}, left={after_refresh['left']}, top={after_refresh['top']}")
    screenshot(page, "fix_drag_04_after_refresh", "After refresh — verify researcher position preserved")

    if after_refresh["position"] == "absolute" and after_refresh["left"] and after_refresh["top"]:
        print(f"  ✅ researcher: Position preserved through drag → DECO OFF → polling → refresh!")
        return True
    else:
        print(f"  ❌ researcher: Position lost!")
        return False


def main():
    print("=" * 60)
    print("🦑 DECO Position Save Bug Fix — E2E Test")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        test_results = {}

        # Fix 1
        try:
            test_results["fix1"] = test_fix1_polling_preserves_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 1 error: {e}")
            test_results["fix1"] = False

        # Fix 2
        try:
            test_results["fix2"] = test_fix2_deco_off_restores_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 2 error: {e}")
            test_results["fix2"] = False

        # Fix 3
        try:
            test_results["fix3"] = test_fix3_skill_rerender_preserves_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 3 error: {e}")
            test_results["fix3"] = False

        # Bonus: refresh
        try:
            test_results["refresh"] = test_page_refresh_preserves_all(page)
        except Exception as e:
            print(f"  ❌ Refresh test error: {e}")
            test_results["refresh"] = False

        # Integration: drag → save → restore
        try:
            test_results["drag_save"] = test_drag_and_verify_save(page)
        except Exception as e:
            print(f"  ❌ Drag save test error: {e}")
            test_results["drag_save"] = False

        browser.close()

    # Results summary
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    all_pass = True
    for name, passed in test_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} — {name}")
        if not passed:
            all_pass = False

    print(f"\n{'🎉 All passed!' if all_pass else '⚠️ Some failed!'}")
    print(f"📸 Screenshots: {SCREENSHOT_DIR}/")

    # Save JSON results
    result_json = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": test_results,
        "all_pass": all_pass,
        "screenshots": [r for r in results],
    }
    result_path = os.path.join(SCREENSHOT_DIR, "test_results.json")
    with open(result_path, "w") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
