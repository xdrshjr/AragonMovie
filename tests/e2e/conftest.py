"""Shared fixtures for the AragonMovie UI end-to-end suite.

The suite drives the real Next.js frontend in a real Chromium browser and lets
the backend call the Ali Token Plan gateway (text / image / video models).
Start both dev servers first (see ``tests/e2e/README.md``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).parent
REPO_ROOT = E2E_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FRONTEND_URL = os.getenv("E2E_FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("E2E_BACKEND_URL", "http://localhost:8000")


def pytest_configure(config: pytest.Config) -> None:
    """Register the custom markers used by this suite."""
    config.addinivalue_line(
        "markers",
        "e2e: full UI end-to-end run that calls the real generation APIs",
    )


@pytest.fixture(scope="session")
def frontend_url() -> str:
    """Base URL of the Next.js frontend under test."""
    return FRONTEND_URL


@pytest.fixture(scope="session")
def backend_url() -> str:
    """Base URL of the FastAPI backend under test."""
    return BACKEND_URL


@pytest.fixture(scope="session")
def artifacts_dir() -> Path:
    """Directory that receives screenshots, logs and the generated video."""
    path = Path(os.getenv("E2E_ARTIFACTS_DIR", str(E2E_DIR / "artifacts")))
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def backend_api(backend_url: str):
    """REST helper pointed at the backend, checked for readiness."""
    from tests.e2e.e2e_support import BackendApi

    api = BackendApi(backend_url)
    api.wait_healthy(timeout_s=90)
    return api


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    """Give the browser a desktop viewport and a stable locale."""
    return {
        **browser_context_args,
        "viewport": {"width": 1600, "height": 1000},
        "locale": "zh-CN",
    }


@pytest.fixture(scope="session", autouse=True)
def cleanup_generated_artifacts(backend_url: str):
    """Cancel leftover tasks and delete temp dirs / projects created by the run.

    Every E2E run used to leave one project record in ``backend/projects/`` and a
    whole ``backend/temp_projects/workflow_*`` directory (images + videos) on
    disk, and any task the run abandoned kept generating in the background.

    Best effort on purpose: it depends only on the configured URL (not on a
    healthy backend), so it can never block or fail the suite.
    """
    yield

    from tests.e2e.e2e_support import BackendApi

    api = BackendApi(backend_url, timeout_s=60.0)

    # Skip everything when the backend was never reachable during the run.
    try:
        api.session.get(f"{api.base_url}/health", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] backend unreachable, skipping cleanup: {exc}")
        return

    # 1) stop generation that is still running but no longer watched
    try:
        result = api.sweep_abandoned_tasks()
        print(f"[cleanup] abandoned tasks cancelled: {result.get('cancelled_count')}")
    except Exception as exc:  # noqa: BLE001 - teardown must not fail the suite
        print(f"[cleanup] abandoned-task sweep failed: {exc}")

    # 2) remove the project records this run created
    project_name = os.getenv("E2E_PROJECT_NAME", "E2E 城市微光")
    try:
        deleted = api.delete_projects_named(project_name)
        print(f"[cleanup] deleted {deleted} project(s) named {project_name!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] project cleanup failed: {exc}")

    # 3) remove temp project directories (max_age_hours=0 -> all of them)
    try:
        result = api.cleanup_temp_projects(max_age_hours=0)
        print(
            "[cleanup] temp projects removed: "
            f"{result.get('temp_projects_removed')}"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[cleanup] temp project cleanup failed: {exc}")


CHROME_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    """Prefer an installed Google Chrome over a downloaded Playwright build.

    Set ``E2E_BROWSER_CHANNEL=`` (empty) to force the bundled Chromium, or
    install it once with ``python -m playwright install chromium``.
    """
    channel = os.getenv("E2E_BROWSER_CHANNEL")
    if channel is None:
        channel = "chrome" if any(Path(p).exists() for p in CHROME_PATHS) else ""
    if not channel:
        return browser_type_launch_args
    return {**browser_type_launch_args, "channel": channel}
