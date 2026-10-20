"""Async task management system

This module provides task submission, status tracking, and result storage.
Tasks are stored in memory or Redis depending on configuration.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from enum import Enum
import time
import traceback

from backend.core.models import TaskStatus, TaskInfo, TaskResult
from backend.core.exceptions import TaskNotFoundException, TaskCancelledException, StorageException, ServiceException
from backend.config import settings
from backend.utils.logger import get_logger
from backend.utils.helpers import generate_task_id

logger = get_logger(__name__)


class TaskStore:
    """In-memory task storage with automatic cleanup"""
    
    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def start_cleanup(self):
        """Start background cleanup task (idempotent, restart-safe)."""
        # A task left over from a previous event loop (e.g. two TestClient
        # lifespans in one process) must be replaced, not reused.
        if self._cleanup_task is not None and (
            self._cleanup_task.done() or self._cleanup_task.get_loop() is not asyncio.get_running_loop()
        ):
            self._cleanup_task = None

        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Task cleanup service started")
    
    async def stop_cleanup(self):
        """Stop background cleanup task"""
        task, self._cleanup_task = self._cleanup_task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001 - loop may already be closing
            logger.debug(f"Cleanup task ended with {e.__class__.__name__}: {e}")
        logger.info("Task cleanup service stopped")
    
    async def _cleanup_loop(self):
        """Background loop to clean up expired tasks"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    async def cleanup_expired(self):
        """Remove tasks older than retention period"""
        async with self._lock:
            retention_delta = timedelta(hours=settings.task_retention_hours)
            now = datetime.utcnow()
            expired_tasks = []
            
            for task_id, task_data in self._tasks.items():
                created_at = task_data.get("created_at")
                if created_at and (now - created_at) > retention_delta:
                    expired_tasks.append(task_id)
            
            for task_id in expired_tasks:
                del self._tasks[task_id]
            
            if expired_tasks:
                logger.info(f"Cleaned up {len(expired_tasks)} expired tasks")
    
    async def save(self, task_id: str, task_data: Dict[str, Any]):
        """Save task data"""
        async with self._lock:
            self._tasks[task_id] = task_data
            logger.debug(f"Task saved: {task_id}")
    
    async def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task data"""
        async with self._lock:
            return self._tasks.get(task_id)
    
    async def delete(self, task_id: str):
        """Delete task data"""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.debug(f"Task deleted: {task_id}")
    
    async def list_tasks(self) -> List[Dict[str, Any]]:
        """List all tasks"""
        async with self._lock:
            return list(self._tasks.values())


class TaskManager:
    """Manager for async task execution and tracking"""

    def __init__(self):
        self.store = TaskStore()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_tasks)
        self._status_callbacks: List[Callable] = []  # Callbacks for status updates
        # BUG 14: monotonic timestamps of the last status poll per task. A task
        # that was being watched and then stopped being polled (closed tab,
        # crashed browser) is cancelled by the idle sweep so it stops burning
        # quota. Tasks that were never polled are never touched.
        self._last_poll: Dict[str, float] = {}
        # Why a task was cancelled ("user" / "abandoned"), surfaced in status
        self._cancel_reasons: Dict[str, str] = {}
        self._idle_sweeper: Optional[asyncio.Task] = None
        logger.info(f"TaskManager initialized (max concurrent: {settings.max_concurrent_tasks})")

    def register_status_callback(self, callback: Callable):
        """Register a callback to be called when task status changes

        Args:
            callback: Async function with signature (task_id, status, progress, result, error)
        """
        self._status_callbacks.append(callback)
        logger.debug(f"Registered status callback: {callback.__name__}")

    def unregister_status_callback(self, callback: Callable):
        """Unregister a status callback

        Args:
            callback: Callback function to remove
        """
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
            logger.debug(f"Unregistered status callback: {callback.__name__}")
    
    async def start(self):
        """Start the task manager"""
        await self.store.start_cleanup()
        self._start_idle_sweeper()
    
    def _start_idle_sweeper(self) -> None:
        """Start the abandoned-task watchdog (no-op when disabled)."""
        if self._idle_sweeper is not None:
            return
        if getattr(settings, "task_idle_timeout_seconds", 0) <= 0:
            logger.info("Abandoned-task watchdog disabled (task_idle_timeout_seconds=0)")
            return
        self._idle_sweeper = asyncio.create_task(self._idle_sweep_loop())
        logger.info(
            "Abandoned-task watchdog started | "
            f"idle_timeout={settings.task_idle_timeout_seconds}s | "
            f"interval={settings.task_idle_sweep_interval_seconds}s"
        )

    async def stop_idle_sweeper(self) -> None:
        """Stop the abandoned-task watchdog."""
        if self._idle_sweeper is not None:
            self._idle_sweeper.cancel()
            try:
                await self._idle_sweeper
            except asyncio.CancelledError:
                pass
            self._idle_sweeper = None
            logger.info("Abandoned-task watchdog stopped")

    async def _idle_sweep_loop(self) -> None:
        interval = max(1, int(settings.task_idle_sweep_interval_seconds))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.cancel_abandoned_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001 - never kill the loop
                logger.error(f"Error in abandoned-task sweep: {e}")

    def note_poll(self, task_id: str) -> None:
        """Record that a client is (still) watching this task."""
        self._last_poll[task_id] = time.monotonic()

    async def cancel_abandoned_tasks(self) -> List[str]:
        """Cancel running tasks nobody has polled for the idle timeout.

        Returns:
            The task ids that were cancelled.
        """
        timeout = getattr(settings, "task_idle_timeout_seconds", 0)
        if timeout <= 0:
            return []

        now = time.monotonic()
        # Only tasks that are actually running here can be cancelled
        candidates = [
            task_id for task_id in list(self._running_tasks)
            if task_id in self._last_poll
        ]

        cancelled: List[str] = []
        for task_id in candidates:
            idle_for = now - self._last_poll[task_id]
            if idle_for < timeout:
                continue

            logger.warning(
                f"Task abandoned by client, cancelling | task_id={task_id} | "
                f"idle_for={idle_for:.0f}s > {timeout}s"
            )
            reason = (
                "Task cancelled automatically: no status poll for "
                f"{int(idle_for)}s (client disconnected or closed the page)"
            )
            await self.cancel_task(task_id, reason=reason)
            # NOTE: the reason stays in _cancel_reasons so the task's own
            # CancelledError handler writes the same, meaningful message
            # instead of overwriting this one with a generic string.
            await self._update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                message=reason,
            )
            self._last_poll.pop(task_id, None)
            cancelled.append(task_id)

        return cancelled

    async def stop(self):
        """Stop the task manager and cancel all running tasks"""
        await self.stop_idle_sweeper()
        # Cancel all running tasks
        for task_id, task in self._running_tasks.items():
            task.cancel()
            logger.info(f"Cancelled running task: {task_id}")
        
        # Wait for cancellation
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
        
        await self.store.stop_cleanup()
    
    async def submit_task(
        self,
        task_func: Callable,
        task_type: str = "task",
        **kwargs
    ) -> str:
        """Submit a new task for async execution
        
        Args:
            task_func: Async function to execute
            task_type: Type prefix for task ID (e.g., 'img', 'vid')
            **kwargs: Arguments to pass to task_func
            
        Returns:
            Task ID
        """
        task_id = generate_task_id(task_type)
        
        # Create task data
        task_data = {
            "task_id": task_id,
            "status": TaskStatus.PENDING,
            "progress": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "message": "Task submitted",
            "task_type": task_type,
            "result": None,
            "error": None
        }
        
        await self.store.save(task_id, task_data)
        
        # Start task execution in background
        task = asyncio.create_task(self._execute_task(task_id, task_func, **kwargs))
        self._running_tasks[task_id] = task
        
        logger.info(f"Task submitted: {task_id} (type: {task_type})")
        
        return task_id
    
    async def _execute_task(
        self,
        task_id: str,
        task_func: Callable,
        **kwargs
    ):
        """Execute a task with error handling
        
        Args:
            task_id: Task identifier
            task_func: Async function to execute
            **kwargs: Arguments to pass to task_func
        """
        try:
            # Acquire semaphore for concurrency control
            async with self._semaphore:
                # Update status to processing
                await self._update_task_status(
                    task_id,
                    TaskStatus.PROCESSING,
                    message="Task processing started"
                )
                
                logger.info(f"Task processing started: {task_id}")
                start_time = time.time()
                
                # Execute the task function
                result = await task_func(**kwargs)
                
                duration = time.time() - start_time
                
                # Update status to completed
                await self._update_task_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    progress=100,
                    message="Task completed successfully",
                    result=result
                )
                
                logger.info(f"Task completed: {task_id} (duration: {duration:.2f}s)")
                
        except asyncio.CancelledError:
            reason = self._cancel_reasons.pop(task_id, None)
            logger.warning(f"Task cancelled: {task_id} | reason={reason or 'user'}")
            await self._update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                message=reason or "Task was cancelled"
            )
            
        except Exception as e:
            logger.exception(f"Task failed: {task_id} | error: {str(e)}")

            # 构建详细的错误信息
            error_info = {
                "type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }

            # 如果是ServiceException，提取额外的错误信息
            if isinstance(e, ServiceException):
                error_info.update({
                    "service": e.service_name,
                    "retryable": e.retryable,
                    "error_code": e.error_code,
                    "error_type": e.error_type,
                    "stage": e.stage,
                    "api_response": e.api_response,
                    "original_error": str(e.original_error) if e.original_error else None
                })
                logger.error(f"Service error details | service={e.service_name} | "
                           f"code={e.error_code} | type={e.error_type} | "
                           f"stage={e.stage} | retryable={e.retryable}")

            await self._update_task_status(
                task_id,
                TaskStatus.FAILED,
                message=str(e),
                error=error_info
            )
        
        finally:
            # Remove from running tasks and drop watchdog bookkeeping, otherwise
            # completed tasks would keep entries in _last_poll / _cancel_reasons.
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
            self._last_poll.pop(task_id, None)
            self._cancel_reasons.pop(task_id, None)
    
    async def _update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: int = None,
        message: str = None,
        result: Any = None,
        error: Any = None
    ):
        """Update task status

        Args:
            task_id: Task identifier
            status: New status
            progress: Progress percentage (0-100)
            message: Status message
            result: Task result data
            error: Error information
        """
        task_data = await self.store.get(task_id)
        if not task_data:
            logger.warning(f"Attempted to update non-existent task: {task_id}")
            return

        task_data["status"] = status
        task_data["updated_at"] = datetime.utcnow()

        if progress is not None:
            task_data["progress"] = progress

        if message is not None:
            task_data["message"] = message

        if result is not None:
            task_data["result"] = result

        if error is not None:
            task_data["error"] = error

        if status == TaskStatus.COMPLETED:
            task_data["completed_at"] = datetime.utcnow()

        await self.store.save(task_id, task_data)

        # Call registered callbacks
        if self._status_callbacks:
            for callback in self._status_callbacks:
                try:
                    await callback(
                        task_id=task_id,
                        status=status,
                        progress=task_data["progress"],
                        result=result,
                        error=error
                    )
                except Exception as e:
                    logger.error(f"Error in status callback {callback.__name__}: {e}")
    
    async def get_task_status(self, task_id: str) -> TaskInfo:
        """Get current task status
        
        Args:
            task_id: Task identifier
            
        Returns:
            TaskInfo object
            
        Raises:
            TaskNotFoundException: If task doesn't exist
        """
        task_data = await self.store.get(task_id)
        if not task_data:
            raise TaskNotFoundException(task_id)
        
        return TaskInfo(
            task_id=task_data["task_id"],
            status=task_data["status"],
            progress=task_data["progress"],
            created_at=task_data["created_at"],
            updated_at=task_data["updated_at"],
            message=task_data.get("message")
        )
    
    async def get_task_result(self, task_id: str) -> TaskResult:
        """Get complete task result
        
        Args:
            task_id: Task identifier
            
        Returns:
            TaskResult object
            
        Raises:
            TaskNotFoundException: If task doesn't exist
            TaskCancelledException: If task was cancelled
        """
        # BUG 14: mark the task as still being watched, so the abandoned-task
        # watchdog only cancels tasks whose client stopped polling.
        if task_id in self._running_tasks:
            self.note_poll(task_id)

        task_data = await self.store.get(task_id)
        if not task_data:
            raise TaskNotFoundException(task_id)
        
        if task_data["status"] == TaskStatus.CANCELLED:
            raise TaskCancelledException(task_id)
        
        return TaskResult(
            task_id=task_data["task_id"],
            status=task_data["status"],
            progress=task_data["progress"],
            created_at=task_data["created_at"],
            updated_at=task_data["updated_at"],
            completed_at=task_data.get("completed_at"),
            result=task_data.get("result"),
            error=task_data.get("error")
        )
    
    async def cancel_task(self, task_id: str, reason: str = "") -> bool:
        """Cancel a running task
        
        Args:
            task_id: Task identifier
            reason: Optional message stored on the cancelled task

        Returns:
            True if task was cancelled, False if not running
        """
        if reason:
            self._cancel_reasons[task_id] = reason
        message = self._cancel_reasons.get(task_id) or "Task cancelled by user"

        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            task.cancel()
            logger.info(f"Task cancellation requested: {task_id}")
            # The reason stays in _cancel_reasons so the task's own
            # CancelledError handler can write it; that handler (and the
            # _execute_task finally block) both pop the entry, so it cannot leak
            # even if the task finishes without observing the cancellation.
            return True
        
        # If task exists but not running, mark as cancelled
        task_data = await self.store.get(task_id)
        if task_data and task_data["status"] in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            self._cancel_reasons.pop(task_id, None)
            await self._update_task_status(
                task_id,
                TaskStatus.CANCELLED,
                message=message
            )
            return True
        
        # Nothing was cancelled: make sure the reason does not linger
        self._cancel_reasons.pop(task_id, None)
        return False
    
    async def sweep_abandoned_tasks(self) -> List[str]:
        """Public hook: run one abandoned-task sweep now."""
        return await self.cancel_abandoned_tasks()

    async def list_all_tasks(self) -> List[TaskInfo]:
        """List all tasks
        
        Returns:
            List of TaskInfo objects
        """
        all_tasks = await self.store.list_tasks()
        return [
            TaskInfo(
                task_id=task["task_id"],
                status=task["status"],
                progress=task["progress"],
                created_at=task["created_at"],
                updated_at=task["updated_at"],
                message=task.get("message")
            )
            for task in all_tasks
        ]


# Global task manager instance
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get the global task manager instance"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

