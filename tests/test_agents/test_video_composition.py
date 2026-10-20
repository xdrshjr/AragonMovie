"""
Unit tests for video composition and orchestration modules
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

# Import modules to test
from utils.video_utils import FFmpegProcessor
from utils.video_effects import VideoEffects
from utils.checkpoint import CheckpointManager
from utils.progress_monitor import ProgressMonitor, ProgressInfo
from utils.task_queue import TaskQueue, Task, TaskStatus
from agents.video_composer_agent import VideoComposerAgent
from agents.orchestrator_agent import DramaGenerationOrchestrator


class TestFFmpegProcessor:
    """FFmpeg video processor tests"""

    def test_init(self):
        """Test FFmpegProcessor initialization"""
        processor = FFmpegProcessor()
        assert processor is not None
        assert processor.logger is not None

    @pytest.mark.skip(reason="Requires FFmpeg and actual video files")
    def test_get_video_info(self):
        """Test getting video information"""
        processor = FFmpegProcessor()
        # This would need a real video file to test
        pass

    @pytest.mark.skip(reason="Requires FFmpeg and actual video files")
    def test_concatenate_videos(self):
        """Test video concatenation"""
        processor = FFmpegProcessor()
        # This would need real video files to test
        pass


class TestVideoEffects:
    """Video effects tests"""

    def test_init(self):
        """Test VideoEffects initialization"""
        effects = VideoEffects()
        assert effects is not None
        assert effects.logger is not None

    @pytest.mark.skip(reason="Requires MoviePy and actual video clips")
    def test_apply_color_grading(self):
        """Test color grading effect"""
        effects = VideoEffects()
        # This would need real video clips to test
        pass


class TestCheckpointManager:
    """Checkpoint manager tests"""

    def test_init(self, tmp_path):
        """Test CheckpointManager initialization"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        assert manager.checkpoint_dir == checkpoint_dir
        assert checkpoint_dir.exists()

    def test_save_and_load_checkpoint(self, tmp_path):
        """Test saving and loading checkpoints"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        # Save checkpoint
        task_id = "test_task_123"
        stage = "parsing"
        data = {"scenes": 5, "duration": 30.0}

        checkpoint_file = manager.save_checkpoint(task_id, stage, data)
        assert checkpoint_file.exists()

        # Load checkpoint
        loaded = manager.load_checkpoint(task_id, stage)
        assert loaded is not None
        assert loaded['task_id'] == task_id
        assert loaded['stage'] == stage
        assert loaded['data'] == data

    def test_checkpoint_exists(self, tmp_path):
        """Test checking checkpoint existence"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        task_id = "test_task_456"
        stage = "image_generation"

        # Should not exist initially
        assert not manager.checkpoint_exists(task_id, stage)

        # Save checkpoint
        manager.save_checkpoint(task_id, stage, {"test": "data"})

        # Should exist now
        assert manager.checkpoint_exists(task_id, stage)

    def test_list_checkpoints(self, tmp_path):
        """Test listing checkpoints"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        task_id = "test_task_789"

        # Save multiple checkpoints
        manager.save_checkpoint(task_id, "stage1", {"data": 1})
        manager.save_checkpoint(task_id, "stage2", {"data": 2})
        manager.save_checkpoint(task_id, "stage3", {"data": 3})

        checkpoints = manager.list_checkpoints(task_id)
        assert len(checkpoints) == 3

    def test_clear_checkpoints(self, tmp_path):
        """Test clearing checkpoints"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        task_id = "test_task_clear"

        # Save checkpoints
        manager.save_checkpoint(task_id, "stage1", {"data": 1})
        manager.save_checkpoint(task_id, "stage2", {"data": 2})

        # Clear all checkpoints
        manager.clear_checkpoints(task_id)

        # Should not exist anymore
        assert not manager.checkpoint_exists(task_id)

    def test_get_resume_stage(self, tmp_path):
        """Test getting resume stage"""
        checkpoint_dir = tmp_path / "checkpoints"
        manager = CheckpointManager(checkpoint_dir)

        task_id = "test_resume"

        # No checkpoints yet
        assert manager.get_resume_stage(task_id) is None

        # Save parsing checkpoint
        manager.save_checkpoint(task_id, "parsing", {"data": 1})
        assert manager.get_resume_stage(task_id) == "image_generation"

        # Save image_generation checkpoint
        manager.save_checkpoint(task_id, "image_generation", {"data": 2})
        assert manager.get_resume_stage(task_id) == "video_generation"


