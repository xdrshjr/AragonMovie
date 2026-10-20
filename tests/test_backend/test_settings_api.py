"""Tests for the Settings REST API (GET/PUT/test/agent-status/chat)."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.core.settings_store import (  # noqa: E402
    ModelSettingsStore,
    get_settings_store,
    FIELD_MAP,
)


@pytest.fixture()
def client(tmp_path):
    from backend.main import app

    # Point the global store at a temp file for isolation
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


class TestSettingsCrud:
    def test_get_returns_masked_keys(self, client):
        client.put("/api/v1/settings", json={
            "agent": {"api_key": "sk-agent-test-key-1234"}
        })
        r = client.get("/api/v1/settings")
        assert r.status_code == 200
        data = r.json()
        assert data["settings"]["agent"]["api_key"] == "sk-a****1234"
        assert "test-key" not in json.dumps(data)

    def test_put_updates_and_persists(self, client):
        r = client.put("/api/v1/settings", json={
            "video": {"service_type": "sora2", "sora2": {"model": "sora-2-pro"}}
        })
        assert r.status_code == 200
        assert r.json()["settings"]["video"]["sora2"]["model"] == "sora-2-pro"

        r2 = client.get("/api/v1/settings")
        assert r2.json()["settings"]["video"]["service_type"] == "sora2"

    def test_put_write_only_key_semantics(self, client):
        client.put("/api/v1/settings", json={
            "text": {"fast_llm": {"api_key": "sk-keep-me-123456"}}
        })
        # api_key absent -> key kept, model updated
        r = client.put("/api/v1/settings", json={
            "text": {"fast_llm": {"model": "qwen-max"}}
        })
        body = r.json()["settings"]["text"]["fast_llm"]
        assert body["model"] == "qwen-max"
        assert body["api_key"] == "sk-k****3456"

    def test_put_invalid_category_value_returns_400(self, client):
        r = client.put("/api/v1/settings", json={
            "agent": {"provider": "bogus"}
        })
        assert r.status_code == 422  # pydantic validation on request model


class TestConnectionTests:
    def test_unknown_category_404(self, client):
        r = client.post("/api/v1/settings/test/nope")
        assert r.status_code == 404

    def test_text_reports_missing_key(self, client):
        # The probe reads the effective (store-backed) settings, and a developer
        # .env may well carry real keys - so clear them through the API first
        # ("" clears a write-only key) to make the scenario deterministic.
        clear = client.put("/api/v1/settings", json={
            "text": {
                "fast_llm": {"api_key": ""},
                "judge_llm": {"api_key": ""},
            }
        })
        assert clear.status_code == 200

        r = client.post("/api/v1/settings/test/text")
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 2
        for item in results:
            assert item["success"] is False
            assert "API Key" in item["message"]

    def test_agent_reports_missing_config(self, client):
        r = client.post("/api/v1/settings/test/agent")
        assert r.status_code == 200
        assert r.json()[0]["success"] is False

    def test_video_skips_unconfigured_alternatives(self, client):
        # Force a deterministic selection: veo3 without a key is the selected
        # provider; sora2/ali_token_plan alternatives are skipped only when
        # they have no key either (env may provide one for ali_token_plan).
        client.put("/api/v1/settings", json={
            "video": {
                "service_type": "veo3",
                "veo3": {"api_key": ""},
                "sora2": {"api_key": ""},
                "ali_token_plan": {"api_key": ""},
            }
        })
        r = client.post("/api/v1/settings/test/video")
        assert r.status_code == 200
        targets = {item["target"] for item in r.json()}
        assert targets == {"veo3"}  # selected provider only; unkeyed alternatives skipped


class TestAgentEndpoints:
    def test_agent_status_shape(self, client):
        r = client.get("/api/v1/settings/agent/status")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] in ("aragon", "llm_fallback", "unavailable")
        assert isinstance(body["aragon_installed"], bool)
        assert isinstance(body["agent_configured"], bool)
        assert body["message"]

    def test_agent_chat_without_config_yields_error_event(self, client):
        r = client.post("/api/v1/settings/agent/chat", json={"message": "hi"})
        assert r.status_code == 200
        assert r.text.startswith("data: ")
        events = [
            json.loads(line[len("data: "):])
            for line in r.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        types = [e["type"] for e in events]
        assert "meta" in types
        assert "error" in types
        assert r.text.strip().endswith("data: [DONE]")
