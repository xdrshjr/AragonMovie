"""Task management API endpoints (REST v1)

Provides endpoints for querying, listing, and managing async tasks.
"""
from fastapi import APIRouter, HTTPException, status
from typing import List

from backend.core.models import TaskInfo, TaskResult
from backend.core.task_manager import get_task_manager
from backend.core.exceptions import TaskNotFoundException, TaskCancelledException
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/{task_id}", response_model=TaskResult, summary="Get Task Status")
async def get_task_status(task_id: str):
    """
    Get the status and result of a task.
    
    This is the primary endpoint for polling task status. Use it to check
    the progress of async operations like video generation.
    
    **Task Status Flow:**
    - `pending`: Task is queued
    - `processing`: Task is currently running
    - `completed`: Task finished successfully (check `result` field)
    - `failed`: Task failed (check `error` field)
    - `cancelled`: Task was cancelled
    
    **Parameters:**
    - **task_id**: The task identifier returned when submitting the task
    
    **Returns:**
    - Complete task information including status, progress, and result/error
    
    **Example:**
    ```
    GET /api/v1/tasks/vid_a1b2c3d4e5f6
    
    Response (processing):
    {
      "task_id": "vid_a1b2c3d4e5f6",
      "status": "processing",
      "progress": 45,
      "created_at": "2026-01-11T10:30:00Z",
      "updated_at": "2026-01-11T10:30:15Z",
      "result": null,
      "error": null
    }
    
    Response (completed):
    {
      "task_id": "vid_a1b2c3d4e5f6",
      "status": "completed",
      "progress": 100,
      "created_at": "2026-01-11T10:30:00Z",
      "updated_at": "2026-01-11T10:31:00Z",
      "completed_at": "2026-01-11T10:31:00Z",
      "result": {
        "service": "veo3",
        "result": {
          "video_url": "https://..."
        },
        "duration": 60.5
      },
      "error": null
    }
    ```
    """
    logger.debug(f"Task status request | task_id={task_id}")
    
    try:
        task_manager = get_task_manager()
        task_result = await task_manager.get_task_result(task_id)
        
        logger.debug(f"Task status | task_id={task_id} | status={task_result.status}")
        
        return task_result
        
    except TaskNotFoundException:
        logger.warning(f"Task not found | task_id={task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    except TaskCancelledException:
        logger.info(f"Task was cancelled | task_id={task_id}")
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=f"Task was cancelled: {task_id}"
        )
    except Exception as e:
        logger.exception(f"Error getting task status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.delete("/{task_id}", summary="Cancel Task")
async def cancel_task(task_id: str):
    """
    Cancel a running or pending task.
    
    Attempts to cancel a task that is currently pending or processing.
    Completed or failed tasks cannot be cancelled.
    
    **Parameters:**
    - **task_id**: The task identifier
    
    **Returns:**
    - Success message if task was cancelled
    """
    logger.info(f"Task cancellation request | task_id={task_id}")
    
    try:
        task_manager = get_task_manager()
        cancelled = await task_manager.cancel_task(task_id)
        
        if cancelled:
            logger.info(f"Task cancelled | task_id={task_id}")
            return {
                "success": True,
                "message": f"Task {task_id} has been cancelled",
                "task_id": task_id
            }
        else:
            logger.warning(f"Task cannot be cancelled | task_id={task_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task {task_id} cannot be cancelled (not running or already completed)"
            )
        
    except TaskNotFoundException:
        logger.warning(f"Task not found for cancellation | task_id={task_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task not found: {task_id}"
        )
    except Exception as e:
        logger.exception(f"Error cancelling task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.post(
    "/maintenance/sweep",
    summary="Cancel Abandoned Tasks",
    include_in_schema=False,
)
async def sweep_abandoned_tasks():
    """Cancel running tasks whose client stopped polling.

    The frontend polls ``GET /api/v1/tasks/{id}`` every couple of seconds while
    the workflow page is open. If the tab is closed or the browser dies, the
    backend task used to keep generating to completion (and keep spending
    quota). The idle watchdog does this automatically; this endpoint triggers a
    sweep on demand (ops / E2E teardown).
    """
    logger.info("Abandoned-task sweep requested")

    try:
        task_manager = get_task_manager()
        cancelled = await task_manager.sweep_abandoned_tasks()
        logger.info(f"Abandoned-task sweep finished | cancelled={cancelled}")
        return {
            "success": True,
            "cancelled_count": len(cancelled),
            "cancelled_tasks": cancelled,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Abandoned-task sweep failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Abandoned-task sweep failed: {str(e)}",
        )


@router.get("/", response_model=List[TaskInfo], summary="List All Tasks")
async def list_tasks():
    """
    List all tasks in the system.
    
    Returns a list of all tasks (pending, processing, completed, failed).
    This is useful for monitoring and debugging.
    
    **Note:** In production, you should implement user-specific task filtering
    and pagination for better performance and security.
    
    **Returns:**
    - List of task information objects
    """
    logger.debug("List all tasks request")
    
    try:
        task_manager = get_task_manager()
        tasks = await task_manager.list_all_tasks()
        
        logger.info(f"Listed {len(tasks)} tasks")
        
        return tasks
        
    except Exception as e:
        logger.exception(f"Error listing tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

