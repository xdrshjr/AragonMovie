"""Workflow API Endpoints (REST v1)

Provides endpoints for full workflow video generation pipeline.
"""
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Any
import os

from backend.core.models import (
    WorkflowGenerationRequest,
    WorkflowGenerationResponse,
    TaskStatus,
    QuickModeWorkflowRequest
)
from backend.models.project_models import (
    CreateProjectRequest,
    VideoType,
    GenerationMode
)
from backend.core.workflow_service import get_workflow_service
from backend.core.quick_mode_service import get_quick_mode_service
from backend.utils.asset_manager import get_asset_manager
from backend.core.task_manager import get_task_manager
from backend.core.project_manager import get_project_manager
from backend.core.exceptions import TaskNotFoundException
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/generate", response_model=WorkflowGenerationResponse, summary="Generate Video Workflow")
async def generate_workflow(request: WorkflowGenerationRequest, http_request: Request):
    """
    Generate a complete video workflow from script to final composed video.
    
    This endpoint orchestrates the full CLI-based pipeline:
    1. Script parsing
    2. Character reference generation (if not provided)
    3. Scene image generation (if not provided)
    4. Video generation for each scene
    5. Video composition with transitions
    
    **Two Modes:**
    
    **Mode A - With Pre-generated Images:**
    ```json
    {
      "script": "# My Story\\n## Characters\\n...",
      "character_images": {
        "Alice": "base64_or_url",
        "Bob": "base64_or_url"
      },
      "scene_images": {
        "scene_001": "base64_or_url",
        "scene_002": "base64_or_url"
      },
      "config": {...}
    }
    ```
    
    **Mode B - Full Pipeline:**
    ```json
    {
      "script": "# My Story\\n## Characters\\n...",
      "config": {...}
    }
    ```
    
    **Returns:**
    - Task ID for polling status
    - Initial task status
    
    **Workflow:**
    1. Submit workflow request → Get task_id
    2. Poll `/api/v1/tasks/{task_id}` for status and progress
    3. When status="completed", get video_url and assets from result
    4. Access assets via `/api/v1/workflow/assets/{task_id}/{asset_type}/{filename}`
    """
    # Determine mode
    mode = "with_images" if (request.character_images or request.scene_images) else "full_pipeline"

    logger.info(
        f"WorkflowAPI | Workflow generation request | "
        f"mode={mode} | "
        f"script_length={len(request.script)} | "
        f"char_images={len(request.character_images) if request.character_images else 0} | "
        f"scene_images={len(request.scene_images) if request.scene_images else 0}"
    )

    try:
        # Get base URL from request
        base_url = str(http_request.base_url).rstrip('/')

        # Get managers
        task_manager = get_task_manager()
        project_manager = get_project_manager()

        # Step 1: Create Project entity first
        # This ensures the project exists before task execution begins
        logger.info("WorkflowAPI | Creating project entity before task submission")

        # Determine video type from request
        video_type_enum = VideoType.SHORT_DRAMA  # Default
        if request.video_type:
            try:
                video_type_enum = VideoType(request.video_type)
            except ValueError:
                logger.warning(f"WorkflowAPI | Invalid video_type: {request.video_type}, using default")

        project_create_request = CreateProjectRequest(
            name=f"Video Project {request.video_type or 'default'}",
            description=f"Generated from workflow API ({mode} mode)",
            video_type=video_type_enum,
            mode=GenerationMode.FULL
        )

        project = project_manager.create_project(project_create_request)
        project_id = project.id

        logger.info(
            f"WorkflowAPI | Project created | "
            f"project_id={project_id} | "
            f"name={project.name} | "
            f"video_type={project.video_type} | "
            f"status={project.status}"
        )

        # We need to capture the task_id in a closure
        # Since task_manager generates the ID during submit_task,
        # we'll create a holder for it
        workflow_task_id = None

        # Step 2: Define status synchronization callback
        # This callback will be called whenever the task status changes
        async def sync_task_to_project(task_id: str, status: TaskStatus, progress: int, result: Any, error: Any):
            """
            Synchronize task status to project entity.

            This ensures the project status stays in sync with the task status,
            so the frontend can display the correct state.
            """
            try:
                # Only sync if this is our task
                if task_id != workflow_task_id:
                    return

                logger.debug(
                    f"WorkflowAPI | Status callback triggered | "
                    f"task_id={task_id} | "
                    f"project_id={project_id} | "
                    f"status={status} | "
                    f"progress={progress}"
                )

                # Sync basic status and progress
                success = project_manager.sync_task_status(project_id, status, progress)
                if not success:
                    logger.warning(f"WorkflowAPI | Failed to sync status | project_id={project_id} | task_id={task_id}")
                    return

                logger.info(
                    f"WorkflowAPI | Status synced to project | "
                    f"project_id={project_id} | "
                    f"status={status} | "
                    f"progress={progress}"
                )

                # Handle COMPLETED status - update video metadata
                if status == TaskStatus.COMPLETED and result:
                    logger.info(f"WorkflowAPI | Task completed, updating project metadata | project_id={project_id}")

                    # Extract metadata from result (ensure result is dict)
                    if isinstance(result, dict):
                        video_path = result.get('video_path')
                        duration = result.get('duration')
                        scene_count = result.get('scene_count')
                        character_count = result.get('character_count')

                        logger.debug(
                            f"WorkflowAPI | Extracted result metadata | "
                            f"video_path={video_path} | "
                            f"duration={duration} | "
                            f"scene_count={scene_count} | "
                            f"character_count={character_count}"
                        )

                        # Update project with result data
                        success = project_manager.update_project_from_task_result(
                            project_id=project_id,
                            video_path=video_path,
                            duration=duration,
                            scene_count=scene_count,
                            character_count=character_count
                        )

                        if success:
                            logger.info(
                                f"WorkflowAPI | Project metadata updated successfully | "
                                f"project_id={project_id} | "
                                f"video_path={video_path}"
                            )
                        else:
                            logger.error(
                                f"WorkflowAPI | Failed to update project metadata | "
                                f"project_id={project_id}"
                            )
                    else:
                        logger.warning(
                            f"WorkflowAPI | Result is not a dict, skipping metadata update | "
                            f"project_id={project_id} | "
                            f"result_type={type(result).__name__}"
                        )

                # Handle FAILED status - sync error message
                elif status == TaskStatus.FAILED and error:
                    # Extract error message (ensure error is dict)
                    if isinstance(error, dict):
                        error_type = error.get('type', 'unknown')
                        logger.warning(
                            f"WorkflowAPI | Task failed, syncing error to project | "
                            f"project_id={project_id} | "
                            f"error_type={error_type}"
                        )

                        error_message = error.get('message', 'Unknown error')
                        if error.get('service'):
                            error_message = f"[{error['service']}] {error_message}"

                        # Update project with error
                        success = project_manager.update_project_from_task_result(
                            project_id=project_id,
                            error_message=error_message
                        )

                        if success:
                            logger.info(
                                f"WorkflowAPI | Error message synced to project | "
                                f"project_id={project_id}"
                            )
                        else:
                            logger.error(
                                f"WorkflowAPI | Failed to sync error message | "
                                f"project_id={project_id}"
                            )
                    else:
                        # Fallback: use str representation if error is not a dict
                        error_message = str(error) if error else 'Unknown error'
                        logger.warning(
                            f"WorkflowAPI | Error is not a dict, using string representation | "
                            f"project_id={project_id} | "
                            f"error_type={type(error).__name__}"
                        )

                        project_manager.update_project_from_task_result(
                            project_id=project_id,
                            error_message=error_message
                        )

            except Exception as e:
                # Don't let callback errors crash the main workflow
                logger.error(
                    f"WorkflowAPI | Error in status callback | "
                    f"project_id={project_id} | "
                    f"task_id={task_id} | "
                    f"error={e}",
                    exc_info=True
                )

        # Step 3: Register the callback with task manager
        task_manager.register_status_callback(sync_task_to_project)
        logger.info(f"WorkflowAPI | Registered status callback for project {project_id}")

        # Define workflow task
        async def workflow_task():
            # Use the task_id that was set after submission
            nonlocal workflow_task_id
            
            # Create progress callback that updates task status
            async def progress_callback(progress: float, message: str = ""):
                if workflow_task_id:
                    try:
                        await task_manager._update_task_status(
                            workflow_task_id,
                            TaskStatus.PROCESSING,
                            progress=int(progress),
                            message=message
                        )
                    except Exception as e:
                        logger.warning(f"WorkflowAPI | Failed to update progress | task_id={workflow_task_id} | error={e}")
            
            workflow_service = get_workflow_service()
            result = await workflow_service.execute_workflow(
                task_id=workflow_task_id,
                script=request.script,
                character_images=request.character_images,
                scene_images=request.scene_images,
                config=request.config,
                video_type=request.video_type,
                video_subtype=request.video_subtype,
                progress_callback=progress_callback,
                base_url=base_url
            )
            return result.dict()
        
        # Submit task
        task_id = await task_manager.submit_task(
            workflow_task,
            task_type="workflow"
        )

        # Set the task_id for the closure
        workflow_task_id = task_id

        # Step 4: Update project with task_id association
        # This links the project to the task for tracking
        project.task_id = task_id
        project_manager._write_project_file(project)

        logger.info(
            f"WorkflowAPI | Workflow task submitted | "
            f"task_id={task_id} | "
            f"project_id={project_id} | "
            f"mode={mode}"
        )

        return WorkflowGenerationResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message=f"Workflow generation task submitted (mode: {mode}). Project ID: {project_id}. Poll /api/v1/tasks/{task_id} for status."
        )
        
    except Exception as e:
        logger.exception(f"WorkflowAPI | Failed to submit workflow task | error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit workflow task: {str(e)}"
        )


