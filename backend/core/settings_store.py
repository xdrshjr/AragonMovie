"""Runtime model-settings store: persistence + hot apply.

Layering
--------
1. ``.env`` (loaded once by pydantic-settings) provides the DEFAULTS.
2. ``backend/data/model_settings.json`` (this store) stores runtime
   overrides produced by the Settings UI or the configuration Agent.
   On startup and on every update the JSON values are written onto BOTH
   settings singletons:
   - ``backend.config.settings``  (web backend)
   - ``config.settings.settings`` (root pipeline: agents/services)

Service hot-reload
------------------
``reset_runtime_services()`` (in service_wrapper) drops the cached
service-wrapper singletons so the next request rebuilds them from the
new settings. ``ImageServiceFactory`` already builds per-call services,
so image generation picks up new values automatically.

The JSON file contains REAL API KEYS. It lives under ``backend/data/``
which is git-ignored; ``GET``-style reads for the UI go through
:func:`mask_settings` and never expose full keys.
"""
import asyncio
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.core.settings_models import (
    ModelSettings,
    SettingsUpdateRequest,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

SETTINGS_VERSION = 1

# Path of the persisted runtime settings (relative to the backend package).
DEFAULT_SETTINGS_FILE = Path(__file__).parent.parent / "data" / "model_settings.json"

# (dotted json path in ModelSettings, attribute name on both settings singletons)
FIELD_MAP: List[Tuple[str, str]] = [
    # text
    ("text.fast_llm.api_key", "fast_llm_api_key"),
    ("text.fast_llm.api_url", "fast_llm_api_url"),
    ("text.fast_llm.model", "fast_llm_model"),
    ("text.judge_llm.api_key", "judge_llm_api_key"),
    ("text.judge_llm.api_url", "judge_llm_api_url"),
    ("text.judge_llm.model", "judge_llm_model"),
    ("text.enable_prompt_optimization", "enable_prompt_optimization"),
    ("text.enable_character_consistency_judge", "enable_character_consistency_judge"),
    # voice
    ("voice.enabled", "enable_tts"),
    ("voice.api_key", "tts_api_key"),
    ("voice.base_url", "tts_base_url"),
    ("voice.model", "tts_model"),
    ("voice.default_voice", "tts_default_voice"),
    ("voice.default_format", "tts_default_format"),
    ("voice.default_speed", "tts_default_speed"),
    # video
    ("video.service_type", "video_service_type"),
    ("video.veo3.api_key", "veo3_api_key"),
    ("video.veo3.base_url", "veo3_base_url"),
    ("video.veo3.endpoint", "veo3_endpoint"),
    ("video.veo3.model", "veo3_model"),
    ("video.veo3.skip_upload", "veo3_skip_upload"),
    ("video.sora2.api_key", "sora2_api_key"),
    ("video.sora2.base_url", "sora2_base_url"),
    ("video.sora2.endpoint", "sora2_endpoint"),
    ("video.sora2.model", "sora2_model"),
    ("video.sora2.default_size", "sora2_default_size"),
    ("video.sora2.default_duration", "sora2_default_duration"),
    ("video.sora2.default_style", "sora2_default_style"),
    ("video.sora2.watermark", "sora2_watermark"),
    ("video.sora2.private", "sora2_private"),
    # image
    ("image.service_type", "image_service_type"),
    ("image.doubao.api_key", "doubao_api_key"),
    ("image.doubao.base_url", "doubao_base_url"),
    ("image.doubao.endpoint", "doubao_endpoint"),
    ("image.doubao.model", "doubao_model"),
    ("image.doubao.watermark", "doubao_watermark"),
    ("image.nano_banana.api_key", "nano_banana_api_key"),
    ("image.nano_banana.base_url", "nano_banana_base_url"),
    ("image.nano_banana.endpoint", "nano_banana_endpoint"),
    ("image.nano_banana.model", "nano_banana_model"),
    ("image.midjourney.api_key", "midjourney_api_key"),
    ("image.midjourney.base_url", "midjourney_base_url"),
    ("image.midjourney.bot_type", "midjourney_bot_type"),
    ("image.midjourney.poll_interval", "midjourney_poll_interval"),
    ("image.midjourney.max_poll_attempts", "midjourney_max_poll_attempts"),
    ("image.midjourney.auto_upscale", "midjourney_auto_upscale"),
    ("image.midjourney.upscale_index", "midjourney_upscale_index"),
    # agent
    ("agent.enabled", "agent_enabled"),
    ("agent.provider", "agent_provider"),
    ("agent.api_key", "agent_api_key"),
    ("agent.base_url", "agent_base_url"),
    ("agent.model", "agent_model"),
    ("agent.max_turns", "agent_max_turns"),
    ("agent.timeout_seconds", "agent_timeout_seconds"),
    ("agent.aragon_cli_path", "aragon_cli_path"),
]

# ModelSettings paths that hold write-only secrets.
SECRET_PATHS = {
    "text.fast_llm.api_key",
    "text.judge_llm.api_key",
    "voice.api_key",
    "video.veo3.api_key",
    "video.sora2.api_key",
    "image.doubao.api_key",
    "image.nano_banana.api_key",
    "image.midjourney.api_key",
    "agent.api_key",
}


def mask_key(key: Optional[str]) -> str:
    """Mask an API key for display: ``sk-abcd****wxyz`` ("" when unset)."""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _get_path(obj, dotted: str):
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def _set_path(obj, dotted: str, value):
    parts = dotted.split(".")
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], value)


