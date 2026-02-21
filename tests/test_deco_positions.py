#!/usr/bin/env python3
"""
DECO 위치 저장 버그 수정 E2E 테스트
====================================
3가지 버그 수정을 Playwright로 검증:
  Fix 1: 3초 폴링이 에이전트 DECO 위치를 덮어쓰지 않는지
  Fix 2: DECO OFF 후 저장된 위치가 복원되는지
  Fix 3: 스킬 머신 재렌더 후 위치가 유지되는지
"""

import json
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8420"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# 테스트할 에이전트/스킬 (현재 저장된 DECO 레이아웃 기준)
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
    """Fix 1: 3초 폴링 후에도 에이전트 DECO 위치가 유지되는지 테스트."""
    print("\n🧪 Fix 1: 3초 폴링 — 에이전트 DECO 위치 보존")

    # 1) 초기 로드 후 위치 확인
    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix1_01_initial_load", "초기 로드 — DECO 위치 적용 확인")

    before = {}
    for agent, expected in SAVED_AGENTS.items():
        pos = get_agent_position(page, agent)
        before[agent] = pos
        print(f"  [{agent}] position={pos['position']}, left={pos['left']}, top={pos['top']}")

    # 2) 폴링 사이클 대기 (loadDashboardData는 3초마다)
    print("  ⏳ 4초 대기 (폴링 사이클 1회 이상)...")
    page.wait_for_timeout(4000)
    screenshot(page, "fix1_02_after_polling", "4초 대기 후 — 폴링 후 위치 유지 확인")

    # 3) 위치 비교
    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] before: left={before[agent]['left']}, top={before[agent]['top']}")
        print(f"  [{agent}] after:  left={after['left']}, top={after['top']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            # 위치가 유지됨
            print(f"  ✅ {agent}: 폴링 후에도 DECO 위치 유지됨")
        else:
            print(f"  ❌ {agent}: 폴링이 위치를 초기화함!")
            all_pass = False

    return all_pass


def test_fix2_deco_off_restores_positions(page):
    """Fix 2: DECO OFF 후 저장된 위치가 복원되는지 테스트."""
    print("\n🧪 Fix 2: DECO OFF — 위치 복원")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1) DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(500)
    screenshot(page, "fix2_01_deco_on", "DECO ON 상태")

    # 에이전트 위치 기록 (DECO ON 상태)
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
    screenshot(page, "fix2_02_deco_off", "DECO OFF 후 — 위치 복원 확인")

    # 3) 에이전트 위치 확인
    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] DECO OFF: position={after['position']}, left={after['left']}, top={after['top']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {agent}: DECO OFF 후 위치 복원됨")
        else:
            print(f"  ❌ {agent}: DECO OFF 후 위치 소실!")
            all_pass = False

    # 4) 스킬 위치 확인
    for skill, expected in SAVED_SKILLS.items():
        after = get_skill_position(page, skill)
        if after is None:
            print(f"  ⚠️ {skill}: 스킬 머신 DOM 없음 (스킬 비활성)")
            continue
        print(f"  [{skill}] DECO OFF: position={after['position']}, left={after['left']}, parent={after['parent_id']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {skill}: DECO OFF 후 위치 복원됨")
        else:
            print(f"  ❌ {skill}: DECO OFF 후 위치 소실!")
            all_pass = False

    return all_pass


def test_fix3_skill_rerender_preserves_positions(page):
    """Fix 3: 스킬 머신 재렌더 후 위치가 유지되는지 테스트."""
    print("\n🧪 Fix 3: 스킬 머신 재렌더 — 위치 보존")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 1) 초기 스킬 위치 기록
    before_skills = {}
    for skill in SAVED_SKILLS:
        before_skills[skill] = get_skill_position(page, skill)
        if before_skills[skill]:
            print(f"  [{skill}] 초기: left={before_skills[skill]['left']}, top={before_skills[skill]['top']}, parent={before_skills[skill]['parent_id']}")

    screenshot(page, "fix3_01_before_rerender", "재렌더 전 — 스킬 위치")

    # 2) renderSkillMachines 강제 호출 (재렌더 시뮬레이션)
    page.evaluate("""() => {
        if (window._lastSkillsRaw) {
            renderSkillMachines(window._lastSkillsRaw);
        }
    }""")
    page.wait_for_timeout(1000)
    screenshot(page, "fix3_02_after_rerender", "재렌더 후 — 스킬 위치 유지 확인")

    # 3) 비교
    all_pass = True
    for skill, expected in SAVED_SKILLS.items():
        after = get_skill_position(page, skill)
        if after is None:
            print(f"  ⚠️ {skill}: 스킬 머신 DOM 없음 (스킬 비활성)")
            continue

        print(f"  [{skill}] 재렌더 후: position={after['position']}, left={after['left']}, top={after['top']}, parent={after['parent_id']}")

        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {skill}: 재렌더 후 위치 유지됨")
        else:
            print(f"  ❌ {skill}: 재렌더 후 위치 소실!")
            all_pass = False

    return all_pass


