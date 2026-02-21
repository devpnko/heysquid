#!/usr/bin/env python3
"""
DECO 가드 E2E 테스트
====================
1. DECO ON 상태에서 3초 폴링 후 스킬 머신이 사라지지 않는지
2. DECO ON 상태에서 에이전트를 드래그로 이동할 수 있는지
3. DECO OFF 후 스킬/워크스페이스가 정상 렌더되는지
"""

import json
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8420"
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []


def screenshot(page, name, desc=""):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.locator(".viewport").screenshot(path=path, type="png")
    results.append({"name": name, "desc": desc, "path": path})
    print(f"  📸 {name}: {desc}")
    return path


def test_deco_skills_persist_after_polling(page):
    """DECO ON 상태에서 3초 폴링 후 스킬 머신이 사라지지 않는지."""
    print("\n🧪 Test 1: DECO ON — 스킬 머신 폴링 후 유지")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 초기 스킬 개수 확인
    initial_count = page.locator(".skill-machine").count()
    print(f"  초기 스킬 머신 수: {initial_count}")

    if initial_count == 0:
        print("  ⚠️ 스킬 머신이 없음 (스킬 비활성 상태) — 스킵")
        return True

    screenshot(page, "guard_01_before_deco", "DECO OFF — 초기 상태")

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    deco_count = page.locator(".skill-machine").count()
    print(f"  DECO ON 직후 스킬 머신 수: {deco_count}")
    screenshot(page, "guard_02_deco_on", "DECO ON 직후")

    # 폴링 사이클 대기 (3초 × 2 = 6초)
    print("  ⏳ 7초 대기 (폴링 사이클 2회)...")
    page.wait_for_timeout(7000)

    after_count = page.locator(".skill-machine").count()
    print(f"  폴링 후 스킬 머신 수: {after_count}")
    screenshot(page, "guard_03_after_polling", "폴링 2회 후")

    if after_count >= initial_count:
        print(f"  ✅ 스킬 머신 유지됨 ({after_count}개)")
        # DECO OFF
        page.click("#btnDeco")
        page.wait_for_timeout(500)
        return True
    else:
        print(f"  ❌ 스킬 머신 사라짐! {initial_count} → {after_count}")
        page.click("#btnDeco")
        page.wait_for_timeout(500)
        return False


def test_deco_agent_draggable(page):
    """DECO ON 상태에서 에이전트를 드래그로 이동할 수 있는지."""
    print("\n🧪 Test 2: DECO ON — 에이전트 드래그 이동")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # JS dispatchEvent로 드래그 (Playwright headless 마우스는 decoMakeDraggable과 호환 이슈)
    drag_result = page.evaluate("""() => {
        var agent = document.getElementById('pool-researcher');
        if (!agent) return { error: 'no agent' };
        var before = { left: agent.style.left, top: agent.style.top };

        var downEvt = new MouseEvent('mousedown', {
            bubbles: true, cancelable: true, button: 0,
            clientX: 300, clientY: 700
        });
        agent.dispatchEvent(downEvt);

        var moveEvt = new MouseEvent('mousemove', {
            bubbles: true, cancelable: true,
            clientX: 380, clientY: 760
        });
        document.dispatchEvent(moveEvt);

        var upEvt = new MouseEvent('mouseup', {
            bubbles: true, cancelable: true,
            clientX: 380, clientY: 760
        });
        document.dispatchEvent(upEvt);

        var after = { left: agent.style.left, top: agent.style.top };
        return { before: before, after: after, moved: before.left !== after.left || before.top !== after.top };
    }""")

    print(f"  드래그 결과: {drag_result}")
    screenshot(page, "guard_04_agent_drag", "에이전트 드래그 후")
    moved = drag_result.get("moved", False)

    if moved:
        print(f"  ✅ 에이전트 이동 성공!")
    else:
        print(f"  ❌ 에이전트 이동 실패")

    # 폴링 후에도 위치 유지?
    after_left = drag_result.get("after", {}).get("left", "")
    after_top = drag_result.get("after", {}).get("top", "")
    print(f"  ⏳ 4초 대기 (폴링 1회)...")
    page.wait_for_timeout(4000)

    poll_pos = page.evaluate("""() => {
        var a = document.getElementById('pool-researcher');
        return { left: a.style.left, top: a.style.top };
    }""")
    print(f"  폴링 후: left={poll_pos['left']}, top={poll_pos['top']}")

    position_kept = (after_left == poll_pos["left"]) and (after_top == poll_pos["top"])
    if position_kept:
        print(f"  ✅ 폴링 후에도 에이전트 위치 유지됨")
    else:
        print(f"  ❌ 폴링 후 에이전트 위치 변경됨!")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    return moved and position_kept


