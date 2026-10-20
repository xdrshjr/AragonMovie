"""BUG 14 smoke test: maintenance endpoints respond and clean temp dirs."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_sweep_endpoint_ok(client):
    response = client.post("/api/v1/tasks/maintenance/sweep")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["cancelled_tasks"], list)


def test_cleanup_endpoint_can_remove_temp_projects(client, tmp_path, monkeypatch):
    from backend.core import temp_project_manager as tpm

    fake_base = tmp_path / "temp_projects"
    stale = fake_base / "workflow_stale"
    stale.mkdir(parents=True)
    (stale / "output").mkdir()

    manager = tpm.TempProjectManager(base_dir=fake_base)
    monkeypatch.setattr(
        tpm, "_temp_project_manager_instance", manager, raising=False
    )

    response = client.post(
        "/api/v1/workflow/cleanup",
        params={"max_age_hours": 0, "include_temp_projects": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["temp_projects_removed"] >= 1
    assert not stale.exists()
