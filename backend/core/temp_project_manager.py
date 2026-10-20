"""Temporary Project Manager

This module manages creation and configuration of temporary project structures
for workflow-based video generation.
"""
import yaml
import base64
import httpx
import asyncio
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

from backend.core.models import WorkflowConfig
from backend.utils.logger import get_logger
from backend.utils.log_helpers import truncate_base64

logger = get_logger(__name__)


class TempProjectManager:
    """Manages temporary project structures for workflows"""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize temporary project manager
        
        Args:
            base_dir: Base directory for temporary projects (default: backend/temp_projects)
        """
        if base_dir is None:
            base_dir = Path(__file__).parent.parent / "temp_projects"
        
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"TempProjectManager initialized | base_dir={self.base_dir}")
    
    def cleanup_old_projects(self, max_age_hours: int = 12) -> int:
        """Delete temporary project directories older than ``max_age_hours``.

        Each workflow run creates ``backend/temp_projects/workflow_*`` containing
        generated images and videos. Nothing used to remove them, so every run
        (including abandoned E2E runs) left the directory behind forever.

        Args:
            max_age_hours: Maximum age in hours before a directory is removed.

        Returns:
            Number of removed directories.
        """
        import shutil
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0

        try:
            for path in self.base_dir.iterdir():
                if not path.is_dir() or not path.name.startswith("workflow_"):
                    continue
                try:
                    modified = datetime.fromtimestamp(path.stat().st_mtime)
                except OSError:
                    continue
                if modified >= cutoff:
                    continue
                try:
                    shutil.rmtree(path)
                    removed += 1
                    logger.debug(
                        f"TempProjectManager | Removed temp project | "
                        f"path={path} | age={(datetime.now() - modified).total_seconds() / 3600:.1f}h"
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"TempProjectManager | Failed to remove temp project | "
                        f"path={path} | error={e}"
                    )
        except FileNotFoundError:
            return removed
        except Exception as e:  # noqa: BLE001
            logger.error(f"TempProjectManager | Cleanup failed | error={e}")
            return removed

        if removed:
            logger.info(
                f"TempProjectManager | Cleanup completed | removed={removed} "
                f"directories older than {max_age_hours}h"
            )
        return removed

    async def create_temp_project(
        self,
        task_id: str,
        script: str,
        config: Optional[WorkflowConfig] = None,
        character_images: Optional[Dict[str, str]] = None,
        scene_images: Optional[Dict[str, str]] = None,
        video_type: Optional[str] = None,
        video_subtype: Optional[str] = None
    ) -> tuple[Path, Dict[str, str]]:
        """
        Create a temporary project structure

        Args:
            task_id: Unique task identifier
            script: Script text content
            config: Workflow configuration
            character_images: Character name -> base64/url mapping
            scene_images: Scene ID -> base64/url mapping
            video_type: Video type (news_broadcast, anime, movie, short_drama)
            video_subtype: Video subtype (varies by type)

        Returns:
            Tuple of (project_path, saved_character_images_dict)
            - project_path: Path to created project directory
            - saved_character_images_dict: Character name -> saved file path mapping
        """
        logger.info(f"TempProjectManager | Creating temp project | task_id={task_id}")
        
        # Create project directory
        project_dir = self.base_dir / task_id
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"TempProjectManager | Created project directory | path={project_dir}")
        
        # Create subdirectories
        (project_dir / "characters").mkdir(exist_ok=True)
        (project_dir / "scenes").mkdir(exist_ok=True)
        (project_dir / "output").mkdir(exist_ok=True)
        (project_dir / "output" / "character_references").mkdir(exist_ok=True)
        (project_dir / "output" / "images").mkdir(exist_ok=True)
        (project_dir / "output" / "videos").mkdir(exist_ok=True)
        (project_dir / "output" / "final").mkdir(exist_ok=True)
        logger.debug(f"TempProjectManager | Created subdirectories")
        
        # Save script
        script_path = project_dir / "script.yaml"
        
        # Validate YAML format before saving
        try:
            yaml_data = yaml.safe_load(script)
            logger.debug(f"TempProjectManager | Script validation passed | is_yaml=True")
            
            # Check required fields
            if not isinstance(yaml_data, dict):
                logger.error("TempProjectManager | Script validation failed | reason=not_dict")
                raise ValueError("Script must be a valid YAML dictionary")
            
            if 'title' not in yaml_data:
                logger.error("TempProjectManager | Script validation failed | reason=missing_title")
                raise ValueError("Script missing required field: title")
            
            if 'scenes' not in yaml_data or not isinstance(yaml_data['scenes'], list):
                logger.error("TempProjectManager | Script validation failed | reason=missing_or_invalid_scenes")
                raise ValueError("Script missing required field: scenes (must be a list)")
            
            if not yaml_data['scenes']:
                logger.error("TempProjectManager | Script validation failed | reason=empty_scenes")
                raise ValueError("Script must have at least one scene")
            
            logger.info(
                f"TempProjectManager | Script validated | "
                f"title={yaml_data.get('title')} | "
                f"scenes={len(yaml_data.get('scenes', []))} | "
                f"characters={len(yaml_data.get('characters', []))}"
            )
            
        except yaml.YAMLError as e:
            logger.error(f"TempProjectManager | Invalid YAML script | error={e}")
            raise ValueError(f"Invalid YAML format in script: {str(e)}")
        
        script_path.write_text(script, encoding='utf-8')
        logger.info(f"TempProjectManager | Saved script | path={script_path} | size={len(script)} chars")
        
        # Generate and save config
        config_path = project_dir / "config.yaml"
        config_dict = self._generate_config_dict(task_id, config, video_type, video_subtype)
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"TempProjectManager | Saved config | path={config_path}")
        
        # Track saved character image paths for return
        saved_character_images = {}
        
        # Save character images if provided
        if character_images:
            logger.info(f"TempProjectManager | Saving custom character images | count={len(character_images)}")
            logger.debug(f"TempProjectManager | Character names | names={list(character_images.keys())}")
            for char_name, image_data in character_images.items():
                saved_path = project_dir / "characters" / f"{self._sanitize_filename(char_name)}.png"
                
                # Log with truncated base64
                image_preview = truncate_base64(image_data, max_length=40)
                logger.debug(
                    f"TempProjectManager | Saving character image | "
                    f"character={char_name} | "
                    f"data={image_preview}"
                )
                
                await self._save_image(
                    image_data,
                    saved_path,
                    f"character_{char_name}"
                )
                # Store the absolute path for later use
                saved_character_images[char_name] = str(saved_path.absolute())
                logger.info(
                    f"TempProjectManager | Saved custom character image | "
                    f"character={char_name} | path={saved_path}"
                )
        
        # Save scene images if provided
        if scene_images:
            logger.info(f"TempProjectManager | Saving scene images | count={len(scene_images)}")
            logger.debug(f"TempProjectManager | Scene IDs | ids={list(scene_images.keys())}")
            for scene_id, image_data in scene_images.items():
                # Log with truncated base64
                image_preview = truncate_base64(image_data, max_length=40)
                logger.debug(
                    f"TempProjectManager | Saving scene image | "
                    f"scene_id={scene_id} | "
                    f"data={image_preview}"
                )
                
                await self._save_image(
                    image_data,
                    project_dir / "scenes" / f"{self._sanitize_filename(scene_id)}.png",
                    f"scene_{scene_id}"
                )
        
        logger.info(
            f"TempProjectManager | Temp project created successfully | "
            f"path={project_dir} | "
            f"custom_character_images={len(saved_character_images)}"
        )
        
        return project_dir, saved_character_images
    
    def _generate_config_dict(
        self,
        task_id: str,
        config: Optional[WorkflowConfig],
        video_type: Optional[str] = None,
        video_subtype: Optional[str] = None
    ) -> Dict:
        """
        Generate project configuration dictionary

        Args:
            task_id: Task identifier
            config: Workflow configuration
            video_type: Video type (news_broadcast, anime, movie, short_drama)
            video_subtype: Video subtype (varies by type)

        Returns:
            Configuration dictionary for YAML
        """
        logger.debug(f"TempProjectManager | Generating config dict | task_id={task_id}")

        # Use defaults if config not provided
        if config is None:
            config = WorkflowConfig()

        config_dict = {
            "project": {
                "name": f"workflow_{task_id}",
                "description": f"Workflow-generated project for task {task_id}",
                "author": "Workflow API",
                "version": "1.0"
            },
            "video_type": {
                "type": video_type or "short_drama",
                "subtype": video_subtype or "modern_drama",
                "description": None
            },
            "script": {
                "file": "script.yaml",
                "encoding": "utf-8"
            },
            "characters": {
                "enable_references": config.enable_character_references,
                "reference_mode": "single_multi_view",
                "art_style": "realistic"
            },
            "image": {
                "service": "doubao",
                "max_concurrent": config.max_concurrent_requests,
                "width": config.image_width,
                "height": config.image_height,
                "quality": "high",
                "cfg_scale": config.image_cfg_scale or 7.5,
                "steps": config.image_steps or 50,
                "enable_image_to_image": True,
                "reference_weight": 0.7
            },
            "video": {
                "service": "veo3",
                "max_concurrent": min(config.max_concurrent_requests, 2),
                "fps": config.video_fps,
                "resolution": f"{config.image_width}x{config.image_height}",
                "motion_strength": config.video_motion_strength,
                "model": "veo_3_1"
            },
            "composer": {
                "add_transitions": config.add_transitions,
                "transition_type": "fade",
                "transition_duration": config.transition_duration,
                "fps": config.video_fps,
                "preset": "medium",
                "threads": 4,
                "bgm": {
                    "enabled": False,
                    "volume": config.bgm_volume
                },
                "subtitles": {
                    "enabled": config.add_subtitles
                }
            },
            "output": {
                "directory": "output",
                "filename": f"workflow_{task_id}.mp4",
                "save_intermediate": True,
                "metadata": {
                    "enabled": True,
                    "format": "json"
                }
            },
            "performance": {
                "max_concurrent_requests": config.max_concurrent_requests,
                "enable_checkpoints": False,
                "checkpoint_interval": 5
            },
            "api_keys": {},
            "enable_global_progress_bar": False
        }
        
        logger.debug(f"TempProjectManager | Config dict generated")
        return config_dict
    
    async def _save_image(
        self,
        image_data: str,
        output_path: Path,
        image_identifier: str
    ) -> None:
        """
        Save image from base64 or URL
        
        Args:
            image_data: Base64 encoded image or URL
            output_path: Path to save the image
            image_identifier: Identifier for logging
        """
        try:
            if image_data.startswith("http://") or image_data.startswith("https://"):
                # Download from URL with retry logic
                logger.debug(f"TempProjectManager | Downloading image from URL | id={image_identifier} | url={image_data[:100]}...")
                image_bytes = await self._download_image_with_retry(image_data, image_identifier)
                output_path.write_bytes(image_bytes)
                logger.info(f"TempProjectManager | Image downloaded successfully | id={image_identifier} | size={len(image_bytes)} bytes")
            else:
                # Decode from base64
                data_preview = truncate_base64(image_data, max_length=40)
                logger.debug(f"TempProjectManager | Decoding base64 image | id={image_identifier} | data={data_preview}")
                
                # Remove data URL prefix if present
                if ',' in image_data and image_data.startswith('data:'):
                    image_data = image_data.split(',', 1)[1]
                
                image_bytes = base64.b64decode(image_data)
                output_path.write_bytes(image_bytes)
                logger.info(f"TempProjectManager | Image decoded successfully | id={image_identifier} | size={len(image_bytes)} bytes")
        
        except base64.binascii.Error as e:
            logger.error(f"TempProjectManager | Invalid base64 image data | id={image_identifier} | error={e}")
            raise ValueError(f"Invalid base64 image data: {e}")
        except ValueError:
            # Re-raise ValueError (from download failures)
            raise
        except Exception as e:
            logger.error(f"TempProjectManager | Failed to save image | id={image_identifier} | error={type(e).__name__}: {e}")
            raise ValueError(f"Failed to save image: {type(e).__name__}: {e}")
    
    async def _download_image_with_retry(
        self,
        url: str,
        image_identifier: str,
        max_retries: int = 3
    ) -> bytes:
        """
        Download image from URL with retry logic
        
        Args:
            url: Image URL to download
            image_identifier: Identifier for logging
            max_retries: Maximum number of retry attempts
            
        Returns:
            Downloaded image bytes
            
        Raises:
            ValueError: If download fails after all retries
        """
        last_error = None
        
        # Try without proxy first (trust_env=False) - better for CDN URLs
        for attempt in range(max_retries):
            try:
                logger.debug(f"TempProjectManager | Download attempt {attempt + 1}/{max_retries} (no proxy) | id={image_identifier}")
                async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    logger.debug(f"TempProjectManager | Download successful | id={image_identifier} | attempt={attempt + 1}")
                    return response.content
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
                last_error = e
                logger.warning(
                    f"TempProjectManager | Download attempt {attempt + 1}/{max_retries} failed (no proxy) | "
                    f"id={image_identifier} | error={type(e).__name__}: {str(e)[:100]}"
                )
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    wait_time = 2 ** attempt
                    logger.debug(f"TempProjectManager | Waiting {wait_time}s before retry | id={image_identifier}")
                    await asyncio.sleep(wait_time)
        
        # If all retries without proxy failed, try once with proxy (trust_env=True)
        try:
            logger.debug(f"TempProjectManager | Final attempt with proxy enabled | id={image_identifier}")
            async with httpx.AsyncClient(timeout=30.0, trust_env=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                logger.info(f"TempProjectManager | Download successful with proxy | id={image_identifier}")
                return response.content
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as e:
            logger.error(
                f"TempProjectManager | All download attempts failed | id={image_identifier} | "
                f"url={url[:100]} | last_error={type(e).__name__}: {str(e)[:200]}"
            )
            raise ValueError(
                f"Failed to download image from {url[:100]}... after {max_retries + 1} attempts. "
                f"Last error: {type(e).__name__}: {str(e)[:200]}. "
                f"Please check your network connection or proxy settings."
            )
    
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
_temp_project_manager_instance: Optional[TempProjectManager] = None


def get_temp_project_manager() -> TempProjectManager:
    """
    Get the singleton TempProjectManager instance
    
    Returns:
        TempProjectManager instance
    """
    global _temp_project_manager_instance
    
    if _temp_project_manager_instance is None:
        _temp_project_manager_instance = TempProjectManager()
    
    return _temp_project_manager_instance

