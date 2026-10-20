"""FastAPI Backend Main Application

This module initializes the FastAPI application with all routers, middleware,
and configuration for the AI Movie Agent API.
"""
import sys
from pathlib import Path

# Add parent directory to path to import existing services
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import time

from backend.config import settings
from backend.utils.logger import setup_logging, get_logger
from backend.middleware.logging import LoggingMiddleware
from backend.middleware.error_handler import setup_exception_handlers
from backend.api.router import api_router

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    # Load runtime model settings (Settings UI / agent overrides) on top of .env
    from backend.core.settings_store import get_settings_store
    try:
        runtime_settings = get_settings_store().load_and_apply()
        logger.info(
            f"Runtime model settings loaded | file={get_settings_store().file_path}"
        )
        if runtime_settings.agent.enabled:
            logger.info(
                f"Agent assist enabled | provider={runtime_settings.agent.provider} "
                f"| model={runtime_settings.agent.model}"
            )
    except Exception as e:
        logger.warning(f"Runtime settings load failed, using .env defaults: {e}")

    logger.info("=" * 60)
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Server: {settings.host}:{settings.port}")
    logger.info(f"Log Level: {settings.log_level}")
    logger.info(f"Image Service: {settings.image_service_type}")

    # Log video service configuration based on selected type
    if settings.video_service_type == "veo3":
        logger.info(f"Video Service: Veo3 (model={settings.veo3_model})")
        logger.debug(f"  - Veo3 Base URL: {settings.veo3_base_url}")
        logger.debug(f"  - Veo3 Endpoint: {settings.veo3_endpoint}")
    elif settings.video_service_type == "sora2":
        logger.info(f"Video Service: Sora2 (model={settings.sora2_model})")
        logger.debug(f"  - Sora2 Base URL: {settings.sora2_base_url}")
        logger.debug(f"  - Sora2 Endpoint: {settings.sora2_endpoint}")
        logger.debug(f"  - Sora2 Default Size: {settings.sora2_default_size}")
        logger.debug(f"  - Sora2 Default Duration: {settings.sora2_default_duration}s")
        if settings.sora2_default_style:
            logger.debug(f"  - Sora2 Default Style: {settings.sora2_default_style}")
    elif settings.video_service_type == "ali_token_plan":
        logger.info(
            f"Video Service: Ali Token Plan (model={settings.ali_video_model})"
        )
        logger.debug(f"  - Ali Base URL: {settings.ali_token_plan_base_url}")
        logger.debug(f"  - Ali Endpoint: {settings.ali_video_endpoint}")
    else:
        logger.warning(f"Unknown video service type: {settings.video_service_type}")

    logger.info(f"Task Storage: {settings.task_storage_backend}")
    logger.info("=" * 60)

    # Create projects directory
    projects_dir = Path("backend/projects")
    projects_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Projects directory: {projects_dir.absolute()}")

    # Initialize project manager and register callback with task manager
    from backend.core.project_manager import get_project_manager
    from backend.core.task_manager import get_task_manager
    from backend.core.models import TaskStatus

    project_manager = get_project_manager()
    task_manager = get_task_manager()

    async def project_status_callback(task_id: str, status: TaskStatus, progress: int, result: any, error: any):
        """Callback to sync project status with task status

        ProjectManager is synchronous (JSON persistence + ffmpeg thumbnail
        generation, which shells out with a 30s timeout), so it must run in a
        worker thread - otherwise the event loop stalls and task polling stalls
        with it.
        """
        from utils.blocking import run_blocking

        try:
            # Find project by task_id
            project = await run_blocking(
                project_manager.get_project_by_task_id, task_id
            )
            if not project:
                return

            # Sync status and progress
            await run_blocking(
                project_manager.sync_task_status, project.id, status, progress
            )

            # Update project with result data if completed
            if status == TaskStatus.COMPLETED and result:
                video_path = result.get("video_path")
                duration = result.get("duration")
                scene_count = result.get("scene_count")
                character_count = result.get("character_count")

                # This is where the ffmpeg thumbnail is generated: keep it off
                # the event loop.
                await run_blocking(
                    project_manager.update_project_from_task_result,
                    project.id,
                    video_path=video_path,
                    duration=duration,
                    scene_count=scene_count,
                    character_count=character_count
                )

            # Update project with error message if failed
            elif status == TaskStatus.FAILED and error:
                error_message = error.get("message", str(error))
                await run_blocking(
                    project_manager.update_project_from_task_result,
                    project.id,
                    error_message=error_message
                )

        except Exception as e:
            logger.error(f"Error in project status callback: {e}")

    task_manager.register_status_callback(project_status_callback)
    logger.info("Project status callback registered")

    # BUG 14: start the task manager (abandoned-task watchdog) and clean up temp
    # project directories left behind by earlier runs.
    await task_manager.start()
    try:
        from backend.core.temp_project_manager import get_temp_project_manager
        from utils.blocking import run_blocking

        removed = await run_blocking(
            get_temp_project_manager().cleanup_old_projects,
            settings.temp_project_retention_hours,
        )
        if removed:
            logger.info(f"Startup cleanup removed {removed} stale temp project(s)")
    except Exception as e:  # noqa: BLE001 - cleanup must never block startup
        logger.warning(f"Startup temp-project cleanup failed: {e}")

    yield

    # Shutdown
    logger.info("Shutting down API server...")

    # Cancel running tasks, stop the abandoned-task watchdog and the TaskStore
    # cleanup loop (a bare stop_idle_sweeper() left the hourly loop dangling).
    try:
        await task_manager.stop()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to stop task manager cleanly: {e}")

    # Release the media worker pool used for blocking composition work
    from utils.blocking import shutdown_media_executor
    shutdown_media_executor(wait=False)

    logger.info("Cleanup completed")