@router.post("/quick-generate", response_model=WorkflowGenerationResponse, summary="Quick Mode Video Generation")
async def generate_quick_workflow(request: QuickModeWorkflowRequest, http_request: Request):
    """
    Generate video from pre-uploaded scene images (Quick Mode).

    This endpoint bypasses script parsing and image generation, directly generating
    videos from user-provided images with per-scene configuration.

    **Quick Mode Workflow:**
    1. User uploads images (scene_001.png, scene_002.png, etc.)
    2. User configures per-scene parameters (duration, prompt, camera motion)
    3. System generates videos directly from images
    4. System composes final video with transitions

    **Request Format:**
    ```json
    {
      "mode": "quick",
      "scenes": [
        {
          "scene_id": "scene_001",
          "image": "base64_encoded_image_or_url",
          "duration": 5,
          "prompt": "Camera slowly pans across the scene",
          "camera_motion": "pan",
          "motion_strength": 0.7
        },
        {
          "scene_id": "scene_002",
          "image": "base64_encoded_image_or_url",
          "duration": 7,
          "prompt": "Static shot with subtle movement",
          "camera_motion": "static",
          "motion_strength": 0.3
        }
      ],
      "config": {
        "video_fps": 30,
        "add_transitions": true
      }
    }
    ```

    **Returns:**
    - Task ID for polling status
    - Initial task status

    **Workflow:**
    1. Submit quick mode request → Get task_id
    2. Poll `/api/v1/tasks/{task_id}` for status and progress
    3. When status="completed", get video_url and assets from result
    4. Access assets via `/api/v1/workflow/assets/{task_id}/{asset_type}/{filename}`
    """
    logger.info(
        f"WorkflowAPI | Quick mode request | "
        f"scene_count={len(request.scenes)}"
    )

    try:
        # Get base URL from request
        base_url = str(http_request.base_url).rstrip('/')

        # Get managers
        task_manager = get_task_manager()
        project_manager = get_project_manager()

        # Step 1: Create Project entity for quick mode
        logger.info("WorkflowAPI | Creating project entity for quick mode before task submission")

        project_create_request = CreateProjectRequest(
            name=f"Quick Mode Video ({len(request.scenes)} scenes)",
            description=f"Generated from quick mode workflow API",
            video_type=VideoType.SHORT_DRAMA,  # Default for quick mode
            mode=GenerationMode.QUICK
        )

        project = project_manager.create_project(project_create_request)
        project_id = project.id

        logger.info(
            f"WorkflowAPI | Quick mode project created | "
            f"project_id={project_id} | "
            f"name={project.name} | "
            f"scene_count={len(request.scenes)} | "
            f"status={project.status}"
        )

        # Task ID holder
        workflow_task_id = None

        # Step 2: Define status synchronization callback for quick mode
        async def sync_quick_task_to_project(task_id: str, status: TaskStatus, progress: int, result: Any, error: Any):
            """Synchronize quick mode task status to project entity."""
            try:
                # Only sync if this is our task
                if task_id != workflow_task_id:
                    return

                logger.debug(
                    f"WorkflowAPI | Quick mode status callback | "
                    f"task_id={task_id} | "
                    f"project_id={project_id} | "
                    f"status={status} | "
                    f"progress={progress}"
                )

                # Sync basic status and progress
                success = project_manager.sync_task_status(project_id, status, progress)
                if not success:
                    logger.warning(f"WorkflowAPI | Failed to sync quick mode status | project_id={project_id}")
                    return

                logger.info(
                    f"WorkflowAPI | Quick mode status synced | "
                    f"project_id={project_id} | "
                    f"status={status} | "
                    f"progress={progress}"
                )

                # Handle COMPLETED status
                if status == TaskStatus.COMPLETED and result:
                    logger.info(f"WorkflowAPI | Quick mode completed, updating metadata | project_id={project_id}")

                    # Extract metadata from result (ensure result is dict)
                    if isinstance(result, dict):
                        video_path = result.get('video_path')
                        duration = result.get('duration')
                        scene_count = result.get('scene_count')

                        logger.debug(
                            f"WorkflowAPI | Quick mode result | "
                            f"video_path={video_path} | "
                            f"duration={duration} | "
                            f"scene_count={scene_count}"
                        )

                        success = project_manager.update_project_from_task_result(
                            project_id=project_id,
                            video_path=video_path,
                            duration=duration,
                            scene_count=scene_count,
                            character_count=0  # Quick mode doesn't have characters
                        )

                        if success:
                            logger.info(f"WorkflowAPI | Quick mode metadata updated | project_id={project_id}")
                        else:
                            logger.error(f"WorkflowAPI | Failed to update quick mode metadata | project_id={project_id}")
                    else:
                        logger.warning(
                            f"WorkflowAPI | Quick mode result is not a dict | "
                            f"project_id={project_id} | "
                            f"result_type={type(result).__name__}"
                        )

                # Handle FAILED status
                elif status == TaskStatus.FAILED and error:
                    # Extract error message (ensure error is dict)
                    if isinstance(error, dict):
                        error_type = error.get('message', 'unknown')
                        logger.warning(
                            f"WorkflowAPI | Quick mode failed | "
                            f"project_id={project_id} | "
                            f"error={error_type}"
                        )

                        error_message = error.get('message', 'Unknown error')
                        if error.get('service'):
                            error_message = f"[{error['service']}] {error_message}"

                        success = project_manager.update_project_from_task_result(
                            project_id=project_id,
                            error_message=error_message
                        )

                        if success:
                            logger.info(f"WorkflowAPI | Quick mode error synced | project_id={project_id}")
                    else:
                        # Fallback: use str representation if error is not a dict
                        error_message = str(error) if error else 'Unknown error'
                        logger.warning(
                            f"WorkflowAPI | Quick mode error is not a dict | "
                            f"project_id={project_id} | "
                            f"error_type={type(error).__name__}"
                        )

                        project_manager.update_project_from_task_result(
                            project_id=project_id,
                            error_message=error_message
                        )

            except Exception as e:
                logger.error(
                    f"WorkflowAPI | Error in quick mode callback | "
                    f"project_id={project_id} | "
                    f"error={e}",
                    exc_info=True
                )

        # Step 3: Register callback
        task_manager.register_status_callback(sync_quick_task_to_project)
        logger.info(f"WorkflowAPI | Registered quick mode callback for project {project_id}")

        # Define quick mode workflow task
        async def quick_workflow_task():
            nonlocal workflow_task_id

            # Create progress callback
            async def progress_callback(progress: float, message: str = ""):
                if workflow_task_id:
                    try:
                        await task_manager._update_task_status(
                            workflow_task_id,
                            TaskStatus.PROCESSING,
                            progress=int(progress),
                            message=message
                        )
                    except Exception as e:
                        logger.warning(f"WorkflowAPI | Failed to update progress | task_id={workflow_task_id} | error={e}")

            # Execute quick mode workflow
            quick_mode_service = get_quick_mode_service()
            result = await quick_mode_service.execute_quick_workflow(
                task_id=workflow_task_id,
                scenes_config=request.scenes,
                config=request.config,
                progress_callback=progress_callback,
                base_url=base_url
            )
            return result.dict()

        # Submit task
        task_id = await task_manager.submit_task(
            quick_workflow_task,
            task_type="quick_workflow"
        )

        # Set task_id for closure
        workflow_task_id = task_id

        # Step 4: Update project with task_id association
        project.task_id = task_id
        project_manager._write_project_file(project)

        logger.info(
            f"WorkflowAPI | Quick mode task submitted | "
            f"task_id={task_id} | "
            f"project_id={project_id} | "
            f"scene_count={len(request.scenes)}"
        )

        return WorkflowGenerationResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message=f"Quick mode workflow task submitted ({len(request.scenes)} scenes). Project ID: {project_id}. Poll /api/v1/tasks/{task_id} for status."
        )

    except Exception as e:
        logger.exception(f"WorkflowAPI | Failed to submit quick mode task | error={e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit quick mode task: {str(e)}"
        )