def test_deco_off_full_rerender(page):
    """DECO OFF 후 스킬/워크스페이스가 정상 렌더되는지."""
    print("\n🧪 Test 3: DECO OFF — 전체 재렌더")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # 초기 상태
    initial_skills = page.locator(".skill-machine").count()
    initial_zones = page.locator(".workspace-zone").count()
    print(f"  초기: 스킬 {initial_skills}개, 워크스페이스 {initial_zones}개")

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # 폴링 1회 대기
    page.wait_for_timeout(4000)
    screenshot(page, "guard_06_deco_before_off", "DECO ON + 폴링 후")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(2000)

    # 다음 폴링까지 대기 (cache가 null이므로 재렌더 트리거)
    page.wait_for_timeout(4000)

    after_skills = page.locator(".skill-machine").count()
    after_zones = page.locator(".workspace-zone").count()
    print(f"  DECO OFF 후: 스킬 {after_skills}개, 워크스페이스 {after_zones}개")
    screenshot(page, "guard_07_deco_off_rerendered", "DECO OFF + 폴링 후")

    skills_ok = after_skills >= initial_skills
    zones_ok = after_zones >= initial_zones

    if skills_ok:
        print(f"  ✅ 스킬 정상 ({after_skills}개)")
    else:
        print(f"  ❌ 스킬 감소 {initial_skills} → {after_skills}")

    if zones_ok:
        print(f"  ✅ 워크스페이스 정상 ({after_zones}개)")
    else:
        print(f"  ❌ 워크스페이스 감소 {initial_zones} → {after_zones}")

    return skills_ok and zones_ok


def test_deco_skill_drag(page):
    """DECO ON 상태에서 스킬 머신을 드래그로 이동할 수 있는지."""
    print("\n🧪 Test 4: DECO ON — 스킬 머신 드래그 이동")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    initial_skills = page.locator(".skill-machine").count()
    if initial_skills == 0:
        print("  ⚠️ 스킬 머신 없음 — 스킵")
        return True

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # JS dispatchEvent로 스킬 드래그
    drag_result = page.evaluate("""() => {
        var skill = document.querySelector('.skill-machine');
        if (!skill) return { error: 'no skill' };
        var name = skill.dataset.skill;
        var before = { left: skill.style.left, top: skill.style.top };

        var downEvt = new MouseEvent('mousedown', {
            bubbles: true, cancelable: true, button: 0,
            clientX: 500, clientY: 550
        });
        skill.dispatchEvent(downEvt);

        var moveEvt = new MouseEvent('mousemove', {
            bubbles: true, cancelable: true,
            clientX: 560, clientY: 590
        });
        document.dispatchEvent(moveEvt);

        var upEvt = new MouseEvent('mouseup', {
            bubbles: true, cancelable: true,
            clientX: 560, clientY: 590
        });
        document.dispatchEvent(upEvt);

        var after = { left: skill.style.left, top: skill.style.top };
        return { name: name, before: before, after: after, moved: before.left !== after.left || before.top !== after.top };
    }""")

    print(f"  드래그 결과: {drag_result}")
    moved = drag_result.get("moved", False)
    skill_name = drag_result.get("name", "?")

    if moved:
        print(f"  ✅ 스킬 [{skill_name}] 드래그 이동 성공")
    else:
        print(f"  ❌ 스킬 [{skill_name}] 드래그 이동 실패")

    # 폴링 후에도 위치 유지?
    after_left = drag_result.get("after", {}).get("left", "")
    after_top = drag_result.get("after", {}).get("top", "")
    print(f"  ⏳ 4초 대기 (폴링 1회)...")
    page.wait_for_timeout(4000)

    poll_info = page.evaluate("""(name) => {
        var el = document.querySelector('.skill-machine[data-skill="' + name + '"]');
        return el ? { exists: true, left: el.style.left, top: el.style.top } : { exists: false };
    }""", skill_name)
    print(f"  폴링 후: {poll_info}")

    screenshot(page, "guard_08_skill_after_poll", f"스킬 드래그 + 폴링 후 ({skill_name})")

    position_kept = poll_info.get("exists", False) and (after_left == poll_info.get("left")) and (after_top == poll_info.get("top"))

    if position_kept:
        print(f"  ✅ 폴링 후에도 스킬 위치 유지")
    else:
        print(f"  ❌ 폴링 후 스킬 위치/존재 변경됨")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    return moved and position_kept


def main():
    print("=" * 60)
    print("🦑 DECO 가드 — 스킬 사라짐 + 에이전트 위치 깨짐 수정 검증")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        test_results = {}

        tests = [
            ("skills_persist", test_deco_skills_persist_after_polling),
            ("agent_drag", test_deco_agent_draggable),
            ("skill_drag", test_deco_skill_drag),
            ("deco_off_rerender", test_deco_off_full_rerender),
        ]

        for name, fn in tests:
            try:
                test_results[name] = fn(page)
            except Exception as e:
                print(f"  ❌ {name} 에러: {e}")
                import traceback
                traceback.print_exc()
                test_results[name] = False

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
        "screenshots": results,
    }
    result_path = os.path.join(SCREENSHOT_DIR, "guard_results.json")
    with open(result_path, "w") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
