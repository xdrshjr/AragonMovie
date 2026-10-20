"""BUG 2 regression (integration): task polling must stay responsive while heavy media work runs.

The workflow endpoint and ``GET /api/v1/tasks/{id}`` share one uvicorn event loop.
When the final video was composed synchronously inside the workflow coroutine,
every status poll queued behind moviepy/ffmpeg for minutes, which the frontend
surfaced as ``Generation failed`` even though the mp4 had been written.
"""

import asyncio
import time

import httpx
import pytest

from backend.core.task_manager import get_task_manager
from utils.blocking import run_media_blocking


@pytest.mark.asyncio
async def test_task_status_endpoint_responds_during_media_work():
    from backend.main import app

    task_manager = get_task_manager()

    async def fake_workflow():
        # Mirrors VideoComposerAgent.execute(): blocking work pushed to a worker thread
        await run_media_blocking(time.sleep, 1.5)
        return {"video_url": "http://example.com/final.mp4", "duration": 24.36}

    task_id = await task_manager.submit_task(fake_workflow, task_type="wftest")

    latencies = []
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Poll while the "composition" is still running
        deadline = time.monotonic() + 1.2
        while time.monotonic() < deadline:
            started = time.monotonic()
            response = await client.get(f"/api/v1/tasks/{task_id}")
            latencies.append(time.monotonic() - started)

            assert response.status_code == 200
            assert response.json()["task_id"] == task_id
            await asyncio.sleep(0.05)

    # Let the background task finish before leaving the test
    await asyncio.sleep(0.5)

    assert len(latencies) >= 8, f"too few polls: {len(latencies)}"
    worst = max(latencies)
    assert worst < 0.5, (
        f"status polling was blocked by media work: worst latency {worst:.2f}s "
        f"({len(latencies)} polls); composition must run via run_media_blocking()"
    )
