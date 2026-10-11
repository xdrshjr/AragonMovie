"""TTS (voice synthesis) API endpoints (REST v1)

Provides a text-to-speech generation endpoint backed by the runtime
configurable TTS service (OpenAI-compatible /audio/speech).
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from typing import Optional

from pydantic import BaseModel, Field

from backend.config import settings
from backend.core.exceptions import ServiceException
from backend.utils.logger import get_logger

import sys
from pathlib import Path

# Add parent directory to path to import existing services
parent_dir = Path(__file__).parent.parent.parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from services.tts_service import TTSService, TTSError  # noqa: E402

logger = get_logger(__name__)
router = APIRouter()

CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


class TTSGenerateRequest(BaseModel):
    """Text-to-speech generation request"""
    text: str = Field(..., min_length=1, max_length=4096, description="Text to synthesize")
    voice: Optional[str] = Field(None, description="Voice name (default from settings)")
    response_format: Optional[str] = Field(
        None, description="Audio format: mp3/opus/aac/flac/wav/pcm"
    )
    speed: Optional[float] = Field(None, ge=0.25, le=4.0, description="Speech speed")
    model: Optional[str] = Field(None, description="Override TTS model")


class TTSGenerateResponse(BaseModel):
    """Legacy JSON response (used when download=false is explicitly wanted)"""
    success: bool
    audio_base64: str = Field("", description="Base64-encoded audio")
    format: str
    model: str
    voice: str
    duration_ms: int


@router.post("/generate", summary="Text to Speech")
async def generate_speech(request: TTSGenerateRequest):
    """
    Synthesize speech from text using the configured TTS service.

    Returns the raw audio bytes with the matching Content-Type header
    (e.g. audio/mpeg), so the response can be played or saved directly.
    """
    if not settings.enable_tts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TTS is disabled. Enable it in Settings → Voice.",
        )

    fmt = request.response_format or settings.tts_default_format
    if fmt not in CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {fmt}",
        )

    import time
    start = time.time()

    service = TTSService()
    try:
        audio = await service.text_to_speech_bytes(
            text=request.text,
            voice=request.voice,
            response_format=fmt,
            speed=request.speed,
            model=request.model,
        )
    except TTSError as e:
        logger.error(f"TTS generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TTS generation failed: {e}",
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"TTS unexpected error: {e}")
        raise ServiceException(
            f"TTS generation failed: {e}", service_name="TTSService", retryable=True,
            original_error=e,
        )
    finally:
        await service.close()

    duration_ms = int((time.time() - start) * 1000)
    logger.info(f"TTS generation completed | bytes={len(audio)} | duration={duration_ms}ms")

    return Response(
        content=audio,
        media_type=CONTENT_TYPES[fmt],
        headers={"X-TTS-Duration-Ms": str(duration_ms)},
    )