class ModelSettingsStore:
    """File-backed runtime settings store with hot-apply."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = Path(file_path) if file_path else DEFAULT_SETTINGS_FILE
        self._lock = threading.RLock()
        self._current: Optional[ModelSettings] = None
        self._file_hash: Optional[str] = None

    # ---------------- singleton access ----------------

    @classmethod
    def get_instance(cls) -> "ModelSettingsStore":
        global _store_instance
        if _store_instance is None:
            _store_instance = cls()
        return _store_instance

    # ---------------- env <-> model ----------------

    def settings_from_env(self) -> ModelSettings:
        """Build a ModelSettings snapshot from the backend settings singleton
        (which reflects .env plus any previously applied overrides)."""
        from backend.config import settings as backend_settings

        data: Dict = {}
        for json_path, attr in FIELD_MAP:
            value = getattr(backend_settings, attr)
            if json_path in SECRET_PATHS:
                value = value or ""
            _set_path_nested(data, json_path, value)
        return ModelSettings.model_validate(data)

    # ---------------- persistence ----------------

    def load(self) -> ModelSettings:
        """Load settings: JSON file wins over env defaults; missing or
        invalid files fall back to env (never crash the app)."""
        with self._lock:
            env_settings = self.settings_from_env()
            if not self.file_path.exists():
                self._current = env_settings
                self._file_hash = None
                return env_settings
            try:
                raw = self.file_path.read_bytes()
                payload = json.loads(raw.decode("utf-8"))
                stored = payload.get("settings", payload)
                merged = _merge_write_only(env_settings.model_dump(), stored)
                parsed = ModelSettings.model_validate(merged)
                self._current = parsed
                self._file_hash = hashlib.sha256(raw).hexdigest()
                return parsed
            except Exception as e:  # noqa: BLE001 - settings must never crash startup
                logger.error(f"Failed to load model settings file, falling back to env: {e}")
                self._current = env_settings
                self._file_hash = None
                return env_settings

    def save(self, model_settings: ModelSettings) -> None:
        """Persist the full settings (real keys) atomically."""
        with self._lock:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": SETTINGS_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "settings": model_settings.model_dump(),
            }
            raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            tmp = self.file_path.with_suffix(".json.tmp")
            tmp.write_bytes(raw)
            tmp.replace(self.file_path)
            self._current = model_settings
            self._file_hash = hashlib.sha256(raw).hexdigest()

    # ---------------- runtime apply ----------------

    def apply_to_runtime(self, model_settings: ModelSettings) -> None:
        """Write all mapped fields onto both settings singletons and drop
        cached service instances so new config takes effect immediately."""
        from backend.config import settings as backend_settings
        from config.settings import settings as root_settings
        from backend.core import service_wrapper

        for json_path, attr in FIELD_MAP:
            value = _get_path(model_settings, json_path)
            if json_path in SECRET_PATHS and value is None:
                value = ""
            setattr(backend_settings, attr, value)
            setattr(root_settings, attr, value)

        self._schedule_service_reset(service_wrapper)
        logger.info(
            "Runtime model settings applied | image=%s video=%s tts=%s agent=%s",
            model_settings.image.service_type,
            model_settings.video.service_type,
            model_settings.voice.enabled,
            model_settings.agent.enabled,
        )

    def _schedule_service_reset(self, service_wrapper) -> None:
        """Best-effort graceful close of cached services, then reset."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            loop.create_task(service_wrapper.reset_runtime_services())
        else:
            service_wrapper.reset_runtime_services_sync()

    def load_and_apply(self) -> ModelSettings:
        """Startup entrypoint: load persisted overrides and apply them."""
        model_settings = self.load()
        self.apply_to_runtime(model_settings)
        return model_settings

    # ---------------- update (API path) ----------------

    def update(self, request: SettingsUpdateRequest) -> ModelSettings:
        """Merge a partial update (write-only key semantics), persist and
        hot-apply. Returns the new effective settings."""
        with self._lock:
            current = self._current if self._current is not None else self.load()
            merged = current.model_copy(deep=True)

            for category in ("text", "voice", "video", "image", "agent"):
                incoming = getattr(request, category)
                if incoming is None:
                    continue
                current_cat = getattr(merged, category)
                incoming_dump = incoming.model_dump()
                _merge_category(current_cat, incoming_dump)

            ModelSettings.model_validate(merged.model_dump())  # validate result
            self.save(merged)
            self.apply_to_runtime(merged)
            return merged

    # ---------------- agent-edit reload ----------------

    def reload_if_changed(self) -> bool:
        """Detect external edits to the settings file (e.g. by the agent),
        re-validate and hot-apply. Returns True when settings changed."""
        with self._lock:
            if not self.file_path.exists():
                return False
            raw = self.file_path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if digest == self._file_hash:
                return False
            try:
                payload = json.loads(raw.decode("utf-8"))
                stored = payload.get("settings", payload)
                env_settings = self.settings_from_env()
                merged = _merge_write_only(env_settings.model_dump(), stored)
                parsed = ModelSettings.model_validate(merged)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Externally edited settings file is invalid, ignored: {e}")
                self._file_hash = digest
                return False
            self._current = parsed
            self._file_hash = digest
            self.apply_to_runtime(parsed)
            logger.info("External settings edit detected and applied")
            return True

    # ---------------- masked views ----------------

    def current(self) -> ModelSettings:
        if self._current is None:
            return self.load()
        return self._current

    def masked(self) -> Dict:
        """Settings dict with masked secrets, plus ``has_*_key`` flags."""
        data = self.current().model_dump()
        for path in SECRET_PATHS:
            node = data
            parts = path.split(".")
            for part in parts[:-1]:
                node = node[part]
            node[parts[-1]] = mask_key(node.get(parts[-1]))
        return data


