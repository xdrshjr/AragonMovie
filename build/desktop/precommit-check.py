"""Pre-commit gate: the staged blob must not contain any known credential.

Reads the staged tree (``git diff --cached``), never prints values.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def staged_diff() -> str:
    return subprocess.run(
        ["git", "diff", "--cached"], cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout


def local_secrets() -> list[tuple[str, str]]:
    secrets: list[tuple[str, str]] = []
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            name, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if len(value) >= 16 and re.search(r"API_KEY|TOKEN|SECRET", name):
                secrets.append((name.strip(), value))
    settings = REPO / "backend" / "data" / "model_settings.json"
    if settings.exists():
        payload = json.loads(settings.read_text(encoding="utf-8"))
        stack = list((payload.get("settings") or payload).items())
        while stack:
            key, value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.items())
            elif isinstance(value, str) and "api_key" in str(key) and len(value) >= 16:
                secrets.append((str(key), value))
    extra = os.environ.get("AUDIT_EXTRA_SECRETS", "")
    for index, value in enumerate(extra.splitlines(), 1):
        if len(value.strip()) >= 16:
            secrets.append((f"env#{index}", value.strip()))
    return secrets


def main() -> int:
    diff = staged_diff()
    print(f"staged diff: {len(diff) / 1024:.1f} KB")

    problems = 0
    for name, value in local_secrets():
        fingerprint = hashlib.sha256(value.encode()).hexdigest()[:12]
        if value in diff:
            problems += 1
            print(f"  BLOCKED {name} ({len(value)}ch sha256:{fingerprint}) appears in the staged diff")
        else:
            print(f"  ok      {name} ({len(value)}ch sha256:{fingerprint}) not staged")

    # generic shapes, ignoring placeholder-looking values and the audit tool itself
    patterns = {
        "sk-*": r"sk-[A-Za-z0-9._-]{24,}",
        "dashboard token": r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{28,}",
    }
    placeholder = re.compile(r"your|example|placeholder|here|dummy|xxxx|asdasd|9999", re.IGNORECASE)
    for label, pattern in patterns.items():
        hits = []
        for line in diff.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            if "audit-secrets.py" in line:
                continue
            for match in re.finditer(pattern, line):
                if not placeholder.search(match.group(0)):
                    hits.append(match.group(0))
        if hits:
            problems += 1
            print(f"  BLOCKED {label}: {len(hits)} credential-shaped addition(s) "
                  f"(lengths {sorted({len(h) for h in hits})})")
        else:
            print(f"  ok      {label}: no credential-shaped addition")

    print("\nRESULT:", "STOP - do not commit" if problems else "safe to commit")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
