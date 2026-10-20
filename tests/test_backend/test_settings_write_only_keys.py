"""Review regression: nested ``*_api_key`` fields must stay write-only.

`_merge_category` only protected a field literally named ``api_key``. The new
``voice.native_api_key`` therefore got overwritten with ``None`` by any PUT that
omitted it - silently destroying the stored DashScope key.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.core.settings_store import FIELD_MAP, get_settings_store  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    from backend.main import app

    store = get_settings_store()
    original_path = store.file_path
    store.file_path = tmp_path / "model_settings.json"
    store._current = None
    store._file_hash = None

    from backend.config import settings as backend_settings
    from config.settings import settings as root_settings

    snapshot = {attr: getattr(backend_settings, attr) for _, attr in FIELD_MAP}
    snapshot_root = {attr: getattr(root_settings, attr) for _, attr in FIELD_MAP}

    with TestClient(app) as c:
        yield c

    for attr, value in snapshot.items():
        setattr(backend_settings, attr, value)
    for attr, value in snapshot_root.items():
        setattr(root_settings, attr, value)
    store.file_path = original_path
    store._current = None
    store._file_hash = None


def _set_native_key(client) -> None:
    r = client.put("/api/v1/settings", json={
        "voice": {"provider": "dashscope_native", "native_api_key": "sk-dashscope-abcdef"}
    })
    assert r.status_code == 200


class TestWriteOnlyNestedKeys:
    def test_omitted_native_key_is_preserved(self, client):
        _set_native_key(client)

        # Unrelated voice update that does NOT mention native_api_key
        r = client.put("/api/v1/settings", json={"voice": {"default_voice": "longxiaochun"}})
        assert r.status_code == 200
        assert r.json()["settings"]["voice"]["default_voice"] == "longxiaochun"

        from backend.config import settings as backend_settings
        assert backend_settings.tts_native_api_key == "sk-dashscope-abcdef"

    def test_masked_echo_does_not_overwrite_key(self, client):
        _set_native_key(client)
        masked = client.get("/api/v1/settings").json()["settings"]["voice"]["native_api_key"]

        r = client.put("/api/v1/settings", json={"voice": {"native_api_key": masked}})
        assert r.status_code == 200

        from backend.config import settings as backend_settings
        assert backend_settings.tts_native_api_key == "sk-dashscope-abcdef"

    def test_empty_string_clears_native_key(self, client):
        _set_native_key(client)

        r = client.put("/api/v1/settings", json={"voice": {"native_api_key": ""}})
        assert r.status_code == 200

        from backend.config import settings as backend_settings
        assert backend_settings.tts_native_api_key in ("", None)
