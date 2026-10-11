"""Tests for the OpenAI-compatible TTS service client."""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.tts_service import TTSService, TTSError  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content
        self.text = ""


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def post(self, url, json=None):
        self.calls.append((url, json))
        return self._response

    async def aclose(self):
        pass


@pytest.fixture()
def service(monkeypatch):
    s = TTSService(api_key="sk-tts", base_url="https://tts.example.com/v1",
                   model="tts-1", default_voice="alloy")
    yield s
    try:
        import asyncio
        asyncio.get_event_loop()
    except RuntimeError:
        pass


def test_bytes_success(service, monkeypatch):
    fake = _FakeClient(_FakeResponse(200, b"FAKE_MP3_BYTES"))
    monkeypatch.setattr(service, "client", fake)

    import asyncio
    audio = asyncio.run(service.text_to_speech_bytes("你好世界"))
    assert audio == b"FAKE_MP3_BYTES"
    url, payload = fake.calls[0]
    assert url == "/audio/speech"
    assert payload["model"] == "tts-1"
    assert payload["voice"] == "alloy"
    assert payload["input"] == "你好世界"


def test_http_error_wrapped(service, monkeypatch):
    fake = _FakeClient(_FakeResponse(401))
    monkeypatch.setattr(service, "client", fake)

    import asyncio
    with pytest.raises(TTSError):
        asyncio.run(service.text_to_speech_bytes("hello"))


def test_empty_text_rejected(service):
    import asyncio
    with pytest.raises(TTSError):
        asyncio.run(service.text_to_speech_bytes("   "))


def test_file_output(service, monkeypatch, tmp_path):
    fake = _FakeClient(_FakeResponse(200, b"AUDIO"))
    monkeypatch.setattr(service, "client", fake)

    import asyncio
    out = tmp_path / "sub" / "out.mp3"
    asyncio.run(service.text_to_speech("保存到文件", out))
    assert out.read_bytes() == b"AUDIO"
