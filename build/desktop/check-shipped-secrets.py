"""Assert the shipped app bundles contain no credential files."""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECRET_NAMES = {".env", ".env.local", "model_settings.json", "desktop-state.json"}
ROOTS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "AragonMovie" / "resources",
    REPO / "build" / "desktop" / "app",
    REPO / "build" / "desktop" / "web",
    REPO / "desktop" / "release" / "win-unpacked" / "resources",
]

failures = 0
for root in ROOTS:
    print(f"== {root}")
    if not root.exists():
        print("   (missing, skipped)")
        continue
    hits = [p for p in root.rglob("*") if p.is_file() and p.name in SECRET_NAMES]
    if hits:
        failures += len(hits)
        for path in hits:
            print(f"   SHIPPED {path.relative_to(root)}")
    else:
        print("   ok: no .env / model_settings.json / desktop-state.json")

    # Also make sure no obvious key material sits in a shipped text config.
    suspicious = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".yaml", ".yml", ".env", ".txt"}:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if '"api_key": "sk-' in text or "API_KEY=sk-" in text:
            suspicious += 1
            print(f"   SUSPECT {path.relative_to(root)}")
    if suspicious:
        failures += suspicious
    else:
        print("   ok: no api_key value shipped in text config")

print("\nRESULT:", "FAIL" if failures else "PASS - installer carries no credentials")
sys.exit(1 if failures else 0)
