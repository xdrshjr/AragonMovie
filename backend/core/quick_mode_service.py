"""Quick Mode Service

This module provides the quick mode workflow service that bypasses script parsing
and image generation, directly generating videos from user-uploaded images.
"""
import sys
import asyncio
import time
import base64
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any
from datetime import datetime

# Add project root to path for CLI imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.core.models import (
    QuickModeSceneConfig,
    QuickModeWorkflowRequest,
    WorkflowConfig,
    WorkflowResult,
    AssetsManifest,
    AssetInfo
)
from backend.utils.asset_manager import get_asset_manager
from backend.utils.logger import get_logger
from backend.config import settings

# CLI imports
from agents.orchestrator_agent import DramaGenerationOrchestrator
from models.script_models import Scene, Script
from core.errors import ProjectError

logger = get_logger(__name__)


class QuickModeService:
    """Service for orchestrating quick mode video generation"""

    def __init__(self):
        """Initialize quick mode service"""
        self.asset_manager = get_asset_manager()
        logger.info("QuickModeService initialized")

    async def execute_quick_workflow(
        self,
        task_id: str,
        scenes_config: List[QuickModeSceneConfig],
        config: Optional[WorkflowConfig] = None,
        progress_callback: Optional[Callable] = None,
        base_url: str = ""
    ) -> WorkflowResult:
        """
        Execute quick mode workflow - bypass script parsing and image generation

        Args:
            task_id: Unique task identifier
            scenes_config: List of scene configurations with images
            config: Workflow configuration (optional)
            progress_callback: Optional progress callback function
            base_url: Base URL for generating asset URLs

        Returns:
            WorkflowResult with video path and assets

        Raises:
            Exception: If workflow execution fails
        """
        start_time = time.time()

        logger.info(
            f"QuickModeService | Starting quick mode workflow | "
            f"task_id={task_id} | scene_count={len(scenes_config)}"
        )

        try:
            # Step 1: Create output directory for this task
            logger.info(f"QuickModeService | Creating output directory | task_id={task_id}")
            if progress_callback:
                await progress_callback(5, "Preparing workspace...")

            # Get task directory and create output subdirectory
            # AssetManager expects: temp_projects/{task_id}/output/...
            task_dir = self.asset_manager.get_task_directory(task_id)
            task_dir.mkdir(parents=True, exist_ok=True)

            # Orchestrator will create subdirectories inside this output_dir
            output_dir = task_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create images subdirectory for saving uploaded images
            images_dir = output_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # Step 2: Save uploaded images and prepare scene data
            logger.info(f"QuickModeService | Saving uploaded images | count={len(scenes_config)}")
            if progress_callback:
                await progress_callback(10, f"Saving {len(scenes_config)} images...")

            scene_image_paths = {}
            scene_params = {}

            for scene_config in scenes_config:
                # Save image to disk
                image_path = await self._save_scene_image(
                    scene_config.scene_id,
                    scene_config.image,
                    images_dir
                )
                scene_image_paths[scene_config.scene_id] = str(image_path)

                # Store scene parameters
                scene_params[scene_config.scene_id] = {
                    'duration': scene_config.duration,
                    'prompt': scene_config.prompt,
                    'camera_motion': scene_config.camera_motion,
                    'motion_strength': scene_config.motion_strength
                }

            logger.info(
                f"QuickModeService | Images saved | "
                f"task_id={task_id} | count={len(scene_image_paths)}"
            )

            # Step 3: Create minimal Scene objects for orchestrator
            logger.info(f"QuickModeService | Creating scene objects | count={len(scenes_config)}")
            scenes = []
            for scene_config in scenes_config:
                scene = Scene(
                    scene_id=scene_config.scene_id,
                    location="Quick Mode Scene",
                    time="day",
                    description=scene_config.prompt or "Quick mode generated scene",
                    characters=[],
                    dialogues=[],
                    duration=scene_config.duration
                )
                scenes.append(scene)

            # Step 4: Initialize orchestrator
            logger.info(f"QuickModeService | Initializing orchestrator | task_id={task_id}")

            # Build orchestrator config
            orchestrator_config = self._build_orchestrator_config(config)

            orchestrator = DramaGenerationOrchestrator(
                agent_id=f"quick_orchestrator_{task_id}",
                config=orchestrator_config,
                output_dir=output_dir
            )

            # Step 5: Execute quick mode generation
            logger.info(f"QuickModeService | Starting video generation | task_id={task_id}")
            if progress_callback:
                await progress_callback(15, "Generating videos from images...")

            # Create progress callback wrapper for orchestrator
            async def orchestrator_progress(progress: float, message: str = ""):
                # Map orchestrator progress (0-100) to our progress (15-95)
                mapped_progress = 15 + (progress * 0.80)
                if progress_callback:
                    await progress_callback(mapped_progress, message)

            output_filename = f"quick_mode_{task_id}.mp4"

            video_path = await orchestrator.execute_quick_mode(
                scenes_config=scenes,
                scene_image_paths=scene_image_paths,
                scene_params=scene_params,
                output_filename=output_filename,
                progress_callback=orchestrator_progress
            )

            logger.info(
                f"QuickModeService | Video generation completed | "
                f"task_id={task_id} | video_path={video_path}"
            )

            # Step 6: Verify video file is fully written and accessible
            logger.info(f"QuickModeService | Verifying video file | task_id={task_id} | path={video_path}")
            max_retries = 5
            for i in range(max_retries):
                try:
                    # Check if file exists and has content
                    if not Path(video_path).exists():
                        raise FileNotFoundError(f"Video file not found: {video_path}")

                    file_size = Path(video_path).stat().st_size
                    if file_size == 0:
                        raise ValueError(f"Video file is empty: {video_path}")

                    # Try to open and read the file to verify it's not locked
                    with open(video_path, 'rb') as f:
                        f.read(1024)  # Read first 1KB to verify accessibility

                    logger.info(f"QuickModeService | Video file verified | task_id={task_id} | size={file_size}")
                    break
                except Exception as e:
                    if i == max_retries - 1:
                        logger.error(f"QuickModeService | Failed to verify video file | task_id={task_id} | error={e}")
                        raise
                    logger.warning(f"QuickModeService | Video file not ready, retrying {i+1}/{max_retries} | task_id={task_id} | error={e}")
                    await asyncio.sleep(0.5)  # Wait 500ms before retry

            # Step 7: Build assets manifest
            if progress_callback:
                await progress_callback(95, "Building assets manifest...")

            assets = await self._build_assets_manifest(
                task_id=task_id,
                output_dir=output_dir,
                video_path=video_path,
                base_url=base_url
            )

            # Step 7: Calculate duration and build result
            duration = time.time() - start_time

            if progress_callback:
                await progress_callback(100, "Quick mode workflow completed!")

            logger.info(
                f"QuickModeService | Workflow completed | "
                f"task_id={task_id} | duration={duration:.2f}s | "
                f"scene_count={len(scenes_config)}"
            )

            # Build result
            result = WorkflowResult(
                video_url=f"{base_url}/api/v1/workflow/assets/{task_id}/final/{Path(video_path).name}",
                video_path=str(video_path),
                metadata={
                    'task_id': task_id,
                    'mode': 'quick',
                    'scene_count': len(scenes_config),
                    'duration': duration,
                    'timestamp': datetime.now().isoformat(),
                    'config': config.dict() if config else {}
                },
                assets=assets,
                duration=duration,
                scene_count=len(scenes_config),
                character_count=0  # No characters in quick mode
            )

            return result

        except Exception as e:
            logger.error(
                f"QuickModeService | Workflow failed | "
                f"task_id={task_id} | error={str(e)}",
                exc_info=True
            )
            raise

    async def _save_scene_image(
        self,
        scene_id: str,
        image_data: str,
        images_dir: Path
    ) -> Path:
        """
        Save scene image from base64 or URL to disk

        Args:
            scene_id: Scene identifier
            image_data: Base64 encoded image or URL
            images_dir: Directory to save images

        Returns:
            Path to saved image file
        """
        image_filename = f"{scene_id}.png"
        image_path = images_dir / image_filename

        try:
            # Check if it's a base64 string
            if image_data.startswith('data:image'):
                # Extract base64 data after comma
                base64_data = image_data.split(',', 1)[1]
            elif image_data.startswith('http://') or image_data.startswith('https://'):
                # Handle URL - download image
                import httpx
                async with httpx.AsyncClient() as client:
                    response = await client.get(image_data)
                    response.raise_for_status()
                    image_path.write_bytes(response.content)
                    logger.debug(f"QuickModeService | Downloaded image from URL | scene_id={scene_id}")
                    return image_path
            else:
                # Assume it's raw base64
                base64_data = image_data

            # Decode and save base64 image
            image_bytes = base64.b64decode(base64_data)
            image_path.write_bytes(image_bytes)

            logger.debug(
                f"QuickModeService | Image saved | "
                f"scene_id={scene_id} | path={image_path} | size={len(image_bytes)} bytes"
            )

            return image_path

        except Exception as e:
            logger.error(
                f"QuickModeService | Failed to save image | "
                f"scene_id={scene_id} | error={str(e)}"
            )
            raise ValueError(f"Failed to save image for {scene_id}: {str(e)}")

    def _build_orchestrator_config(self, config: Optional[WorkflowConfig]) -> Dict[str, Any]:
        """
        Build orchestrator configuration from workflow config

        Args:
            config: Workflow configuration

        Returns:
            Dict compatible with DramaGenerationOrchestrator
        """
        if not config:
            config = WorkflowConfig()

        return {
            'video': {
                'service': settings.video_service_type,
                'max_concurrent': settings.video_max_concurrent,
                'fps': config.video_fps,
                'resolution': f"{config.image_width}x{config.image_height}",
                'motion_strength': config.video_motion_strength,
            },
            'composer': {
                'add_transitions': config.add_transitions,
                'transition_duration': config.transition_duration,
                'fps': config.video_fps,
            },
            'enable_character_references': False,  # Disabled in quick mode
        }

    async def _build_assets_manifest(
        self,
        task_id: str,
        output_dir: Path,
        video_path: str,
        base_url: str
    ) -> AssetsManifest:
        """
        Build assets manifest for quick mode workflow

        Args:
            task_id: Task identifier
            output_dir: Output directory path
            video_path: Path to final video
            base_url: Base URL for asset URLs

        Returns:
            AssetsManifest with all generated assets
        """
        assets = AssetsManifest(
            character_references=[],  # No character references in quick mode
            scene_images=[],
            scene_videos=[],
            final_video=None,
            metadata_file=None
        )

        # Scene images
        images_dir = output_dir / "images"
        if images_dir.exists():
            for image_file in sorted(images_dir.glob("scene_*.png")):
                asset_info = AssetInfo(
                    filename=image_file.name,
                    url=f"{base_url}/api/v1/workflow/assets/{task_id}/images/{image_file.name}",
                    size_bytes=image_file.stat().st_size,
                    type="image/png",
                    path=str(image_file)
                )
                assets.scene_images.append(asset_info)

        # Scene videos
        videos_dir = output_dir / "videos"
        if videos_dir.exists():
            for video_file in sorted(videos_dir.glob("scene_*.mp4")):
                asset_info = AssetInfo(
                    filename=video_file.name,
                    url=f"{base_url}/api/v1/workflow/assets/{task_id}/videos/{video_file.name}",
                    size_bytes=video_file.stat().st_size,
                    type="video/mp4",
                    path=str(video_file)
                )
                assets.scene_videos.append(asset_info)

        # Final video
        video_file = Path(video_path)
        if video_file.exists():
            assets.final_video = AssetInfo(
                filename=video_file.name,
                url=f"{base_url}/api/v1/workflow/assets/{task_id}/final/{video_file.name}",
                size_bytes=video_file.stat().st_size,
                type="video/mp4",
                path=str(video_file)
            )

        # Metadata file
        metadata_file = video_file.with_suffix('.json')
        if metadata_file.exists():
            assets.metadata_file = AssetInfo(
                filename=metadata_file.name,
                url=f"{base_url}/api/v1/workflow/assets/{task_id}/final/{metadata_file.name}",
                size_bytes=metadata_file.stat().st_size,
                type="application/json",
                path=str(metadata_file)
            )

        return assets


# Singleton instance
_quick_mode_service: Optional[QuickModeService] = None


def get_quick_mode_service() -> QuickModeService:
    """Get or create the singleton QuickModeService instance"""
    global _quick_mode_service
    if _quick_mode_service is None:
        _quick_mode_service = QuickModeService()
    return _quick_mode_service