@router.get(
    "/assets/{task_id}/{asset_type}/{filename}",
    summary="Get Workflow Asset",
    response_class=FileResponse
)
async def get_workflow_asset(task_id: str, asset_type: str, filename: str):
    """
    Get a specific asset from a workflow generation task.
    
    **Asset Types:**
    - `character_references` - Character reference images
    - `images` - Scene images
    - `videos` - Individual scene videos
    - `final` - Final composed video and metadata
    
    **Example:**
    ```
    GET /api/v1/workflow/assets/wf_abc123/final/workflow_wf_abc123.mp4
    GET /api/v1/workflow/assets/wf_abc123/images/scene_001_20260111_123456.png
    GET /api/v1/workflow/assets/wf_abc123/character_references/Alice_front.png
    ```
    
    **Returns:**
    - File content with appropriate content type
    - 404 if asset not found
    """
    logger.debug(f"WorkflowAPI | Asset request | task_id={task_id} | type={asset_type} | file={filename}")
    
    try:
        asset_manager = get_asset_manager()
        asset_path = asset_manager.get_asset_path(task_id, asset_type, filename)
        
        if asset_path is None or not asset_path.exists():
            logger.warning(f"WorkflowAPI | Asset not found | task_id={task_id} | type={asset_type} | file={filename}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset not found: {filename}"
            )
        
        logger.debug(f"WorkflowAPI | Serving asset | path={asset_path} | size={asset_path.stat().st_size}")

        # Verify file is readable and not locked
        try:
            with open(asset_path, 'rb') as f:
                # Just read a small chunk to verify file is accessible
                f.read(1)
        except Exception as e:
            logger.error(f"WorkflowAPI | File is not accessible | path={asset_path} | error={e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"File is currently being written to: {filename}. Please try again in a moment."
            )

        # Determine media type
        suffix = asset_path.suffix.lower()
        media_type_map = {
            '.mp4': 'video/mp4',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.webm': 'video/webm',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.webp': 'image/webp',
            '.json': 'application/json',
        }
        media_type = media_type_map.get(suffix, 'application/octet-stream')
        
        return FileResponse(
            path=str(asset_path),
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WorkflowAPI | Error serving asset | task_id={task_id} | error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error serving asset: {str(e)}"
        )