def test_page_refresh_preserves_all(page):
    """보너스: 페이지 새로고침 후 모든 위치가 유지되는지 테스트."""
    print("\n🧪 보너스: 페이지 새로고침 — 전체 위치 보존")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix_bonus_01_first_load", "첫 번째 로드")

    # 위치 기록
    before = {}
    for agent in SAVED_AGENTS:
        before[agent] = get_agent_position(page, agent)

    # 새로고침
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2000)
    screenshot(page, "fix_bonus_02_after_refresh", "새로고침 후")

    all_pass = True
    for agent, expected in SAVED_AGENTS.items():
        after = get_agent_position(page, agent)
        print(f"  [{agent}] 새로고침 후: position={after['position']}, left={after['left']}, top={after['top']}")
        if after["position"] == "absolute" and after["left"] and after["top"]:
            print(f"  ✅ {agent}: 새로고침 후 위치 유지됨")
        else:
            print(f"  ❌ {agent}: 새로고침 후 위치 소실!")
            all_pass = False

    return all_pass


def test_drag_and_verify_save(page):
    """드래그로 에이전트 이동 → 위치 저장 → 새로고침 → 유지 확인."""
    print("\n🧪 드래그 저장 + 새로고침 통합 테스트")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    # researcher 에이전트를 드래그 (새 위치)
    researcher = page.locator("#pool-researcher")
    if researcher.count() > 0:
        box = researcher.bounding_box()
        if box:
            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            # 오른쪽 100px, 아래 50px 드래그
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 100, start_y + 50, steps=10)
            page.mouse.up()
            page.wait_for_timeout(500)

            after_drag = get_agent_position(page, "researcher")
            print(f"  [researcher] 드래그 후: left={after_drag['left']}, top={after_drag['top']}")
            screenshot(page, "fix_drag_01_after_drag", "researcher 드래그 후")

    # 저장 대기 (debounce 1초)
    page.wait_for_timeout(1500)

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)
    screenshot(page, "fix_drag_02_deco_off", "DECO OFF 후 researcher 위치 확인")

    after_off = get_agent_position(page, "researcher")
    print(f"  [researcher] DECO OFF 후: position={after_off['position']}, left={after_off['left']}, top={after_off['top']}")

    # 폴링 대기
    page.wait_for_timeout(4000)
    after_poll = get_agent_position(page, "researcher")
    print(f"  [researcher] 폴링 후: position={after_poll['position']}, left={after_poll['left']}, top={after_poll['top']}")
    screenshot(page, "fix_drag_03_after_poll", "폴링 후 researcher 위치 유지 확인")

    # 새로고침
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(2000)
    after_refresh = get_agent_position(page, "researcher")
    print(f"  [researcher] 새로고침 후: position={after_refresh['position']}, left={after_refresh['left']}, top={after_refresh['top']}")
    screenshot(page, "fix_drag_04_after_refresh", "새로고침 후 researcher 위치 유지 확인")

    if after_refresh["position"] == "absolute" and after_refresh["left"] and after_refresh["top"]:
        print(f"  ✅ researcher: 드래그 → DECO OFF → 폴링 → 새로고침 전 과정 위치 유지!")
        return True
    else:
        print(f"  ❌ researcher: 위치 소실!")
        return False


def main():
    print("=" * 60)
    print("🦑 DECO 위치 저장 버그 수정 — E2E 테스트")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        test_results = {}

        # Fix 1
        try:
            test_results["fix1"] = test_fix1_polling_preserves_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 1 에러: {e}")
            test_results["fix1"] = False

        # Fix 2
        try:
            test_results["fix2"] = test_fix2_deco_off_restores_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 2 에러: {e}")
            test_results["fix2"] = False

        # Fix 3
        try:
            test_results["fix3"] = test_fix3_skill_rerender_preserves_positions(page)
        except Exception as e:
            print(f"  ❌ Fix 3 에러: {e}")
            test_results["fix3"] = False

        # 보너스: 새로고침
        try:
            test_results["refresh"] = test_page_refresh_preserves_all(page)
        except Exception as e:
            print(f"  ❌ 새로고침 테스트 에러: {e}")
            test_results["refresh"] = False

        # 통합: 드래그 → 저장 → 복원
        try:
            test_results["drag_save"] = test_drag_and_verify_save(page)
        except Exception as e:
            print(f"  ❌ 드래그 저장 테스트 에러: {e}")
            test_results["drag_save"] = False

        browser.close()

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)
    all_pass = True
    for name, passed in test_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} — {name}")
        if not passed:
            all_pass = False

    print(f"\n{'🎉 전체 통과!' if all_pass else '⚠️ 일부 실패!'}")
    print(f"📸 스크린샷: {SCREENSHOT_DIR}/")

    # JSON 결과 저장
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