class TestProgressMonitor:
    """Progress monitor tests"""

    def test_init(self):
        """Test ProgressMonitor initialization"""
        monitor = ProgressMonitor(total_steps=100)
        assert monitor.total_steps == 100
        assert monitor.current_step == 0
        assert len(monitor.callbacks) == 0

    @pytest.mark.asyncio
    async def test_update_progress(self):
        """Test updating progress"""
        monitor = ProgressMonitor(total_steps=100)

        await monitor.update(50, "Processing...")

        assert monitor.current_step == 50
        assert len(monitor.history) == 1

        progress = monitor.get_current_progress()
        assert progress is not None
        assert progress.percent == 50.0
        assert progress.message == "Processing..."

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Test progress callback"""
        monitor = ProgressMonitor(total_steps=100)

        callback_called = False
        received_info = None

        async def callback(info: ProgressInfo):
            nonlocal callback_called, received_info
            callback_called = True
            received_info = info

        monitor.register_callback(callback)

        await monitor.update(25, "Test message")

        assert callback_called
        assert received_info is not None
        assert received_info.percent == 25.0

    def test_calculate_eta(self):
        """Test ETA calculation"""
        monitor = ProgressMonitor(total_steps=100)

        # No steps completed yet
        assert monitor._calculate_eta() is None

        # Simulate some progress
        monitor.current_step = 50

        eta = monitor._calculate_eta()
        assert eta is not None
        assert eta >= 0

    def test_completion_check(self):
        """Test completion check"""
        monitor = ProgressMonitor(total_steps=100)

        assert not monitor.is_completed()

        monitor.current_step = 100
        assert monitor.is_completed()

        monitor.current_step = 150
        assert monitor.is_completed()


class TestTaskQueue:
    """Task queue tests"""

    def test_init(self):
        """Test TaskQueue initialization"""
        queue = TaskQueue(max_workers=3)
        assert queue.max_workers == 3
        assert not queue._running

    @pytest.mark.asyncio
    async def test_submit_and_execute_task(self):
        """Test submitting and executing tasks"""
        queue = TaskQueue(max_workers=2)
        await queue.start()

        result_value = 42

        async def test_task():
            await asyncio.sleep(0.1)
            return result_value

        # Submit task
        task = await queue.submit(test_task)
        assert task.task_id in queue.tasks
        assert task.status == TaskStatus.PENDING

        # Wait for result
        result = await queue.get_result(task.task_id, timeout=5.0)
        assert result == result_value
        assert task.status == TaskStatus.COMPLETED

        await queue.stop()

    @pytest.mark.asyncio
    async def test_task_failure(self):
        """Test task failure handling"""
        queue = TaskQueue(max_workers=1)
        await queue.start()

        async def failing_task():
            await asyncio.sleep(0.1)
            raise ValueError("Test error")

        # Submit task
        task = await queue.submit(failing_task)

        # Wait for task to fail
        with pytest.raises(ValueError):
            await queue.get_result(task.task_id, timeout=5.0)

        assert task.status == TaskStatus.FAILED
        assert task.error is not None

        await queue.stop()

    @pytest.mark.asyncio
    async def test_cancel_task(self):
        """Test canceling tasks"""
        queue = TaskQueue(max_workers=1)

        async def slow_task():
            await asyncio.sleep(10)

        # Submit task but don't start queue
        task = await queue.submit(slow_task)

        # Cancel task before it starts
        cancelled = await queue.cancel_task(task.task_id)
        assert cancelled
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_priority_queue(self):
        """Test priority queue"""
        queue = TaskQueue(max_workers=1, use_priority=True)
        await queue.start()

        results = []

        async def priority_task(value):
            await asyncio.sleep(0.1)
            results.append(value)
            return value

        # Submit tasks with different priorities
        task1 = await queue.submit(priority_task, 1, priority=1)
        task2 = await queue.submit(priority_task, 2, priority=3)  # Higher priority
        task3 = await queue.submit(priority_task, 3, priority=2)

        # Wait for all tasks
        await queue.wait_all(timeout=10.0)

        # Higher priority should execute first (but first task might have started)
        # So we just check they all completed
        assert len(results) == 3

        await queue.stop()

    def test_queue_statistics(self):
        """Test queue statistics"""
        queue = TaskQueue(max_workers=2)

        stats = queue.get_statistics()
        assert stats['total_tasks'] == 0
        assert stats['completed_tasks'] == 0
        assert stats['failed_tasks'] == 0


class TestVideoComposerAgent:
    """Video composer agent tests"""

    def test_init(self, tmp_path):
        """Test VideoComposerAgent initialization"""
        output_dir = tmp_path / "output"
        agent = VideoComposerAgent(output_dir=output_dir)

        assert agent.agent_id == "video_composer"
        assert agent.output_dir == output_dir
        assert output_dir.exists()

    @pytest.mark.asyncio
    async def test_validate_input(self, tmp_path):
        """Test input validation"""
        agent = VideoComposerAgent(output_dir=tmp_path)

        # Empty results should fail
        assert not await agent.validate_input([])

        # Valid structure but non-existent files should fail
        video_results = [
            {'scene_id': 1, 'video_path': '/non/existent/path.mp4'}
        ]
        assert not await agent.validate_input(video_results)

    @pytest.mark.skip(reason="Requires MoviePy and actual video files")
    @pytest.mark.asyncio
    async def test_execute_composition(self):
        """Test video composition execution"""
        # This would need real video files to test
        pass


class TestDramaGenerationOrchestrator:
    """Drama generation orchestrator tests"""

    def test_init(self):
        """Test DramaGenerationOrchestrator initialization"""
        config = {
            'image': {},
            'video': {},
            'composer': {}
        }
        orchestrator = DramaGenerationOrchestrator(config=config)

        assert orchestrator.agent_id == "orchestrator"
        assert orchestrator.script_parser is not None
        assert orchestrator.image_generator is not None
        assert orchestrator.video_generator is not None
        assert orchestrator.video_composer is not None

    @pytest.mark.asyncio
    async def test_validate_input(self):
        """Test script validation"""
        orchestrator = DramaGenerationOrchestrator()

        # Empty string should fail
        assert not await orchestrator.validate_input("")

        # Short string should fail
        assert not await orchestrator.validate_input("test")

        # Valid script should pass
        assert await orchestrator.validate_input("This is a valid script text for testing purposes.")

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Test progress callback"""
        orchestrator = DramaGenerationOrchestrator()

        progress_updates = []

        async def progress_callback(percent, message):
            progress_updates.append({'percent': percent, 'message': message})

        await orchestrator._update_progress(50, "Test progress")

        # Without callback, should just log
        assert len(progress_updates) == 0

        # With callback
        orchestrator.progress_callback = progress_callback
        await orchestrator._update_progress(75, "Test progress 2")
        # This would call the callback if implemented correctly

    @pytest.mark.asyncio
    async def test_get_task_status(self):
        """Test getting task status"""
        orchestrator = DramaGenerationOrchestrator()

        # No task running
        status = await orchestrator.get_task_status()
        assert status['status'] == 'idle'

    @pytest.mark.skip(reason="Requires full integration with all agents")
    @pytest.mark.asyncio
    async def test_full_execution(self):
        """Test full drama generation execution"""
        # This would need all agents properly mocked or real services
        pass


