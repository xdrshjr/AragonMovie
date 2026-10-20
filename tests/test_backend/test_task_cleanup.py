"""BUG 14 regression: abandoned tasks are cancelled, temp dirs are collected."""

import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.core.task_manager import TaskManager
from backend.core.temp_project_manager import TempProjectManager


class _StubStore:
    """Minimal in-memory TaskStore replacement."""

    def __init__(self):
        self.tasks = {}

    async def save(self, task_id, task_data):
        self.tasks[task_id] = dict(task_data)

    async def get(self, task_id):
        return self.tasks.get(task_id)

    async def list_tasks(self):
        return list(self.tasks.values())

    async def start_cleanup(self):
        return None

    async def stop_cleanup(self):
        return None


@pytest.fixture()
def manager():
    mgr = TaskManager.__new__(TaskManager)  # skip __init__ side effects
    mgr.store = _StubStore()
    mgr._running_tasks = {}
    mgr._semaphore = asyncio.Semaphore(4)
    mgr._status_callbacks = []
    mgr._last_poll = {}
    mgr._cancel_reasons = {}
    mgr._idle_sweeper = None
    return mgr


class TestAbandonedTasks:
    @pytest.mark.asyncio
    async def test_task_never_polled_is_not_cancelled(self, manager, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "task_idle_timeout_seconds", 60)

        started = asyncio.Event()

        async def long_task():
            started.set()
            await asyncio.sleep(5)

        task_id = await manager.submit_task(long_task, task_type="test")
        await started.wait()

        cancelled = await manager.cancel_abandoned_tasks()

        assert cancelled == []
        assert task_id in manager._running_tasks
        await manager.cancel_task(task_id)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_task_abandoned_after_polling_is_cancelled(self, manager, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "task_idle_timeout_seconds", 1)

        started = asyncio.Event()
        was_cancelled = {"value": False}

        async def long_task():
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                was_cancelled["value"] = True
                raise

        task_id = await manager.submit_task(long_task, task_type="test")
        await started.wait()

        # The client polls once ...
        manager.note_poll(task_id)
        # ... then goes away: pretend the last poll was long ago
        manager._last_poll[task_id] = time.monotonic() - 5

        cancelled = await manager.cancel_abandoned_tasks()
        await asyncio.sleep(0.05)

        assert cancelled == [task_id]
        assert was_cancelled["value"] is True

        stored = await manager.store.get(task_id)
        assert stored["status"].value == "cancelled"
        assert "no status poll" in stored["message"]

    @pytest.mark.asyncio
    async def test_watchdog_disabled_when_timeout_is_zero(self, manager, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "task_idle_timeout_seconds", 0)

        started = asyncio.Event()

        async def long_task():
            started.set()
            await asyncio.sleep(5)

        task_id = await manager.submit_task(long_task, task_type="test")
        await started.wait()
        manager._last_poll[task_id] = 0.0

        assert await manager.cancel_abandoned_tasks() == []
        await manager.cancel_task(task_id)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_polling_refreshes_timestamp(self, manager):
        async def long_task():
            await asyncio.sleep(2)

        task_id = await manager.submit_task(long_task, task_type="test")
        manager._last_poll[task_id] = 0.0

        await manager.get_task_result(task_id)

        assert manager._last_poll[task_id] > 0.0
        await manager.cancel_task(task_id)
        await asyncio.sleep(0)


class TestTempProjectCleanup:
    def _make_dir(self, base: Path, name: str, age_hours: float) -> Path:
        path = base / name
        path.mkdir(parents=True, exist_ok=True)
        (path / "output").mkdir(exist_ok=True)
        stamp = (datetime.now() - timedelta(hours=age_hours)).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def test_removes_only_old_workflow_dirs(self, tmp_path):
        mgr = TempProjectManager(base_dir=tmp_path)
        old = self._make_dir(tmp_path, "workflow_old", age_hours=24)
        fresh = self._make_dir(tmp_path, "workflow_fresh", age_hours=1)
        other = self._make_dir(tmp_path, "not_a_workflow", age_hours=24)

        removed = mgr.cleanup_old_projects(max_age_hours=12)

        assert removed == 1
        assert not old.exists()
        assert fresh.exists()
        assert other.exists()

    def test_zero_hours_removes_everything(self, tmp_path):
        mgr = TempProjectManager(base_dir=tmp_path)
        a = self._make_dir(tmp_path, "workflow_a", age_hours=0.5)
        b = self._make_dir(tmp_path, "workflow_b", age_hours=2)

        removed = mgr.cleanup_old_projects(max_age_hours=0)

        assert removed == 2
        assert not a.exists() and not b.exists()

    def test_missing_base_dir_is_not_an_error(self, tmp_path):
        mgr = TempProjectManager(base_dir=tmp_path / "does-not-exist")
        assert mgr.cleanup_old_projects() == 0
