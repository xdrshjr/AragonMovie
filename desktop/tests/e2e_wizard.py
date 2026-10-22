"""End-to-end verification of the AragonMovie desktop shell.

Drives the real Electron app over the Chrome DevTools Protocol (Playwright
attaches to the already running app — nothing is mocked):

  first-run : onboarding wizard -> live connection test -> finish -> product UI
  relaunch  : proves a configured machine boots straight into the product UI

Usage (the app must already be running with --remote-debugging-port=9222):

    venv\\Scripts\\python.exe desktop\\tests\\e2e_wizard.py first-run
    venv\\Scripts\\python.exe desktop\\tests\\e2e_wizard.py relaunch
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
CDP_URL = os.environ.get("ARAGON_CDP_URL", "http://127.0.0.1:9222")


def load_api_key() -> str:
    """Read the Ali Token Plan key from the repo .env (never printed)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        raise SystemExit("repo .env not found — cannot run the live connection test")
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() in {"FAST_LLM_API_KEY", "ALI_TOKEN_PLAN_API_KEY"}:
            value = value.strip().strip('"').strip("'")
            if value and "YOUR_" not in value and len(value) > 12:
                return value
    raise SystemExit("no usable FAST_LLM_API_KEY in .env")


def connect(playwright, timeout_s: int = 90):
    deadline = time.time() + timeout_s
    last_error = None
    while time.time() < deadline:
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            return browser
        except Exception as exc:  # noqa: BLE001 - retry until the app is up
            last_error = exc
            time.sleep(1.5)
    raise SystemExit(f"cannot attach to Electron over CDP: {last_error}")


def cdp_targets():
    """Raw /json/list — Playwright does not always attach to windows that are
    created after connect_over_cdp, so new windows are detected here first."""
    with urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_target(match, timeout_s=180, label="window"):
    """Poll /json/list until a page target URL satisfies `match`."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            for target in cdp_targets():
                url = target.get("url", "")
                if target.get("type") == "page" and match(url):
                    return url
        except Exception:  # noqa: BLE001 - app may still be booting
            pass
        time.sleep(1)
    raise SystemExit(f"timed out waiting for {label}")


def wait_for_web_target(timeout_s=180):
    return wait_for_target(
        lambda url: url.startswith("http://127.0.0.1:") and "setup.html" not in url,
        timeout_s=timeout_s,
        label="the product window",
    )


def attach_page(playwright, url_substring: str, timeout_s=60):
    """Fresh CDP connection + page lookup by URL fragment."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_URL)
            for page in pages(browser):
                if url_substring in page.url:
                    return browser, page
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1)
    raise SystemExit(f"cannot attach to page containing {url_substring!r}")


def pages(browser):
    found = []
    for context in browser.contexts:
        found.extend(context.pages)
    return found


def wait_for_page(browser, predicate, timeout_s=120, label="page"):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for page in pages(browser):
            try:
                if predicate(page):
                    return page
            except Exception:  # noqa: BLE001 - page may be navigating
                continue
        time.sleep(0.5)
    raise SystemExit(f"timed out waiting for {label}")


def shot(page, name: str):
    """Capture through Electron — CDP screenshots hang on headless VMs."""
    target = "wizard" if "setup.html" in page.url else "main"
    try:
        result = page.evaluate(
            "([t, n]) => (window.aragonShell ? window.aragonShell.capture(t, n) : null)",
            [target, name],
        )
        if result and result.get("ok"):
            return result["file"]
    except Exception:  # noqa: BLE001 - fall back to a plain CDP screenshot
        pass
    try:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS / f"{name}.png"
        page.screenshot(path=str(path), timeout=8000)
        return str(path)
    except Exception:  # noqa: BLE001
        return None


def click(page, selector: str, timeout=30_000):
    page.wait_for_selector(selector, state="visible", timeout=timeout)
    page.click(selector)


