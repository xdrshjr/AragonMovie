"""Model Settings API endpoints (REST v1)

Runtime configuration center for all external model services:

- GET    /api/v1/settings              -> full settings (API keys MASKED)
- PUT    /api/v1/settings              -> partial update, hot-applied + persisted
- POST   /api/v1/settings/test/{cat}   -> connectivity test (text/voice/video/image/agent)
- GET    /api/v1/settings/agent/status -> aragon CLI + agent LLM availability
- POST   /api/v1/settings/agent/chat   -> SSE stream from the configuration agent
"""
import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.core.agent_assist import (
    AgentAssistError,
    agent_chat_stream,
    get_agent_status,
)
from backend.core.settings_models import (
    AgentStatusResponse,
    ConnectionTestResult,
    SettingsUpdateRequest,
)
from backend.core.settings_store import get_settings_store
from backend.core.settings_tester import run_tests
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


class SettingsResponse(BaseModel):
    settings: dict = Field(..., description="Settings tree (API keys masked)")
    settings_file: str = Field(..., description="Persisted settings file path")
    updated_at: Optional[str] = Field(None)


@router.get("", response_model=SettingsResponse, summary="Get Model Settings")
async def get_settings():
    """Full model settings with MASKED API keys (write-only)."""
    store = get_settings_store()
    store.reload_if_changed()  # pick up agent edits made outside the API
    return SettingsResponse(
        settings=store.masked(),
        settings_file=str(store.file_path),
    )


@router.put("", response_model=SettingsResponse, summary="Update Model Settings")
async def update_settings(request: SettingsUpdateRequest):
    """Partially update settings; changes are persisted and hot-applied.

    Write-only key semantics: omit ``api_key`` (or send null) to keep the
    stored key, send ``""`` to clear it, send a new value to replace it.
    """
    store = get_settings_store()
    try:
        new_settings = store.update(request)
    except Exception as e:  # noqa: BLE001 - validation errors -> 422/400
        logger.error(f"Settings update failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid settings: {e}",
        )
    return SettingsResponse(
        settings=store.masked(),
        settings_file=str(store.file_path),
    )


@router.post(
    "/test/{category}",
    response_model=List[ConnectionTestResult],
    summary="Test Service Connectivity",
)
async def test_settings(category: str):
    """Run connectivity tests for a category: text | voice | video | image | agent.

    Tests use the CURRENT settings. ``verified`` in each result says whether
    a real request was verified ("full") or only reachability/auth ("partial").
    """
    if category not in ("text", "voice", "video", "image", "agent"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown category: {category}. Use text|voice|video|image|agent.",
        )
    store = get_settings_store()
    return await run_tests(category, store.current())


@router.get("/agent/status", response_model=AgentStatusResponse, summary="Agent Assist Status")
async def agent_status():
    """Whether the configuration agent can run, and in which mode."""
    return AgentStatusResponse(**await get_agent_status())


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = Field(
        None, description="Reuse a previous conversation session"
    )


@router.post("/agent/chat", summary="Chat with the Configuration Agent")
async def agent_chat(request: AgentChatRequest):
    """Stream one configuration-agent turn as Server-Sent Events.

    Event types on the wire (data is JSON):
    - meta            : {session_id, mode}
    - status          : {message} informational notice
    - system          : aragon session init
    - text_delta      : {text} streamed answer fragment
    - tool_call       : {id, name, input} the agent is using a tool
    - tool_result     : {id, name, preview, is_error}
    - assistant       : {text} full answer for the turn
    - result          : {stop_reason, usage, suggested_patch?}
    - settings_updated: {settings} emitted after the settings file changed
    - error           : {message, detail?}
    """
    async def event_stream():
        try:
            async for event in agent_chat_stream(
                request.message, request.session_id
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except AgentAssistError as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}\n\n'
        except Exception as e:  # noqa: BLE001
            logger.error(f"Agent chat stream failed: {e}")
            yield f'data: {json.dumps({"type": "error", "message": f"Agent chat failed: {e}"}, ensure_ascii=False)}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
