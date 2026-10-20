"""Helpers for running blocking work outside the asyncio event loop.

The API backend runs on a single-worker uvicorn event loop that also serves
``GET /api/v1/tasks/{id}``.  Any synchronous, long-running operation executed
directly inside a coroutine (moviepy composition, ffmpeg subprocesses, large
file copies) freezes that loop, so every status poll queues up behind it and
the frontend eventually reports a timeout even though the work is still
running.

Use :func:`run_blocking` for short-but-synchronous I/O and
:func:`run_media_blocking` for heavy media work (moviepy / ffmpeg), which runs
on a dedicated, bounded thread pool so that it can never starve the default
executor used by other requests.
"""

from __future__ import annotations

import asyncio
import functools
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

__all__ = [
    "run_blocking",
    "run_media_blocking",
    "get_media_executor",
    "shutdown_media_executor",
]

_DEFAULT_MEDIA_WORKERS = 2

_media_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _resolve_workers() -> int:
    try:
        workers = int(os.getenv("MEDIA_EXECUTOR_WORKERS", str(_DEFAULT_MEDIA_WORKERS)))
    except (TypeError, ValueError):
        workers = _DEFAULT_MEDIA_WORKERS
    return max(1, workers)


def get_media_executor() -> ThreadPoolExecutor:
    """Return the process-wide executor used for heavy media work.

    The pool size is read once from ``MEDIA_EXECUTOR_WORKERS`` (default 2).
    Keeping it small is intentional: video encoding is CPU bound, so running
    many compositions in parallel would only slow all of them down.
    """
    global _media_executor

    if _media_executor is None:
        # Lazy creation can be raced by several concurrent requests; without the
        # lock two pools would be created and one silently leaked.
        with _executor_lock:
            if _media_executor is None:
                _media_executor = ThreadPoolExecutor(
                    max_workers=_resolve_workers(),
                    thread_name_prefix="media-worker",
                )

    return _media_executor


async def run_blocking(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous callable on the loop's default thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


async def run_media_blocking(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run heavy media work on the dedicated media thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        get_media_executor(), functools.partial(func, *args, **kwargs)
    )


def shutdown_media_executor(wait: bool = False) -> None:
    """Shut the media pool down (used by tests / graceful shutdown)."""
    global _media_executor

    with _executor_lock:
        executor = _media_executor
        _media_executor = None

    if executor is not None:
        executor.shutdown(wait=wait)