# ==================== merge helpers ====================


def _set_path_nested(data: Dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _merge_write_only(base_dump: Dict, stored: Dict) -> Dict:
    """Overlay ``stored`` (from file) onto ``base_dump`` (env defaults).

    Same semantics as the API: keys absent from ``stored`` keep base values;
    explicit nulls are dropped (treated as absent) so env keys survive.
    """
    def walk(base: Dict, overlay: Dict):
        for key, value in overlay.items():
            if key not in base:
                base[key] = value
            elif isinstance(value, dict) and isinstance(base[key], dict):
                walk(base[key], value)
            elif value is not None:
                base[key] = value
        return base

    return walk(base_dump, stored or {})


def _merge_category(current_cat, incoming_dump: Dict) -> None:
    """Apply one category's partial update onto the current model object.

    ``api_key=None`` (or a value identical to the current MASKED form, in
    case the UI echoes it back) keeps the stored key; ``""`` clears it.
    """
    for field, value in incoming_dump.items():
        if field == "api_key" and value is None:
            continue
        if field == "api_key":
            current_key = getattr(current_cat, "api_key") or ""
            if value == mask_key(current_key):
                continue
        if isinstance(value, dict) and hasattr(current_cat, field):
            sub = getattr(current_cat, field)
            if isinstance(sub, object):
                _merge_category(sub, value)
                continue
        setattr(current_cat, field, value)


_store_instance: Optional[ModelSettingsStore] = None


def get_settings_store() -> ModelSettingsStore:
    return ModelSettingsStore.get_instance()


__all__ = [
    "ModelSettingsStore",
    "get_settings_store",
    "mask_key",
    "FIELD_MAP",
    "SECRET_PATHS",
    "DEFAULT_SETTINGS_FILE",
]