@router.api_route(
    "/cleanup",
    methods=["GET", "POST"],
    summary="Cleanup Old Workflow Assets",
    include_in_schema=False  # Admin endpoint, hide from public docs
)
async def cleanup_old_assets(max_age_hours: int = 24, include_temp_projects: bool = False):
    """
    Clean up old workflow assets (admin endpoint).
    
    **Query Parameters:**
    - `max_age_hours`: Maximum age in hours before cleanup (default: 24)
    - `include_temp_projects`: also delete `backend/temp_projects/workflow_*`
      directories (pass 0 to remove them all)
    
    **Returns:**
    - Number of directories cleaned up
    """
    logger.info(
        f"WorkflowAPI | Cleanup requested | max_age_hours={max_age_hours} | "
        f"include_temp_projects={include_temp_projects}"
    )
    
    try:
        asset_manager = get_asset_manager()
        cleaned_count = asset_manager.cleanup_old_assets(max_age_hours=max_age_hours)

        temp_removed = 0
        if include_temp_projects:
            from backend.core.temp_project_manager import get_temp_project_manager
            from utils.blocking import run_blocking

            temp_removed = await run_blocking(
                get_temp_project_manager().cleanup_old_projects, max_age_hours
            )
        
        logger.info(f"WorkflowAPI | Cleanup completed | cleaned={cleaned_count}")
        
        return {
            "success": True,
            "cleaned_count": cleaned_count,
            "temp_projects_removed": temp_removed,
            "message": (
                f"Cleaned up {cleaned_count} old workflow asset directories and "
                f"{temp_removed} temporary project directories"
            )
        }
        
    except Exception as e:
        logger.error(f"WorkflowAPI | Cleanup failed | error={e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cleanup failed: {str(e)}"
        )

