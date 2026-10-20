"""BUG 12 regression: .env.example must not contain credential-shaped values.

``DOUBAO_API_KEY=0fe6efc8-43fb-49be-a358-bdaasdasd`` and
``NANO_BANANA_API_KEY=sk-Zb5pnfIb...asdasd`` looked like real keys (tail-masked
by hand). That invites people to think a working default exists and risks the
value being reused or committed elsewhere.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Every secret-looking key must use an explicit placeholder.
PLACEHOLDER_HINTS = ("your_", "_here", "YOUR_", "-placeholder", "changeme")


def _assignments() -> dict:
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


@pytest.fixture(scope="module")
def values() -> dict:
    return _assignments()


def test_no_hand_masked_credentials(values):
    """The previously committed fake tails must be gone."""
    blob = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "asdasd" not in blob
    assert "0fe6efc8-43fb-49be-a358" not in blob
    assert "Zb5pnfIbQJQzRXjSJ1gR1rXsqVb6yvEG3rBy" not in blob


def test_secret_keys_use_placeholders(values):
    """Anything that looks like a secret must be an obvious placeholder."""
    non_secret_suffixes = ("_URL", "_BASE_URL", "_ENDPOINT", "_MODEL", "_TYPE", "_VOICE")

    offenders = {}
    for key, value in values.items():
        if not value or key.endswith(non_secret_suffixes):
            continue
        looks_secret = (
            key.endswith("API_KEY")
            or key.endswith("_KEY")
            or key.endswith("_SECRET")
            or key.endswith("_TOKEN")
        )
        if not looks_secret:
            continue
        if any(hint in value for hint in PLACEHOLDER_HINTS):
            continue
        offenders[key] = value

    assert not offenders, (
        "these .env.example keys hold credential-shaped values instead of "
        f"placeholders: {offenders}"
    )


def test_specific_keys_are_explicit_placeholders(values):
    assert values["DOUBAO_API_KEY"].startswith("your_")
    assert values["NANO_BANANA_API_KEY"].startswith("your_")


def test_no_key_looks_like_a_real_token(values):
    """No 30+ char high-entropy blob (sk-…, uuid-ish) anywhere in the file."""
    suspicious = re.compile(r"^(sk-[A-Za-z0-9._-]{16,}|[0-9a-f]{8}-[0-9a-f]{4}-)")
    offenders = {
        key: value
        for key, value in values.items()
        if suspicious.match(value) and not any(h in value for h in PLACEHOLDER_HINTS)
    }
    assert not offenders, f"credential-shaped values found: {offenders}"
