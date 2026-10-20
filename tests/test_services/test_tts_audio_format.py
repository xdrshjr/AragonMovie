"""Review regression: audio container honesty + safe element ids.

The DashScope native route ignores ``response_format``, so labelling its bytes
with the requested format produced files/HTTP responses whose extension or
Content-Type contradicted the content.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.tts_service import TTSService, sniff_audio_format  # noqa: E402

MP3 = b"ID3\x03\x00\x00\x00" + b"\x00" * 32
WAV = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVEfmt " + b"\x00" * 16
OGG = b"OggS" + b"\x00" * 24
FLAC = b"fLaC" + b"\x00" * 24


class TestSniffAudioFormat:
    @pytest.mark.parametrize(
        "data,expected",
        [(MP3, "mp3"), (WAV, "wav"), (OGG, "opus"), (FLAC, "flac"), (b"", None)],
    )
    def test_magic_bytes(self, data, expected):
        assert sniff_audio_format(data) == expected

    def test_mp3_frame_sync_without_id3(self):
        assert sniff_audio_format(b"\xff\xfb\x90\x00") == "mp3"

    def test_unknown_returns_none(self):
        assert sniff_audio_format(b"not audio at all") is None


class TestFileExtensionFollowsContent:
    @pytest.mark.asyncio
    async def test_wav_bytes_for_mp3_path_is_renamed(self, tmp_path):
        service = TTSService(
            api_key="sk-native",
            base_url="https://dashscope.aliyuncs.com",
            provider="dashscope_native",
            native_api_key="sk-native",
            native_model="qwen-tts",
        )
        try:
            async def fake_bytes(*a, **kw):
                return WAV

            service.text_to_speech_bytes = fake_bytes  # type: ignore[assignment]

            written = await service.text_to_speech("你好", tmp_path / "scene_001.mp3")

            assert written.suffix == ".wav"
            assert written.read_bytes() == WAV
            assert not (tmp_path / "scene_001.mp3").exists()
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_matching_container_is_left_alone(self, tmp_path):
        service = TTSService(
            api_key="sk", base_url="https://api.openai.com/v1",
            provider="openai_compatible",
        )
        try:
            async def fake_bytes(*a, **kw):
                return MP3

            service.text_to_speech_bytes = fake_bytes  # type: ignore[assignment]
            written = await service.text_to_speech("hi", tmp_path / "out.mp3")
            assert written.name == "out.mp3"
        finally:
            await service.close()