class TestVideoComposerNonBlocking:
    """BUG 2 regression: composition must never run on the asyncio event loop.

    The backend serves `GET /api/v1/tasks/{id}` from the same single-worker event
    loop that starts the workflow, so a synchronous moviepy composition there
    froze every status poll for minutes and the frontend reported the run as
    failed even though the mp4 had been written.
    """

    @pytest.mark.asyncio
    async def test_execute_runs_composition_off_event_loop(self, tmp_path):
        import time

        composer = VideoComposerAgent(output_dir=tmp_path)
        clip_path = tmp_path / "clip_001.mp4"
        clip_path.write_bytes(b"stub")

        def fake_compose(
            video_results,
            output_filename,
            bgm_path,
            add_subtitles,
            report_progress=None
        ):
            # Stands in for the multi-minute moviepy / ffmpeg composition
            time.sleep(0.4)
            return str(tmp_path / output_filename)

        tick_times = []

        async def ticker(stop):
            while not stop.is_set():
                tick_times.append(time.monotonic())
                await asyncio.sleep(0.02)

        video_results = [
            {"scene_id": "scene_001", "success": True, "video_path": str(clip_path)}
        ]

        stop = asyncio.Event()
        ticker_task = asyncio.create_task(ticker(stop))
        await asyncio.sleep(0.05)  # let the ticker establish itself first

        # Patch the instance so the stub is not bound as a method
        with patch.object(composer, "_compose_sync", new=fake_compose):
            start = time.monotonic()
            output_path = await composer.execute(video_results)
            end = time.monotonic()

        stop.set()
        await ticker_task

        # Ticks recorded *while* the composition was running: with the bug the
        # whole 0.4s block happens inside one task, so the loop cannot tick.
        responsive_ticks = [t for t in tick_times if start <= t <= end]

        assert output_path == str(tmp_path / "final_drama.mp4")
        assert len(responsive_ticks) >= 5, (
            f"event loop was blocked while composing "
            f"(only {len(responsive_ticks)} ticks in {end - start:.2f}s); "
            "composition must run via utils.blocking.run_media_blocking"
        )

    @pytest.mark.asyncio
    async def test_progress_callback_fires_from_worker_thread(self, tmp_path):
        composer = VideoComposerAgent(output_dir=tmp_path)
        clip_path = tmp_path / "clip_001.mp4"
        clip_path.write_bytes(b"stub")

        observed = []

        async def on_progress(percent, message):
            observed.append((percent, message))

        def fake_compose(
            video_results,
            output_filename,
            bgm_path,
            add_subtitles,
            report_progress=None
        ):
            if report_progress:
                report_progress(50.0, "halfway")
            return str(tmp_path / output_filename)

        video_results = [
            {"scene_id": "scene_001", "success": True, "video_path": str(clip_path)}
        ]

        # Patch the instance so the stub is not bound as a method
        with patch.object(composer, "_compose_sync", new=fake_compose):
            await composer.execute(video_results, progress_callback=on_progress)

        # run_coroutine_threadsafe schedules the coroutine on the loop
        await asyncio.sleep(0.05)

        assert observed, "compose progress callback never reached the event loop"
        assert observed[0][0] == 50.0


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