def wait_results(page, minimum=1, timeout=180_000):
    page.wait_for_function(
        "n => document.querySelectorAll('.result').length >= n", arg=minimum, timeout=timeout
    )
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.result')).map(el => ({
            ok: el.classList.contains('ok'),
            target: (el.querySelector('.result-target')||{}).textContent,
            message: (el.querySelector('.result-msg')||{}).textContent,
            latency: (el.querySelector('.result-meta')||{}).textContent,
        }))"""
    )


def fill_secret(page, selector: str, value: str):
    page.evaluate(
        """([sel, val]) => {
            const input = document.querySelector(sel);
            if (!input) throw new Error('input not found: ' + sel);
            input.value = val;
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }""",
        [selector, value],
    )


def body_text(page) -> str:
    return page.evaluate("() => document.body.innerText")


def run_first_run(playwright, browser) -> dict:
    report: dict = {"steps": []}

    wait_for_target(lambda url: "setup.html" in url, label="setup wizard")
    browser, wizard = attach_page(playwright, "setup.html")
    wizard.wait_for_selector(".nav-item", timeout=60_000)
    report["wizard_url"] = wizard.url
    report["screenshots"] = [shot(wizard, "01-setup-text")]

    # ---- step 1: LLM (live connection test with a real key) -----------------
    click(wizard, '[data-preset="ali-token-plan"]')
    fill_secret(wizard, 'input[data-path="fast_llm.api_key"]', load_api_key())
    click(wizard, "#btn-test")
    results = wait_results(wizard, minimum=2)
    report["steps"].append({"step": "text", "results": results})
    report["screenshots"].append(shot(wizard, "02-setup-text-tested"))
    if not any(r["ok"] for r in results):
        raise SystemExit(f"LLM connection test failed: {json.dumps(results, ensure_ascii=False)}")

    # ---- step 2/3: image + video (key mirrored from the Ali plan) -----------
    for step, minimum in (("image", 1), ("video", 1)):
        click(wizard, f'[data-step="{step}"]')
        wizard.wait_for_timeout(400)
        click(wizard, "#btn-test")
        results = wait_results(wizard, minimum=minimum)
        report["steps"].append({"step": step, "results": results})
        report["screenshots"].append(shot(wizard, f"03-setup-{step}-tested"))
        if not all(r["ok"] for r in results):
            raise SystemExit(f"{step} connection test failed: {json.dumps(results, ensure_ascii=False)}")

    # ---- step 4: voice is optional -> skip to the summary ------------------
    click(wizard, '[data-step="voice"]')
    wizard.wait_for_timeout(400)
    report["screenshots"].append(shot(wizard, "04-setup-voice"))
    voice_enabled = wizard.evaluate(
        """() => {
            const el = document.querySelector('.switch[data-toggle="enabled"]');
            return el ? el.getAttribute('aria-checked') === 'true' : false;
        }"""
    )
    report["voice_enabled_on_entry"] = voice_enabled
    if voice_enabled:
        # Voice is optional; leaving it on without a key would block onboarding.
        click(wizard, '.switch[data-toggle="enabled"]')
        wizard.wait_for_timeout(400)
        report["screenshots"].append(shot(wizard, "04b-setup-voice-disabled"))
    click(wizard, "#btn-next")
    wizard.wait_for_timeout(600)

    finish_text = body_text(wizard)
    report["finish_summary_ready"] = "进入工作台" in finish_text
    report["screenshots"].append(shot(wizard, "05-setup-finish"))

    next_disabled = wizard.evaluate("() => document.getElementById('btn-next').disabled")
    report["finish_next_disabled"] = next_disabled
    if next_disabled:
        raise SystemExit("finish step is not ready — required credentials missing")

    click(wizard, "#btn-next")

    # The product window is created after our CDP session attached; detect it
    # through /json/list, then re-attach to it.
    product_url = wait_for_web_target()
    browser, main_page = attach_page(playwright, product_url.replace("http://127.0.0.1:", "127.0.0.1:"))
    main_page.wait_for_timeout(3000)
    main_page.wait_for_load_state("networkidle", timeout=60_000)
    report["main_url"] = main_page.url
    report["main_title"] = main_page.title()
    report["screenshots"].append(shot(main_page, "06-product-home"))

    # The product UI must actually reach the backend through the injected base.
    api_probe = main_page.evaluate(
        """async () => {
            const base = window.aragonDesktop && window.aragonDesktop.apiBase;
            if (!base) return { ok: false, reason: 'no apiBase injected' };
            const res = await fetch(base + '/health');
            const settings = await fetch(base + '/api/v1/settings');
            return { ok: res.ok && settings.ok, base, status: res.status, settingsStatus: settings.status };
        }"""
    )
    report["api_probe"] = api_probe
    if not api_probe.get("ok"):
        raise SystemExit(f"product UI cannot reach the backend: {api_probe}")

    report["main_theme"] = main_page.evaluate(
        """() => {
            const body = getComputedStyle(document.body);
            const html = getComputedStyle(document.documentElement);
            const heading = document.querySelector('h1, h2');
            return {
                htmlClass: document.documentElement.className,
                colorScheme: html.colorScheme,
                background: body.backgroundColor,
                color: body.color,
                headingColor: heading ? getComputedStyle(heading).color : null,
                cardCount: document.querySelectorAll('[class*="rounded"]').length,
                hasHorizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 2,
            };
        }"""
    )

    return report


def run_relaunch(playwright) -> dict:
    product_url = wait_for_web_target()
    browser, main_page = attach_page(playwright, product_url.replace("http://127.0.0.1:", "127.0.0.1:"))
    wizard_present = any("setup.html" in p.url for p in pages(browser))
    main_page.wait_for_timeout(3000)
    main_page.wait_for_load_state("networkidle", timeout=60_000)
    shot(main_page, "07-relaunch-product-home")
    return {
        "wizard_present": wizard_present,
        "main_url": main_page.url,
        "main_title": main_page.title(),
        "pages": [p.url for p in pages(browser)],
        "main_theme": main_page.evaluate(
            """() => ({
                htmlClass: document.documentElement.className,
                background: getComputedStyle(document.body).backgroundColor,
                color: getComputedStyle(document.body).color,
            })"""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["first-run", "relaunch"])
    args = parser.parse_args()

    with sync_playwright() as playwright:
        report = run_first_run(playwright, connect(playwright)) if args.mode == "first-run" else run_relaunch(playwright)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.mode == "relaunch" and report.get("wizard_present"):
        print("FAIL: wizard appeared on a configured machine", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
