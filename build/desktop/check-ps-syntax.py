"""Parse-check every PowerShell file in this repo (no execution)."""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FILES = sorted(
    {
        *REPO.glob("*.ps1"),
        *REPO.glob("**/*.ps1"),
    }
)
FILES = [p for p in FILES if "node_modules" not in p.parts and "venv" not in p.parts]

failures = 0
for path in FILES:
    script = (
        "$errs = $null; "
        "$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{path}', [ref]$null, [ref]$errs); "
        "if ($errs) { $errs | ForEach-Object { $_.Message }; exit 1 } else { exit 0 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    rel = path.relative_to(REPO)
    if result.returncode == 0:
        print(f"  ok    {rel}")
    else:
        failures += 1
        print(f"  ERROR {rel}")
        for line in (result.stdout + result.stderr).strip().splitlines()[:6]:
            print(f"        {line}")

print("\nRESULT:", "FAIL" if failures else f"{len(FILES)} scripts parse cleanly")
sys.exit(1 if failures else 0)
