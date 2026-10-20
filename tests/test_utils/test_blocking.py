"""Tests for utils.blocking (event-loop offloading helpers)."""

import asyncio
import threading
import time
from pathlib import Path

import pytest

from utils import blocking


@pytest.fixture(autouse=True)
def _reset_executor():
    yield
    blocking.shutdown_media_executor(wait=True)


@pytest.mark.asyncio
async def test_run_media_blocking_does_not_block_the_loop():
    ticks = []

    async def ticker(stop):
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    stop = asyncio.Event()
    ticker_task = asyncio.create_task(ticker(stop))
    await asyncio.sleep(0.02)

    start = time.monotonic()
    await blocking.run_media_blocking(time.sleep, 0.3)
    end = time.monotonic()

    stop.set()
    await ticker_task

    responsive = [t for t in ticks if start <= t <= end]
    assert len(responsive) >= 5, "run_media_blocking blocked the event loop"
    assert end - start >= 0.29


@pytest.mark.asyncio
async def test_run_media_blocking_passes_args_and_kwargs():
    def combine(a, b, *, c=0):
        return a + b + c

    assert await blocking.run_media_blocking(combine, 1, 2, c=3) == 6


@pytest.mark.asyncio
async def test_run_media_blocking_uses_dedicated_thread():
    main_thread = threading.get_ident()
    worker_thread = await blocking.run_media_blocking(threading.get_ident)

    assert worker_thread != main_thread
    assert threading.current_thread().name != "media-worker"


@pytest.mark.asyncio
async def test_run_blocking_runs_off_loop():
    main_thread = threading.get_ident()
    worker_thread = await blocking.run_blocking(threading.get_ident)

    assert worker_thread != main_thread


def test_media_executor_is_reused_and_bounded(monkeypatch):
    monkeypatch.setenv("MEDIA_EXECUTOR_WORKERS", "3")
    blocking.shutdown_media_executor(wait=True)

    first = blocking.get_media_executor()
    second = blocking.get_media_executor()

    assert first is second, "a new pool was created on every call"
    assert first._max_workers == 3


def test_media_executor_survives_invalid_worker_setting(monkeypatch):
    monkeypatch.setenv("MEDIA_EXECUTOR_WORKERS", "not-a-number")
    blocking.shutdown_media_executor(wait=True)

    executor = blocking.get_media_executor()

    assert executor._max_workers >= 1


def test_shutdown_media_executor_is_idempotent():
    blocking.get_media_executor()
    blocking.shutdown_media_executor(wait=True)
    blocking.shutdown_media_executor(wait=True)  # must not raise


@pytest.mark.asyncio
async def test_composer_uses_the_media_executor():
    """Guard: the composer must not fall back to the default executor."""
    from agents.video_composer_agent import VideoComposerAgent

    seen = {}

    def fake_compose(
        video_results,
        output_filename,
        bgm_path,
        add_subtitles,
        report=None,
        narration_audio=None,
    ):
        seen["thread"] = threading.current_thread().name
        return "out.mp4"

    composer = VideoComposerAgent(output_dir=Path("."))
    composer._compose_sync = fake_compose

    clip = Path("stub_clip.mp4")
    clip.write_bytes(b"stub")
    try:
        await composer.execute(
            [{"scene_id": "scene_001", "success": True, "video_path": str(clip)}]
        )
    finally:
        clip.unlink(missing_ok=True)

    assert seen["thread"].startswith("media-worker"), seen
