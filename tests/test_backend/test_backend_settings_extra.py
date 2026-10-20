"""BUG 4 regression: `BackendSettings` must ignore CLI-only keys from the shared `.env`.

`config/settings.py` (CLI) and `backend/config.py` (FastAPI backend) read the same
`.env` file but declare different subsets of keys. pydantic-settings defaults to
``extra="forbid"`` **for values coming from the dotenv file**, so a key that only
exists in the CLI ``Settings`` (for example ``CANDIDATE_IMAGES_PER_SCENE``) aborted
backend startup with ``ValidationError: ... Extra inputs are not permitted``.

Note: the failure is specific to the ``.env`` file source — stray ``os.environ``
entries are filtered by field name — so the tests below build a real env file.
"""

from pathlib import Path

import pytest

from backend.config import BackendSettings
from config.settings import Settings

CLI_ONLY_KEYS = """\
IMAGE_SERVICE_TYPE=ali_token_plan
CANDIDATE_IMAGES_PER_SCENE=3
JUDGE_TEMPERATURE=0.3
ENABLE_SCENE_CONTINUITY=true
MAX_REFERENCE_IMAGES=4
"""

BACKEND_ONLY_KEYS = """\
IMAGE_SERVICE_TYPE=doubao
TASK_STORAGE_BACKEND=memory
API_TITLE=AI Movie Agent API
"""


def _env_file(tmp_path: Path, content: str) -> str:
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_backend_settings_ignores_cli_only_keys_from_env_file(tmp_path, monkeypatch):
    """The CLI-only keys used to abort backend startup."""
    monkeypatch.delenv("IMAGE_SERVICE_TYPE", raising=False)
    env = _env_file(tmp_path, CLI_ONLY_KEYS)

    settings = BackendSettings(_env_file=env)

    # Shared keys are still honoured ...
    assert settings.image_service_type == "ali_token_plan"
    # ... while unknown ones are ignored instead of raising
    assert not hasattr(settings, "candidate_images_per_scene")
    assert not hasattr(settings, "judge_temperature")


def test_backend_settings_still_reads_shared_keys(tmp_path, monkeypatch):
    """Sanity check: real env vars keep working alongside the env file."""
    monkeypatch.setenv("VIDEO_SERVICE_TYPE", "veo3")
    env = _env_file(tmp_path, CLI_ONLY_KEYS)

    settings = BackendSettings(_env_file=env)

    assert settings.video_service_type == "veo3"


def test_root_settings_ignores_backend_only_keys_from_env_file(tmp_path, monkeypatch):
    """The reverse direction (CLI Settings reading backend keys) keeps working."""
    # Real env vars outrank the env file: clear the ones this machine exports so
    # the file value is the one under test.
    monkeypatch.delenv("IMAGE_SERVICE_TYPE", raising=False)
    env = _env_file(tmp_path, BACKEND_ONLY_KEYS)

    settings = Settings(_env_file=env)

    assert settings.image_service_type == "doubao"
    assert not hasattr(settings, "task_storage_backend")


def test_extra_is_ignored_for_both_settings_models():
    """Guard the configured policy itself, not just one construction path."""
    assert BackendSettings.model_config.get("extra") == "ignore"
    assert Settings.model_config.get("extra") == "ignore"


@pytest.mark.parametrize("key", ["CANDIDATE_IMAGES_PER_SCENE", "JUDGE_TEMPERATURE"])
def test_each_cli_only_key_is_accepted(tmp_path, key):
    env = _env_file(tmp_path, f"{key}=1\n")

    BackendSettings(_env_file=env)  # must not raise
