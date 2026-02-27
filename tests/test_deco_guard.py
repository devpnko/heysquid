#!/usr/bin/env python3
"""
DECO Guard E2E Test
====================
1. Skill machines should not disappear after 3-second polling with DECO ON
2. Agents should be draggable with DECO ON
3. Skills/workspaces should render correctly after DECO OFF
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
    """Skill machines should not disappear after 3-second polling with DECO ON."""
    print("\n🧪 Test 1: DECO ON — skill machine persistence after polling")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # Check initial skill count
    initial_count = page.locator(".skill-machine").count()
    print(f"  Initial skill machine count: {initial_count}")

    if initial_count == 0:
        print("  ⚠️ No skill machines (skills inactive) — skipping")
        return True

    screenshot(page, "guard_01_before_deco", "DECO OFF — initial state")

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    deco_count = page.locator(".skill-machine").count()
    print(f"  Skill machine count right after DECO ON: {deco_count}")
    screenshot(page, "guard_02_deco_on", "Right after DECO ON")

    # Wait for polling cycles (3s x 2 = 6s)
    print("  ⏳ Waiting 7s (2 polling cycles)...")
    page.wait_for_timeout(7000)

    after_count = page.locator(".skill-machine").count()
    print(f"  Skill machine count after polling: {after_count}")
    screenshot(page, "guard_03_after_polling", "After 2 polling cycles")

    if after_count >= initial_count:
        print(f"  ✅ Skill machines preserved ({after_count})")
        # DECO OFF
        page.click("#btnDeco")
        page.wait_for_timeout(500)
        return True
    else:
        print(f"  ❌ Skill machines disappeared! {initial_count} → {after_count}")
        page.click("#btnDeco")
        page.wait_for_timeout(500)
        return False


def test_deco_agent_draggable(page):
    """Agents should be draggable with DECO ON."""
    print("\n🧪 Test 2: DECO ON — agent drag movement")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # Drag via JS dispatchEvent (Playwright headless mouse has compatibility issues with decoMakeDraggable)
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

    print(f"  Drag result: {drag_result}")
    screenshot(page, "guard_04_agent_drag", "After agent drag")
    moved = drag_result.get("moved", False)

    if moved:
        print(f"  ✅ Agent move succeeded!")
    else:
        print(f"  ❌ Agent move failed")

    # Position preserved after polling?
    after_left = drag_result.get("after", {}).get("left", "")
    after_top = drag_result.get("after", {}).get("top", "")
    print(f"  ⏳ Waiting 4s (1 polling cycle)...")
    page.wait_for_timeout(4000)

    poll_pos = page.evaluate("""() => {
        var a = document.getElementById('pool-researcher');
        return { left: a.style.left, top: a.style.top };
    }""")
    print(f"  After polling: left={poll_pos['left']}, top={poll_pos['top']}")

    position_kept = (after_left == poll_pos["left"]) and (after_top == poll_pos["top"])
    if position_kept:
        print(f"  ✅ Agent position preserved after polling")
    else:
        print(f"  ❌ Agent position changed after polling!")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    return moved and position_kept


def test_deco_off_full_rerender(page):
    """Skills/workspaces should render correctly after DECO OFF."""
    print("\n🧪 Test 3: DECO OFF — full re-render")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    # Initial state
    initial_skills = page.locator(".skill-machine").count()
    initial_zones = page.locator(".workspace-zone").count()
    print(f"  Initial: {initial_skills} skills, {initial_zones} workspaces")

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # Wait for 1 polling cycle
    page.wait_for_timeout(4000)
    screenshot(page, "guard_06_deco_before_off", "DECO ON + after polling")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(2000)

    # Wait until next polling (cache is null, triggering re-render)
    page.wait_for_timeout(4000)

    after_skills = page.locator(".skill-machine").count()
    after_zones = page.locator(".workspace-zone").count()
    print(f"  After DECO OFF: {after_skills} skills, {after_zones} workspaces")
    screenshot(page, "guard_07_deco_off_rerendered", "DECO OFF + after polling")

    skills_ok = after_skills >= initial_skills
    zones_ok = after_zones >= initial_zones

    if skills_ok:
        print(f"  ✅ Skills OK ({after_skills})")
    else:
        print(f"  ❌ Skills decreased {initial_skills} → {after_skills}")

    if zones_ok:
        print(f"  ✅ Workspaces OK ({after_zones})")
    else:
        print(f"  ❌ Workspaces decreased {initial_zones} → {after_zones}")

    return skills_ok and zones_ok


def test_deco_skill_drag(page):
    """Skill machines should be draggable with DECO ON."""
    print("\n🧪 Test 4: DECO ON — skill machine drag movement")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    initial_skills = page.locator(".skill-machine").count()
    if initial_skills == 0:
        print("  ⚠️ No skill machines — skipping")
        return True

    # DECO ON
    page.click("#btnDeco")
    page.wait_for_timeout(1000)

    # Drag skill via JS dispatchEvent
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

    print(f"  Drag result: {drag_result}")
    moved = drag_result.get("moved", False)
    skill_name = drag_result.get("name", "?")

    if moved:
        print(f"  ✅ Skill [{skill_name}] drag move succeeded")
    else:
        print(f"  ❌ Skill [{skill_name}] drag move failed")

    # Position preserved after polling?
    after_left = drag_result.get("after", {}).get("left", "")
    after_top = drag_result.get("after", {}).get("top", "")
    print(f"  ⏳ Waiting 4s (1 polling cycle)...")
    page.wait_for_timeout(4000)

    poll_info = page.evaluate("""(name) => {
        var el = document.querySelector('.skill-machine[data-skill="' + name + '"]');
        return el ? { exists: true, left: el.style.left, top: el.style.top } : { exists: false };
    }""", skill_name)
    print(f"  After polling: {poll_info}")

    screenshot(page, "guard_08_skill_after_poll", f"Skill drag + after polling ({skill_name})")

    position_kept = poll_info.get("exists", False) and (after_left == poll_info.get("left")) and (after_top == poll_info.get("top"))

    if position_kept:
        print(f"  ✅ Skill position preserved after polling")
    else:
        print(f"  ❌ Skill position/existence changed after polling")

    # DECO OFF
    page.click("#btnDeco")
    page.wait_for_timeout(500)

    return moved and position_kept


def test_skill_reconcile_add_remove(page):
    """Reconcile should work correctly when skills are added/removed."""
    print("\n🧪 Test 5: Reconcile — skill add/remove")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    initial_count = page.locator(".skill-machine").count()
    print(f"  Initial skill count: {initial_count}")

    if initial_count == 0:
        print("  ⚠️ No skills — skipping")
        return True

    # Add a new skill + remove an existing one, then call renderSkillMachines
    result = page.evaluate("""() => {
        var raw = window._lastSkillsRaw;
        if (!raw) return { error: 'no _lastSkillsRaw' };
        var names = Object.keys(raw);
        var removedName = names[0];

        // Add new skill
        var fakeSkills = JSON.parse(JSON.stringify(raw));
        fakeSkills['test_reconcile_skill'] = { name: 'TestReconcile', trigger: 'manual', status: 'idle' };
        // Remove existing one
        delete fakeSkills[removedName];

        // Clear cache + render
        lastSkillsData = null;
        renderSkillMachines(fakeSkills);

        // Verify
        var newEl = document.querySelector('.skill-machine[data-skill="test_reconcile_skill"]');
        var removedEl = document.querySelector('.skill-machine[data-skill="' + removedName + '"]');
        var totalCount = document.querySelectorAll('.skill-machine').length;

        return {
            newExists: !!newEl,
            removedGone: !removedEl,
            totalCount: totalCount,
            expectedCount: Object.keys(fakeSkills).length,
            removedName: removedName
        };
    }""")

    print(f"  Result: {result}")

    if result.get("error"):
        print(f"  ❌ Error: {result['error']}")
        return False

    new_ok = result.get("newExists", False)
    removed_ok = result.get("removedGone", False)
    count_ok = result.get("totalCount") == result.get("expectedCount")

    if new_ok:
        print(f"  ✅ New skill DOM created")
    else:
        print(f"  ❌ New skill DOM not created")

    if removed_ok:
        print(f"  ✅ Removed skill [{result.get('removedName')}] DOM deleted")
    else:
        print(f"  ❌ Removed skill DOM still exists")

    if count_ok:
        print(f"  ✅ Total skill count matches ({result.get('totalCount')})")
    else:
        print(f"  ❌ Skill count mismatch: {result.get('totalCount')} vs expected {result.get('expectedCount')}")

    # Restore: re-render with original data
    page.evaluate("""() => {
        lastSkillsData = null;
        renderSkillMachines(window._lastSkillsRaw);
    }""")

    return new_ok and removed_ok and count_ok


def test_skill_status_update_inplace(page):
    """Skill status change should update CSS class in-place without DOM recreation."""
    print("\n🧪 Test 6: Reconcile — skill status in-place update")

    page.goto(f"{BASE_URL}/dashboard.html", wait_until="networkidle")
    page.wait_for_timeout(2000)

    initial_count = page.locator(".skill-machine").count()
    if initial_count == 0:
        print("  ⚠️ No skills — skipping")
        return True

    result = page.evaluate("""() => {
        var raw = window._lastSkillsRaw;
        if (!raw) return { error: 'no _lastSkillsRaw' };
        var names = Object.keys(raw);
        var targetName = names[0];
        var el = document.querySelector('.skill-machine[data-skill="' + targetName + '"]');
        if (!el) return { error: 'no element' };

        // Record DOM identity (to verify same object)
        el._testMarker = 'reconcile_test_marker';
        var beforeStatus = el.dataset.status;

        // Change status to 'running'
        var modified = JSON.parse(JSON.stringify(raw));
        modified[targetName].status = 'running';
        lastSkillsData = null;
        renderSkillMachines(modified);

        // Verify same DOM element (reconcile = same element)
        var afterEl = document.querySelector('.skill-machine[data-skill="' + targetName + '"]');
        var sameElement = afterEl && afterEl._testMarker === 'reconcile_test_marker';
        var afterStatus = afterEl ? afterEl.dataset.status : 'missing';
        var pixel = afterEl ? afterEl.querySelector('.machine-pixel') : null;
        var hasRunningClass = pixel && pixel.className.indexOf('running') >= 0;

        return {
            targetName: targetName,
            beforeStatus: beforeStatus,
            afterStatus: afterStatus,
            sameElement: sameElement,
            hasRunningClass: hasRunningClass
        };
    }""")

    print(f"  Result: {result}")

    if result.get("error"):
        print(f"  ❌ Error: {result['error']}")
        return False

    same = result.get("sameElement", False)
    status_ok = result.get("afterStatus") == "running"
    class_ok = result.get("hasRunningClass", False)

    if same:
        print(f"  ✅ Same DOM element preserved (reconcile working)")
    else:
        print(f"  ❌ DOM element recreated (reconcile failed)")

    if status_ok:
        print(f"  ✅ Status updated: {result.get('beforeStatus')} → running")
    else:
        print(f"  ❌ Status not applied: {result.get('afterStatus')}")

    if class_ok:
        print(f"  ✅ machine-pixel CSS class applied")
    else:
        print(f"  ❌ machine-pixel CSS class not applied")

    # Restore
    page.evaluate("""() => {
        lastSkillsData = null;
        renderSkillMachines(window._lastSkillsRaw);
    }""")

    return same and status_ok and class_ok


def main():
    print("=" * 60)
    print("🦑 DECO Guard — skill disappearance + agent position fix verification")
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
            ("reconcile_add_remove", test_skill_reconcile_add_remove),
            ("reconcile_status_update", test_skill_status_update_inplace),
        ]

        for name, fn in tests:
            try:
                test_results[name] = fn(page)
            except Exception as e:
                print(f"  ❌ {name} error: {e}")
                import traceback
                traceback.print_exc()
                test_results[name] = False

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
        "screenshots": results,
    }
    result_path = os.path.join(SCREENSHOT_DIR, "guard_results.json")
    with open(result_path, "w") as f:
        json.dump(result_json, f, indent=2, ensure_ascii=False)

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit(main())
