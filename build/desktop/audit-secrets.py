#!/usr/bin/env python
"""Credential-leak audit for this repository.

Run it before publishing / after touching docs, config or example files:

    venv\\Scripts\\python.exe build\\desktop\\audit-secrets.py
    venv\\Scripts\\python.exe build\\desktop\\audit-secrets.py --extra-env MY_KEYS

What it checks
--------------
1. every credential value present on this machine (``.env``, runtime
   ``model_settings.json``) against the CURRENT tree and EVERY git ref
2. credential-shaped strings (``sk-*``, ``AKIA*``, ``AIza*``, ``gh*_``,
   ``xox*``, PRIVATE KEY blocks, JWTs) in the tracked tree, in untracked files
   and in the FULL patch history of all refs
3. whether secret-bearing runtime files (``.env``, ``backend/data/``, logs,
   build artefacts, release output) are tracked or ignored
4. placeholder hygiene of ``.env.example``

Exit codes: 0 clean, 1 findings, 2 usage error.
Values are never printed: matches are reported with length + sha256 prefix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()

# Values that are configuration, not credentials.
NON_SECRET_NAMES = re.compile(r"(_URL|_BASE_URL|_ENDPOINT|_MODEL|_VOICE|_FORMAT|_DIR|_PATH|_TYPE)$")
SECRET_NAME = re.compile(r"(API_KEY|_KEY$|TOKEN|SECRET|PASSWORD)")

PATTERNS = {
    "sk-* API key": r"sk-[A-Za-z0-9._-]{24,}",
    "sk-sp-* Ali Token Plan": r"sk-sp-[A-Za-z0-9._-]{20,}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "Google API key": r"AIza[0-9A-Za-z_-]{35}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "Slack token": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "JWT": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
}

# Documentation/test fixtures are reported separately from real leaks.
FIXTURE_HINTS = ("your_", "YOUR_", "example", "placeholder", "dummy", "xxxx", "9999")
INFORMATIONAL_PATHS = ("tests/", "backend/docs/")


def run(args: list[str]) -> str:
    result = subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout


def fp(value: str) -> str:
    return f"{len(value)}ch sha256:{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def collect_needles(extra_env: str | None) -> dict[str, str]:
    needles: dict[str, str] = {}

    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            name = name.strip()
            value = value.strip().strip('"').strip("'")
            if len(value) < 16 or NON_SECRET_NAMES.search(name) or not SECRET_NAME.search(name):
                continue
            if any(hint in value for hint in FIXTURE_HINTS):
                continue
            needles[f".env:{name}"] = value

    settings_file = REPO / "backend" / "data" / "model_settings.json"
    if settings_file.exists():
        try:
            payload = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        stack = list((payload.get("settings") or payload).items())
        while stack:
            key, value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.items())
            elif isinstance(value, str) and "api_key" in str(key) and len(value) >= 16:
                needles[f"model_settings:{key}"] = value

    if extra_env:
        raw = os.environ.get(extra_env, "")
        for index, value in enumerate(raw.splitlines(), 1):
            value = value.strip()
            if len(value) >= 16:
                needles[f"{extra_env}#{index}"] = value

    return needles


def refs() -> list[str]:
    return run(["git", "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes", "refs/tags"]).split()


def needle_in_refs(needle: str) -> list[str]:
    hits = []
    for ref in refs():
        out = run(["git", "grep", "-I", "-l", "-F", needle, ref, "--"])
        if out.strip():
            files = sorted({line.split(":", 1)[-1] for line in out.strip().splitlines()})
            hits.append(f"{ref}: {', '.join(files[:4])}")
    return hits


def needle_in_tree(needle: str) -> list[str]:
    out = run(["git", "grep", "-I", "-n", "-F", needle, "--", "."])
    hits = []
    for line in out.strip().splitlines():
        path, _, rest = line.partition(":")
        lineno, _, _ = rest.partition(":")
        hits.append(f"{path}:{lineno}")
    return hits


def scan_lines(paths_lines: list[str]) -> tuple[list[str], list[str]]:
    real, informational = [], []
    for entry in paths_lines:
        path, _, rest = entry.partition(":")
        lineno, _, content = rest.partition(":")
        if any(hint in content for hint in FIXTURE_HINTS) or path.startswith(INFORMATIONAL_PATHS):
            informational.append(entry)
        else:
            real.append(entry)
    return real, informational


def pattern_hits() -> tuple[list[str], list[str]]:
    real, informational = [], []
    for label, pattern in PATTERNS.items():
        out = run(["git", "grep", "-I", "-E", "-n", "-o", pattern, "--", "."])
        entries = []
        for line in out.strip().splitlines():
            path, _, rest = line.partition(":")
            lineno, _, _match = rest.partition(":")
            if path in (".env.example",) or Path(path).resolve() == SELF:
                continue
            entries.append(f"{path}:{lineno} ({label})")
        group_real, group_info = scan_lines(entries)
        real.extend(group_real)
        informational.extend(group_info)
    return real, informational


def untracked_pattern_hits() -> list[str]:
    out = run(["git", "ls-files", "--others", "--exclude-standard"])
    found = []
    compiled = {label: re.compile(pattern) for label, pattern in PATTERNS.items()}
    for rel in out.splitlines():
        path = REPO / rel
        try:
            if Path(rel).resolve() == SELF or path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, regex in compiled.items():
            for match in regex.finditer(text):
                if any(hint in match.group(0) for hint in FIXTURE_HINTS):
                    continue
                found.append(f"{rel} ({label})")
                break
    return found


def history_pattern_hits() -> list[str]:
    """Credential-shaped strings in the patch of any commit (all refs)."""
    patch = run(["git", "log", "--all", "-p", "--full-history", "--no-color", "-U0"])
    compiled = {label: re.compile(pattern) for label, pattern in PATTERNS.items()}
    findings: list[str] = []
    commit = "?"
    path = "?"
    for line in patch.splitlines():
        if line.startswith("commit ") and len(line.split()) > 1:
            commit, path = line.split()[1][:7], "?"
        elif line.startswith("+++ b/") or line.startswith("--- a/"):
            path = line[6:]
        elif line[:1] in "+-" and not line.startswith(("+++", "---")):
            # "+" = the secret was ADDED by this commit (still in the tree
            # unless a later commit removed it), "-" = it was REMOVED here
            # (a redaction commit, which of course still carries the value in
            # its own patch).
            sign = "added  " if line.startswith("+") else "removed"
            for label, regex in compiled.items():
                for match in regex.finditer(line):
                    if any(hint in match.group(0) for hint in FIXTURE_HINTS):
                        continue
                    entry = f"{commit} {sign} {path} ({label})"
                    if entry not in findings:
                        findings.append(entry)
    return findings


def runtime_file_report() -> list[str]:
    rows = []
    candidates = [
        ".env",
        ".env.local",
        "backend/data/model_settings.json",
        "backend/projects",
        "backend/temp_projects",
        "logs",
        "build/desktop/app/backend/data/model_settings.json",
        "build/desktop/e2e",
        "build/desktop/smoke",
        "build/desktop/python",
        "desktop/release",
        "desktop/node_modules",
    ]
    for path in candidates:
        tracked = bool(run(["git", "ls-files", "--error-unmatch", path]).strip())
        ignored = bool(
            subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO).returncode == 0
        )
        state = "exists" if (REPO / path).exists() else "absent"
        rows.append(f"{path:<50} {state:<7} {'TRACKED' if tracked else 'untracked':<10} {'ignored' if ignored else 'not-ignored'}")
    return rows


def example_hygiene() -> list[str]:
    path = REPO / ".env.example"
    if not path.exists():
        return ["(.env.example missing)"]
    offenders = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if len(value) < 20 or not SECRET_NAME.search(name) or NON_SECRET_NAMES.search(name):
            continue
        if re.search(r"your_|YOUR_|example|placeholder|here|_HERE|xxxx", value, re.IGNORECASE):
            continue
        offenders.append(f".env.example:{lineno} {name.strip()} -> {fp(value)}")
    return offenders


def main() -> int:
    parser = argparse.ArgumentParser(description="audit this repo for credential leaks")
    parser.add_argument("--extra-env", help="env var holding extra secrets to check, newline separated")
    args = parser.parse_args()

    os.chdir(REPO)
    print("=" * 84)
    print(f"repo: {REPO}")
    print(f"commits: {run(['git', 'rev-list', '--all', '--count']).strip()}   refs: {', '.join(r.split('/')[-1] for r in refs())}")
    print("=" * 84)

    findings: list[str] = []

    needles = collect_needles(args.extra_env)
    print(f"\nA. Credential values on this machine ({len(needles)})")
    for label, value in needles.items():
        print(f"   {label:<42} {fp(value)}")

    print("\nB. Those values in the current tree / any ref")
    for label, value in needles.items():
        tree = needle_in_tree(value)
        ref_hits = needle_in_refs(value)
        if tree or ref_hits:
            findings.append(f"credential {label} found in tree/refs")
            print(f"   LEAK  {label}")
            for hit in (tree + ref_hits)[:6]:
                print(f"           {hit}")
        else:
            print(f"   ok    {label}")

    print("\nC. Credential-shaped strings in the tracked tree")
    real, informational = pattern_hits()
    if real:
        findings.extend(real)
        for entry in real:
            print(f"   LEAK  {entry}")
    else:
        print("   ok    none outside fixtures/examples")
    for entry in informational:
        print(f"   note  {entry}")

    print("\nD. Untracked, non-ignored files")
    untracked = untracked_pattern_hits()
    if untracked:
        findings.extend(untracked)
        for entry in untracked:
            print(f"   LEAK  {entry}")
    else:
        print("   ok    none")

    print("\nE. History of all refs (patch scan)")
    history = history_pattern_hits()
    if history:
        for entry in history:
            print(f"   HIST  {entry}")
        findings.extend(f"history {entry}" for entry in history)
    else:
        print("   ok    no credential-shaped string in any commit")

    print("\nF. Secret-bearing runtime files")
    for row in runtime_file_report():
        print(f"   {row}")

    print("\nG. .env.example placeholder hygiene")
    offenders = example_hygiene()
    if offenders:
        findings.extend(offenders)
        for entry in offenders:
            print(f"   LEAK  {entry}")
    else:
        print("   ok    every secret-shaped value is an obvious placeholder")

    print("\n" + "=" * 84)
    if findings:
        print(f"VERDICT: {len(findings)} finding(s) — see LEAK/HIST lines above")
        print("=" * 84)
        return 1
    print("VERDICT: clean — no credential leak in tree, refs, history or examples")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
