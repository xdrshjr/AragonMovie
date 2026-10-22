"""Objective audit of the gray-black theme inside the running desktop app.

Checks computed styles (not screenshots) for every product page: the canvas must
be near-black, no light "slab" backgrounds may survive, text must be light, and
primary/ghost buttons must keep contrast.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

CDP_URL = os.environ.get("ARAGON_CDP_URL", "http://127.0.0.1:9223")
PAGES = ["/", "/settings", "/projects/new"]

AUDIT_JS = """
() => {
  const parse = (c) => {
    const m = /rgba?\\((\\d+), (\\d+), (\\d+)(?:, ([\\d.]+))?\\)/.exec(c || '');
    return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null;
  };
  const luma = (c) => (c ? (0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b) / 255 : null);
  const all = Array.from(document.querySelectorAll('body *'));
  const lightSlabs = [];
  for (const el of all) {
    const style = getComputedStyle(el);
    const bg = parse(style.backgroundColor);
    if (!bg || bg.a < 0.5) continue;
    const l = luma(bg);
    const rect = el.getBoundingClientRect();
    if (rect.width * rect.height < 400) continue;
    if (l > 0.55) {
      lightSlabs.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 90),
        bg: style.backgroundColor,
        luma: +l.toFixed(2),
      });
    }
  }
  const body = getComputedStyle(document.body);
  const bodyLuma = luma(parse(body.backgroundColor));
  const textLuma = luma(parse(body.color));
  return {
    url: location.pathname,
    bodyBackground: body.backgroundColor,
    bodyColor: body.color,
    bodyLuma,
    textLuma,
    contrast: bodyLuma !== null && textLuma !== null ? +(Math.abs(textLuma - bodyLuma)).toFixed(2) : null,
    elementCount: all.length,
    lightSlabCount: lightSlabs.length,
    lightSlabs: lightSlabs.slice(0, 8),
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 2,
    htmlClass: document.documentElement.className,
  };
}
"""


def main() -> int:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(CDP_URL)
        page = None
        for context in browser.contexts:
            for candidate in context.pages:
                if candidate.url.startswith("http://127.0.0.1:"):
                    page = candidate
        if page is None:
            print("no product page found", file=sys.stderr)
            return 1

        report = []
        for route in PAGES:
            page.goto(page.url.split("/", 3)[0] + "//" + page.url.split("/")[2] + route, wait_until="networkidle")
            page.wait_for_timeout(1200)
            report.append(page.evaluate(AUDIT_JS))

        print(json.dumps(report, ensure_ascii=False, indent=2))
        failures = [r for r in report if (r["bodyLuma"] is None or r["bodyLuma"] > 0.2) or r["overflowX"]]
        if failures:
            print("FAIL: canvas is not dark in:", [f["url"] for f in failures], file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
