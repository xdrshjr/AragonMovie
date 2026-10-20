"""Workflow Service

This module provides the core workflow orchestration service that bridges
the backend API and CLI-based video generation logic.
"""
import sys
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Callable
from datetime import datetime

# Add project root to path for CLI imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.models import WorkflowConfig, WorkflowResult, AssetsManifest
from backend.core.temp_project_manager import get_temp_project_manager
from backend.utils.asset_manager import get_asset_manager
from backend.utils.logger import get_logger
from backend.utils.log_helpers import format_image_dict_for_log, sanitize_log_dict
from backend.config import settings

# CLI imports
from core.project_manager import ProjectManager
from core.runner import ProjectRunner
from core.errors import ProjectError
from utils.blocking import run_blocking

logger = get_logger(__name__)


class WorkflowService:
    """Service for orchestrating CLI-based workflow generation"""
    
    def __init__(self):
        """Initialize workflow service"""
        self.temp_project_manager = get_temp_project_manager()
        self.asset_manager = get_asset_manager()
        self.project_manager = ProjectManager()
        logger.info("WorkflowService initialized")
    
    async def execute_workflow(
        self,
        task_id: str,
        script: str,
        character_images: Optional[Dict[str, str]] = None,
        scene_images: Optional[Dict[str, str]] = None,
        config: Optional[WorkflowConfig] = None,
        video_type: Optional[str] = None,
        video_subtype: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
        base_url: str = ""
    ) -> WorkflowResult:
        """
        Execute the complete workflow generation

        Args:
            task_id: Unique task identifier
            script: Polished script text
            character_images: Optional character name -> base64/url mapping
            scene_images: Optional scene ID -> image_path mapping
            config: Workflow configuration
            video_type: Video type (news_broadcast, anime, movie, short_drama)
            video_subtype: Video subtype (varies by type)
            progress_callback: Optional progress callback function
            base_url: Base URL for generating asset URLs

        Returns:
            WorkflowResult with video path and assets

        Raises:
            Exception: If workflow execution fails
        """
        start_time = time.time()
        
        # Determine mode
        mode = "with_images" if (character_images or scene_images) else "full_pipeline"
        logger.info(f"WorkflowService | Starting workflow | task_id={task_id} | mode={mode}")
        
        # Format images for logging (truncate base64)
        char_images_log = format_image_dict_for_log(character_images)
        scene_images_log = format_image_dict_for_log(scene_images)
        
        logger.debug(
            f"WorkflowService | Workflow input details | "
            f"task_id={task_id} | "
            f"script_length={len(script)} | "
            f"character_images_count={len(character_images) if character_images else 0} | "
            f"character_images_keys={list(character_images.keys()) if character_images else []} | "
            f"scene_images_count={len(scene_images) if scene_images else 0} | "
            f"scene_images_keys={list(scene_images.keys()) if scene_images else []} | "
            f"config={sanitize_log_dict(config.dict()) if config else 'default'}"
        )
        
        try:
            # Step 1: Create temporary project structure
            logger.info(f"WorkflowService | Creating temporary project | task_id={task_id}")
            if progress_callback:
                await progress_callback(5, "Creating project structure...")

            project_path, saved_character_images = await self.temp_project_manager.create_temp_project(
                task_id=task_id,
                script=script,
                config=config,
                character_images=character_images,
                scene_images=scene_images,
                video_type=video_type,
                video_subtype=video_subtype
            )
            logger.info(
                f"WorkflowService | Project created | "
                f"path={project_path} | "
                f"custom_character_images={len(saved_character_images)}"
            )
            
            # Build character_images config for orchestrator
            # This tells the character_reference_agent to generate modeling sheets based on custom images
            character_images_for_orchestrator = None
            if saved_character_images:
                character_images_for_orchestrator = {}
                for char_name, image_path in saved_character_images.items():
                    character_images_for_orchestrator[char_name] = {
                        'mode': 'load',
                        'images': [image_path]
                    }
                    logger.info(
                        f"WorkflowService | Configured custom character base image | "
                        f"character={char_name} | "
                        f"mode=load | "
                        f"base_image={image_path} | "
                        f"will_generate_modeling_sheet=True"
                    )
                logger.info(
                    f"WorkflowService | Built character images config for orchestrator | "
                    f"total={len(character_images_for_orchestrator)} characters | "
                    f"note=will generate modeling sheets from custom base images"
                )
            else:
                logger.info("WorkflowService | No custom character images provided, will use AI generation for modeling sheets")
            
            # Step 2: Load project configuration
            logger.info(f"WorkflowService | Loading project configuration | task_id={task_id}")
            logger.debug(f"WorkflowService | Project path | path={project_path}")
            if progress_callback:
                await progress_callback(10, "Loading project configuration...")
            
            # 同步文件 I/O 交给线程池，避免阻塞事件循环
            project_config, abs_path = await run_blocking(
                self.project_manager.load_project, project_path
            )
            logger.debug(f"WorkflowService | Project config loaded | path={abs_path}")
            
            # Step 3: Prepare scene images mapping for runner
            scene_images_mapping = None
            if scene_images:
                # Map scene IDs to actual file paths in the project
                scene_images_mapping = {}
                scenes_dir = project_path / "scenes"
                for scene_id, image_data in scene_images.items():
                    # The image was saved during project creation
                    # Find the actual file path
                    image_path = scenes_dir / f"{self._sanitize_filename(scene_id)}.png"
                    if image_path.exists():
                        scene_images_mapping[scene_id] = str(image_path)
                        logger.debug(f"WorkflowService | Mapped scene image | scene_id={scene_id} | path={image_path}")
                
                logger.info(f"WorkflowService | Prepared scene images mapping | count={len(scene_images_mapping)}")
            
            # Step 4: Create and run project runner
            logger.info(f"WorkflowService | Starting CLI runner | task_id={task_id}")
            if progress_callback:
                await progress_callback(15, "Starting video generation...")
            
            runner = ProjectRunner(project_config, abs_path)
            
            # Wrap progress callback to forward to task manager
            async def wrapped_progress(progress: float, message: str = ""):
                logger.debug(f"WorkflowService | Progress update | progress={progress:.1f}% | message={message}")
                if progress_callback:
                    # Map CLI progress (0-100) to API progress (15-95)
                    api_progress = 15 + (progress * 0.80)  # 15% to 95%
                    await progress_callback(api_progress, message)
            
            # Execute generation
            # Pass character_images_for_orchestrator to runner, which will forward to orchestrator
            logger.debug(
                f"WorkflowService | Starting video generation | "
                f"has_custom_character_images={character_images_for_orchestrator is not None} | "
                f"has_scene_images={scene_images_mapping is not None}"
            )
            
            video_path = await runner.run(
                progress_callback=wrapped_progress,
                scene_images=scene_images_mapping,
                character_images=character_images_for_orchestrator
            )
            
            logger.info(f"WorkflowService | Video generation completed | video_path={video_path}")
            
            # Step 5: Package assets
            logger.info(f"WorkflowService | Packaging assets | task_id={task_id}")
            if progress_callback:
                await progress_callback(95, "Packaging assets...")
            
            # 资源打包（复制文件 / 生成缩略图）同样是同步阻塞操作
            assets = await run_blocking(
                self.asset_manager.save_workflow_assets,
                task_id=task_id,
                project_path=project_path,
                video_path=video_path,
                base_url=base_url
            )
            
            # Step 6: Create result
            duration = time.time() - start_time
            
            # Extract metadata from runner
            scene_count = runner.generation_info.get('scene_count', 0)
            character_count = runner.generation_info.get('character_count', 0)
            
            # Build video URL
            video_filename = Path(video_path).name
            video_url = f"{base_url}/api/v1/workflow/assets/{task_id}/final/{video_filename}"
            
            result = WorkflowResult(
                video_url=video_url,
                video_path=str(video_path),
                metadata=runner.generation_info,
                assets=assets,
                duration=duration,
                scene_count=scene_count,
                character_count=character_count
            )
            
            logger.info(
                f"WorkflowService | Workflow completed successfully | "
                f"task_id={task_id} | "
                f"duration={duration:.2f}s | "
                f"scenes={scene_count} | "
                f"characters={character_count}"
            )
            
            if progress_callback:
                await progress_callback(100, "Workflow completed!")
            
            return result
            
        except ProjectError as e:
            logger.error(f"WorkflowService | Project error | task_id={task_id} | error={e}", exc_info=True)
            raise Exception(f"Project error: {str(e)}")
        except Exception as e:
            logger.error(f"WorkflowService | Workflow failed | task_id={task_id} | error={e}", exc_info=True)
            raise
    
    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a name for use as filename
        
        Args:
            name: Name to sanitize
            
        Returns:
            Sanitized filename
        """
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = name
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip('. ')
        
        # Limit length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        
        return sanitized or "unnamed"


# Singleton instance
_workflow_service_instance: Optional[WorkflowService] = None


def get_workflow_service() -> WorkflowService:
    """
    Get the singleton WorkflowService instance
    
    Returns:
        WorkflowService instance
    """
    global _workflow_service_instance
    
    if _workflow_service_instance is None:
        _workflow_service_instance = WorkflowService()
    
    return _workflow_service_instance

