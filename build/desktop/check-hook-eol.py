"""Confirm the committed hook template is stored with LF endings (CRLF would
break the shebang on a fresh clone with core.autocrlf=true)."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGETS = [
    "build/desktop/git-hooks/pre-commit",
    "build/desktop/install-git-hooks.ps1",
    ".gitattributes",
]

bad = 0
for rel in TARGETS:
    blob = subprocess.run(
        ["git", "cat-file", "-p", f"HEAD:{rel}"], cwd=REPO, capture_output=True
    ).stdout
    crlf = blob.count(b"\r\n")
    bare_cr = blob.count(b"\r") - crlf
    lf = blob.count(b"\n")
    verdict = "LF" if crlf == 0 else "CRLF!"
    if rel.endswith("pre-commit") and crlf:
        bad += 1
    print(f"  {rel:<40} {len(blob):>6} bytes  LF={lf:<4} CRLF={crlf:<3} bare CR={bare_cr}  -> {verdict}")

    if rel.endswith("pre-commit"):
        first = blob.split(b"\n", 1)[0]
        print(f"       shebang: {first!r}")

print("\nRESULT:", "FAIL - template would break on a CRLF checkout" if bad else "PASS - template is stored LF")
raise SystemExit(1 if bad else 0)
