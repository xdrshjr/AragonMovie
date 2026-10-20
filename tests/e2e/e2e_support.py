"""Helpers shared by the UI end-to-end tests.

Kept free of Playwright imports so they can also be used from plain scripts.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

E2E_DIR = Path(__file__).parent
FIXTURES_DIR = E2E_DIR / "fixtures"


class BackendError(RuntimeError):
    """Raised when the backend answers with an unexpected status."""


class BackendApi:
    """Thin REST client for the FastAPI backend, used to prepare test data."""

    def __init__(self, base_url: str, timeout_s: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = requests.Session()

    # ---------------------------------------------------------------- health
    def wait_healthy(self, timeout_s: float = 90.0) -> Dict[str, Any]:
        """Poll ``/health`` until the backend answers or the deadline expires."""
        deadline = time.time() + timeout_s
        last_error: Optional[Exception] = None
        while time.time() < deadline:
            try:
                response = self.session.get(f"{self.base_url}/health", timeout=5)
                if response.status_code == 200:
                    return response.json()
                last_error = BackendError(
                    f"/health returned {response.status_code}: {response.text[:200]}"
                )
            except requests.RequestException as exc:  # backend not up yet
                last_error = exc
            time.sleep(2)
        raise BackendError(
            f"backend at {self.base_url} did not become healthy: {last_error}"
        )

    # ---------------------------------------------------------------- images
    def generate_image(
        self,
        prompt: str,
        service: str = "ali_token_plan",
        width: int = 1024,
        height: int = 1024,
        optimize_prompt: bool = False,
    ) -> Dict[str, Any]:
        """Generate one image through the backend image service."""
        payload = {
            "prompt": prompt,
            "service": service,
            "width": width,
            "height": height,
            "optimize_prompt": optimize_prompt,
        }
        response = self.session.post(
            f"{self.base_url}/api/v1/images/generate",
            json=payload,
            timeout=self.timeout_s,
        )
        if response.status_code != 200:
            raise BackendError(
                f"image generation failed ({response.status_code}): "
                f"{response.text[:500]}"
            )
        return response.json()

    # ---------------------------------------------------------------- assets
    def download(self, url: str, target: Path) -> Path:
        """Download an asset (image / video) to ``target``."""
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.session.get(url, timeout=self.timeout_s, stream=True)
        if response.status_code != 200:
            raise BackendError(
                f"download failed ({response.status_code}) for {url[:120]}"
            )
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
        return target


def save_image_result(result: Dict[str, Any], target: Path) -> Path:
    """Persist an ``ImageGenerationResponse`` payload (url or base64) to disk."""
    import base64

    target.parent.mkdir(parents=True, exist_ok=True)
    image_url = result.get("image_url")
    if image_url and str(image_url).startswith("http"):
        response = requests.get(image_url, timeout=300)
        response.raise_for_status()
        target.write_bytes(response.content)
        return target
    if image_url and str(image_url).startswith("data:"):
        _, _, encoded = str(image_url).partition(",")
        target.write_bytes(base64.b64decode(encoded))
        return target
    image_b64 = result.get("image_b64")
    if image_b64:
        target.write_bytes(base64.b64decode(image_b64))
        return target
    raise BackendError(f"image response carried no usable payload: {list(result)}")


def ffprobe_duration(path: Path) -> float:
    """Return the media duration in seconds using ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found on PATH (install FFmpeg)")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(completed.stdout.strip())


def ffprobe_stream_info(path: Path) -> Dict[str, Any]:
    """Return width/height/codec of the first video stream."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found on PATH (install FFmpeg)")
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name,nb_frames",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    streams = json.loads(completed.stdout or "{}").get("streams") or [{}]
    return streams[0]


def load_script_yaml(name: str = "short_drama_1min.yaml") -> str:
    """Read a YAML script fixture as text (ready to paste into the UI)."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def scene_ids(script_text: str) -> List[str]:
    """Extract ``scene_id`` values from a YAML script fixture."""
    ids: List[str] = []
    for line in script_text.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if stripped.startswith("scene_id:"):
            ids.append(stripped.split(":", 1)[1].strip().strip('"\''))
    return ids
