"""
Configuration and Project Validators

Validates project structure, configuration, and dependencies.
"""

import os
from pathlib import Path
from typing import List, Tuple, Optional

from config.project_schema import ProjectConfig, CharacterReferenceImageConfig
from core.errors import (
    ScriptFileNotFoundError,
    CharacterImageNotFoundError,
    MissingAPIKeyError,
    InvalidProjectStructureError,
)


def validate_script_file(script_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate script file exists and is readable

    Args:
        script_path: Path to script file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not script_path.exists():
        return False, f"Script file not found: {script_path}"

    if not script_path.is_file():
        return False, f"Script path is not a file: {script_path}"

    if script_path.stat().st_size == 0:
        return False, f"Script file is empty: {script_path}"

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                return False, "Script file contains only whitespace"
    except Exception as e:
        return False, f"Cannot read script file: {e}"

    return True, None


def validate_character_images(
    character_config: CharacterReferenceImageConfig,
    character_name: str,
    base_path: Path
) -> Tuple[bool, Optional[str]]:
    """
    Validate character reference images exist when mode is 'load'

    Args:
        character_config: Character configuration
        character_name: Name of the character
        base_path: Project base path

    Returns:
        Tuple of (is_valid, error_message)
    """
    if character_config.mode != "load":
        # No validation needed for generate mode
        return True, None

    if not character_config.images:
        return False, f"Character '{character_name}': no images specified for mode='load'"

    missing_images = []
    for image_path_str in character_config.images:
        # Handle both absolute and relative paths
        image_path = Path(image_path_str)
        if not image_path.is_absolute():
            image_path = base_path / image_path_str

        if not image_path.exists():
            missing_images.append(str(image_path))

    if missing_images:
        return False, (
            f"Character '{character_name}': image files not found:\n  " +
            "\n  ".join(missing_images)
        )

    return True, None


def validate_project_structure(project_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate basic project folder structure

    Args:
        project_path: Path to project folder

    Returns:
        Tuple of (is_valid, list_of_missing_items)
    """
    if not project_path.exists():
        return False, ["Project folder does not exist"]

    if not project_path.is_dir():
        return False, ["Project path is not a directory"]

    missing = []

    # Check for config.yaml
    config_file = project_path / "config.yaml"
    if not config_file.exists():
        missing.append("config.yaml")

    return len(missing) == 0, missing


def validate_project_config(
    config: ProjectConfig,
    project_path: Path
) -> Tuple[bool, List[str]]:
    """
    Validate complete project configuration including file references

    Args:
        config: Project configuration
        project_path: Project base path

    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []

    # Validate script file
    script_path = Path(config.script.file)
    if not script_path.is_absolute():
        script_path = project_path / config.script.file

    is_valid, error_msg = validate_script_file(script_path)
    if not is_valid:
        errors.append(error_msg)

    # Validate character reference images
    if config.characters.reference_images:
        for char_name, char_config in config.characters.reference_images.items():
            is_valid, error_msg = validate_character_images(
                char_config, char_name, project_path
            )
            if not is_valid:
                errors.append(error_msg)

    # Validate BGM file if enabled
    if config.composer.bgm.enabled and config.composer.bgm.file:
        bgm_path = Path(config.composer.bgm.file)
        if not bgm_path.is_absolute():
            bgm_path = project_path / config.composer.bgm.file

        if not bgm_path.exists():
            errors.append(f"BGM file not found: {bgm_path}")

    return len(errors) == 0, errors


def check_api_keys(config: ProjectConfig) -> Tuple[bool, List[str]]:
    """
    Check that required API keys are configured in project config or environment

    Args:
        config: Project configuration

    Returns:
        Tuple of (is_valid, list_of_missing_keys)
    """
    missing_keys = []

    # Helper function to get API key from config or env
    def get_api_key(config_key: str, env_key: str) -> Optional[str]:
        """Get API key from config first, then fall back to environment
        variables, then to the .env-backed settings singleton (pydantic
        loads .env onto Settings, NOT into os.environ)."""
        # Check config
        config_value = getattr(config.api_keys, config_key, None)
        if config_value:
            return config_value
        # Fall back to process environment
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
        # Fall back to settings singleton (.env / runtime settings)
        from config.settings import settings
        return getattr(settings, config_key, None) or None

    # Check image service API key
    if config.image.service == "doubao":
        if not get_api_key("doubao_api_key", "DOUBAO_API_KEY"):
            missing_keys.append("DOUBAO_API_KEY (for Doubao image service) - add to config.yaml api_keys section or .env file")
    elif config.image.service == "nano_banana":
        if not get_api_key("nano_banana_api_key", "NANO_BANANA_API_KEY"):
            missing_keys.append("NANO_BANANA_API_KEY (for Nano Banana service) - add to config.yaml api_keys section or .env file")
    elif config.image.service == "midjourney":
        if not get_api_key("midjourney_api_key", "MIDJOURNEY_API_KEY"):
            missing_keys.append("MIDJOURNEY_API_KEY (for Midjourney service) - add to config.yaml api_keys section or .env file")
    elif config.image.service == "ali_token_plan":
        if not get_api_key("ali_token_plan_api_key", "ALI_TOKEN_PLAN_API_KEY"):
            missing_keys.append("ALI_TOKEN_PLAN_API_KEY (for Ali Token Plan image service) - add to config.yaml api_keys section or .env file")

    # Check video service API key
    if config.video.service == "veo3":
        if not get_api_key("veo3_api_key", "VEO3_API_KEY"):
            missing_keys.append("VEO3_API_KEY (for Veo3 video service) - add to config.yaml api_keys section or .env file")
    elif config.video.service == "sora2":
        if not get_api_key("sora2_api_key", "SORA2_API_KEY"):
            missing_keys.append("SORA2_API_KEY (for Sora2 video service) - add to config.yaml api_keys section or .env file")
    elif config.video.service == "ali_token_plan":
        if not get_api_key("ali_token_plan_api_key", "ALI_TOKEN_PLAN_API_KEY"):
            missing_keys.append("ALI_TOKEN_PLAN_API_KEY (for Ali Token Plan video service) - add to config.yaml api_keys section or .env file")

    return len(missing_keys) == 0, missing_keys


def validate_output_path(output_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate output directory can be created/accessed

    Args:
        output_path: Path to output directory

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Try to create directory if it doesn't exist
        output_path.mkdir(parents=True, exist_ok=True)

        # Check write permissions
        test_file = output_path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            return False, f"No write permission for output directory: {e}"

        return True, None

    except Exception as e:
        return False, f"Cannot create output directory: {e}"


def validate_ffmpeg_available() -> Tuple[bool, Optional[str]]:
    """
    Check if FFmpeg is available in system PATH

    Returns:
        Tuple of (is_available, error_message)
    """
    import shutil

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return False, (
            "FFmpeg not found in system PATH. "
            "Please install FFmpeg 4.0+ and ensure it's in your PATH."
        )

    return True, None


def perform_full_validation(
    project_path: Path,
    config: ProjectConfig,
    check_deps: bool = True
) -> Tuple[bool, List[str], List[str]]:
    """
    Perform complete validation of project

    Args:
        project_path: Project folder path
        config: Project configuration
        check_deps: Whether to check system dependencies (FFmpeg, API keys)

    Returns:
        Tuple of (is_valid, list_of_errors, list_of_warnings)
    """
    errors = []
    warnings = []

    # Validate project structure
    is_valid, missing = validate_project_structure(project_path)
    if not is_valid:
        errors.extend([f"Missing: {item}" for item in missing])
        # Can't proceed without basic structure
        return False, errors, warnings

    # Validate configuration
    is_valid, config_errors = validate_project_config(config, project_path)
    if not is_valid:
        errors.extend(config_errors)

    # Validate output directory
    output_path = Path(config.output.directory)
    if not output_path.is_absolute():
        output_path = project_path / config.output.directory

    is_valid, error_msg = validate_output_path(output_path)
    if not is_valid:
        errors.append(error_msg)

    if check_deps:
        # Check API keys
        is_valid, missing_keys = check_api_keys(config)
        if not is_valid:
            errors.extend([f"Missing API key: {key}" for key in missing_keys])

        # Check FFmpeg
        is_valid, error_msg = validate_ffmpeg_available()
        if not is_valid:
            warnings.append(error_msg)

    # Check for potential issues
    if config.image.max_concurrent > 5:
        warnings.append(
            f"High concurrent image generation ({config.image.max_concurrent}). "
            "This may cause rate limiting or memory issues."
        )

    if config.video.max_concurrent > 3:
        warnings.append(
            f"High concurrent video generation ({config.video.max_concurrent}). "
            "This may cause rate limiting."
        )

    return len(errors) == 0, errors, warnings
