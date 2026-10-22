"""Verify the packaged desktop wizard exposes the new Volcano providers.

Attaches to the running packaged app over CDP and asserts that
  - the video step lists 豆包 Seedance
  - the voice step lists 火山 TTS 2.0 and renders the volc_* fields
  - a screenshot of both steps exists (via the app's own capture bridge)
"""

import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

CDP = os.environ.get("ARAGON_CDP_URL", "http://127.0.0.1:9223")


def targets():
    with urllib.request.urlopen(f"{CDP}/json/list", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    deadline = time.time() + 120
    url = None
    while time.time() < deadline:
        try:
            for target in targets():
                if target.get("type") == "page" and "setup.html" in target.get("url", ""):
                    url = target["url"]
        except Exception:  # noqa: BLE001
            pass
        if url:
            break
        time.sleep(1)
    if not url:
        print("wizard not found", file=sys.stderr)
        return 1

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP)
        page = None
        for context in browser.contexts:
            for candidate in context.pages:
                if "setup.html" in candidate.url:
                    page = candidate
        if page is None:
            print("cannot attach to the wizard page", file=sys.stderr)
            return 1
        page.wait_for_selector(".nav-item", timeout=60_000)
        page.set_viewport_size({"width": 1120, "height": 780})

        # ---- video step ----------------------------------------------------
        page.click('[data-step="video"]')
        page.wait_for_timeout(800)
        segments = page.eval_on_selector_all(
            "[data-seg]", "els => els.map(e => e.textContent.trim())"
        )
        video_fields = page.eval_on_selector_all(
            "#step-body [data-path]", "els => els.map(e => e.dataset.path)"
        )
        page.evaluate("() => window.aragonShell.capture('wizard', 'packaged-video-providers')")
        # open the doubao provider and screenshot its fields
        page.click('[data-seg="video"][data-value="doubao"]')
        page.wait_for_timeout(600)
        doubao_fields = page.eval_on_selector_all(
            "#step-body [data-path]", "els => els.map(e => e.dataset.path)"
        )
        page.evaluate("() => window.aragonShell.capture('wizard', 'packaged-doubao-video')")

        # ---- voice step ----------------------------------------------------
        page.click('[data-step="voice"]')
        page.wait_for_timeout(800)
        voice_segments = page.eval_on_selector_all(
            "[data-seg]", "els => els.map(e => e.textContent.trim())"
        )
        page.click('[data-seg="voice"][data-value="volc_tts2"]')
        page.wait_for_timeout(700)
        voice_fields = page.eval_on_selector_all(
            "#step-body [data-path]", "els => els.map(e => e.dataset.path)"
        )
        page.evaluate("() => window.aragonShell.capture('wizard', 'packaged-volc-voice')")

    report = {
        "video_segments": segments,
        "video_fields": video_fields,
        "doubao_fields": doubao_fields,
        "voice_segments": voice_segments,
        "voice_fields": voice_fields,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    problems = []
    if not any("豆包" in s or "Seedance" in s for s in segments):
        problems.append("豆包 Seedance missing from the video provider list")
    if "doubao.api_key" not in doubao_fields:
        problems.append("doubao.api_key field not rendered")
    if not any("火山" in s for s in voice_segments):
        problems.append("火山 TTS 2.0 missing from the voice transport list")
    if "volc_api_key" not in voice_fields:
        problems.append("volc_api_key field not rendered")

    print("\nVERDICT:", "PASS" if not problems else "FAIL")
    for problem in problems:
        print("  -", problem)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