# Initialize FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description=settings.api_description,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Setup exception handlers
setup_exception_handlers(app)

# Include API routers
app.include_router(api_router)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "name": settings.api_title,
        "version": settings.api_version,
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "rest_api": "/api/v1",
            "openai_compatible": "/v1"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": settings.api_title,
        "version": settings.api_version
    }


if __name__ == "__main__":
    import argparse
    import uvicorn
    import os
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Run AI Movie Agent API server")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG logging level"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (overrides --debug)"
    )
    parser.add_argument(
        "--host",
        default=settings.host,
        help=f"Host to bind to (default: {settings.host})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.port,
        help=f"Port to bind to (default: {settings.port})"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=True,
        help="Enable auto-reload on code changes (default: True)"
    )
    parser.add_argument(
        "--no-reload",
        dest="reload",
        action="store_false",
        help="Disable auto-reload"
    )
    
    args = parser.parse_args()
    
    # Determine log level
    if args.log_level:
        log_level = args.log_level
    elif args.debug:
        log_level = "DEBUG"
    else:
        log_level = settings.log_level
    
    # Update settings with CLI arguments
    settings.log_level = log_level
    
    # IMPORTANT: Set environment variable so child processes also get DEBUG level
    os.environ['LOG_LEVEL'] = log_level
    
    # Re-initialize logging with new level
    setup_logging(log_level=log_level)
    
    logger.info("=" * 60)
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Server: {args.host}:{args.port}")
    logger.info(f"Log Level: {log_level}")
    logger.info(f"Auto-reload: {args.reload}")
    logger.info(f"Image Service: {settings.image_service_type}")

    # Log video service configuration based on selected type
    if settings.video_service_type == "veo3":
        logger.info(f"Video Service: Veo3 (model={settings.veo3_model})")
    elif settings.video_service_type == "sora2":
        logger.info(f"Video Service: Sora2 (model={settings.sora2_model})")
    elif settings.video_service_type == "ali_token_plan":
        logger.info(
            f"Video Service: Ali Token Plan (model={settings.ali_video_model})"
        )
    else:
        logger.warning(f"Unknown video service type: {settings.video_service_type}")

    logger.info("=" * 60)
    
    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=log_level.lower()
    )

