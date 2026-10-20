"""UI end-to-end automation for the AragonMovie full generation workflow.

The test drives the real browser UI (Next.js frontend + FastAPI backend) and
lets the backend call the configured Ali Token Plan gateway for text / image /
video generation. It finishes by asserting that the produced video is shorter
than one minute and that it can be downloaded from the result screen.

Run it with both dev servers up::

    venv\\Scripts\\python.exe -m pytest tests/e2e -v -s --headed

See ``tests/e2e/README.md`` for the full procedure.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.e2e_support import (
    BackendApi,
    ffprobe_duration,
    ffprobe_stream_info,
    load_script_yaml,
    save_image_result,
    scene_ids,
)

PROJECT_NAME = os.getenv("E2E_PROJECT_NAME", "E2E 城市微光")
CHARACTER_NAME = "林小满"
CHARACTER_PROMPT = (
    "Character reference sheet of a 26-year-old Chinese office woman named "
    "Lin Xiaoman: short black bob hair, beige trench coat, white sneakers, "
    "canvas shoulder bag, calm and gentle expression, neutral studio lighting, "
    "photorealistic, full body front view, cinematic color grading"
)
GEN_TIMEOUT_S = float(os.getenv("E2E_GENERATION_TIMEOUT_S", "3000"))
MAX_DURATION_S = float(os.getenv("E2E_MAX_DURATION_S", "60"))
PAGE_TIMEOUT_MS = int(os.getenv("E2E_PAGE_TIMEOUT_MS", "120000"))


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
class Recorder:
    """Collects per-step timings, screenshots and browser console output."""

    def __init__(self, artifacts: Path) -> None:
        self.artifacts = artifacts
        self.steps: List[Dict[str, object]] = []
        self.console: List[str] = []
        self._t0 = time.time()

    def shot(self, page: Page, name: str) -> Path:
        """Save a full page screenshot named after the current step."""
        path = self.artifacts / f"{len(self.steps):02d}_{name}.png"
        try:
            page.screenshot(path=str(path), full_page=True)
        except Exception:  # noqa: BLE001 - screenshots must never break the run
            pass
        return path

    def attach_console(self, page: Page) -> None:
        """Mirror browser console/errors into the report."""
        page.on("console", lambda msg: self.console.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: self.console.append(f"[pageerror] {exc}"))

    def step(self, name: str, started_at: float, screenshot: Path | None = None) -> None:
        """Record one finished step."""
        self.steps.append(
            {
                "step": name,
                "seconds": round(time.time() - started_at, 1),
                "screenshot": str(screenshot) if screenshot else None,
            }
        )
        print(f"  [ok] {name} ({time.time() - started_at:.1f}s)")

    def write(self) -> Path:
        """Write the machine readable report next to the artifacts."""
        report = {
            "total_seconds": round(time.time() - self._t0, 1),
            "steps": self.steps,
            "console_tail": self.console[-300:],
        }
        path = self.artifacts / "e2e_report.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.artifacts / "browser_console.log").write_text(
            "\n".join(self.console), encoding="utf-8"
        )
        return path


def dump_diagnostics(page: Page, artifacts: Path, tag: str) -> Path:
    """Persist everything that helps a human understand a failure."""
    target = artifacts / f"FAILED_{tag}"
    try:
        page.screenshot(path=str(target.with_suffix(".png")), full_page=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        target.with_suffix(".html").write_text(page.content(), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    try:
        logs = page.locator("div.font-mono.text-sm").first.inner_text(timeout=5_000)
        target.with_suffix(".logviewer.txt").write_text(logs, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return target


def _open_new_project(page: Page, frontend_url: str, recorder: Recorder) -> None:
    """Home page -> project creation wizard."""
    started = time.time()
    page.goto(frontend_url, wait_until="domcontentloaded", timeout=180_000)
    expect(page.get_by_role("heading", name="My Projects")).to_be_visible(timeout=180_000)

    page.locator('a[href="/projects/new"]').first.click()
    expect(page.get_by_role("heading", name="Create New Project")).to_be_visible(
        timeout=180_000
    )
    recorder.step("打开新建项目向导", started, recorder.shot(page, "new_project"))


def _create_project(page: Page, recorder: Recorder) -> None:
    """Fill the wizard and land on the workflow page (Step 0)."""
    started = time.time()
    # Labels are wired to the controls (htmlFor/id), so label locators work and
    # no longer break when placeholder copy changes.
    page.get_by_label("Project Name").fill(PROJECT_NAME)
    page.get_by_label("Description (Optional)").fill(
        "UI 自动化测试：阿里云 Token Plan 凭证驱动的 1 分钟内短剧"
    )
    page.get_by_role("button").filter(has_text="Short Drama").first.click()
    page.get_by_role("button").filter(has_text="Full Mode").first.click()

    page.get_by_role("button", name="Create Project").click()
    page.wait_for_url("**/workflow/**", timeout=180_000)
    expect(
        page.get_by_role("heading", name="选择视频类型", exact=True)
    ).to_be_visible(timeout=180_000)
    recorder.step("创建项目并进入 Step0", started, recorder.shot(page, "step0_video_type"))


def _step0_choose_type(page: Page, recorder: Recorder) -> None:
    """Step 0: short drama + modern-drama subtype."""
    started = time.time()
    page.locator("button").filter(has=page.get_by_text("短剧", exact=True)).first.click()
    page.locator("button").filter(has_text="现代都市").first.click()
    expect(page.get_by_text("3. 场景连续性配置")).to_be_visible(timeout=30_000)

    page.get_by_role("button", name="继续到剧本输入").click()
    expect(page.get_by_text("Generate Script")).to_be_visible(timeout=60_000)
    recorder.step("Step0 选择视频类型/子类型", started, recorder.shot(page, "step0_done"))


def _step1_paste_script(page: Page, script_text: str, recorder: Recorder) -> None:
    """Step 1: paste a YAML script through the Direct YAML Input tab."""
    started = time.time()
    page.get_by_role("tab", name="Direct YAML Input").click()
    editor = page.get_by_placeholder(
        "Paste your pre-written YAML script here, or load a sample..."
    )
    editor.fill(script_text)
    # The editor validates with a 500 ms debounce; make sure nothing is flagged.
    expect(page.get_by_text("Script Preview")).to_be_visible(timeout=30_000)
    time.sleep(1.5)
    error_banner = page.locator("p.text-apple-red", has_text="❌")
    if error_banner.count() > 0:
        pytest.fail(f"YAML 校验失败: {error_banner.first.inner_text()}")

    page.get_by_role("button", name="Next: Character Images").click()
    expect(page.get_by_text("Character Reference Images")).to_be_visible(timeout=120_000)
    recorder.step("Step1 粘贴 YAML 剧本", started, recorder.shot(page, "step1_script"))


def _step2_upload_character(
    page: Page, backend_api: BackendApi, artifacts: Path, recorder: Recorder
) -> None:
    """Step 2: generate a reference portrait through the API, upload it in the UI."""
    started = time.time()
    result = backend_api.generate_image(
        prompt=CHARACTER_PROMPT, service="ali_token_plan", width=1024, height=1024
    )
    image_path = save_image_result(result, artifacts / "character_reference.png")
    print(f"  character reference -> {image_path}")

    page.get_by_role("button", name="Manual Upload").first.click()
    page.set_input_files(f"input[id='upload-{CHARACTER_NAME}']", str(image_path))
    expect(page.get_by_text("Image selected")).to_be_visible(timeout=120_000)

    next_button = page.get_by_role("button", name="Next: Scene Images")
    expect(next_button).to_be_enabled(timeout=30_000)
    next_button.click()
    expect(page.get_by_text("Scene Images Setup")).to_be_visible(timeout=120_000)
    recorder.step("Step2 上传角色参考图", started, recorder.shot(page, "step2_character"))


def _step3_scene_images(page: Page, expected_scenes: int, recorder: Recorder) -> None:
    """Step 3: keep the auto-generate mode and move on to video generation."""
    started = time.time()
    expect(
        page.get_by_text(f"Found {expected_scenes} scene", exact=False)
    ).to_be_visible(timeout=60_000)
    page.get_by_role("button", name="Next: Generate Video").click()
    expect(
        page.get_by_role("heading", name="Video Generation Progress")
    ).to_be_visible(timeout=120_000)
    recorder.step("Step3 场景图（后端自动生成）", started, recorder.shot(page, "step3_scenes"))


def _step4_wait_for_video(page: Page, recorder: Recorder) -> None:
    """Step 4: watch the progress card until Step 5 shows up."""
    started = time.time()
    deadline = time.time() + GEN_TIMEOUT_S
    last_stage = None
    stages: List[str] = []
    while time.time() < deadline:
        if page.get_by_text("Video Generated Successfully!").count() > 0:
            recorder.step("Step4 生成视频（轮询完成）", started)
            return
        if page.get_by_text("Generation failed", exact=False).count() > 0:
            dump_diagnostics(page, recorder.artifacts, "generation_failed")
            message = page.get_by_text("Generation failed", exact=False).first.inner_text()
            pytest.fail(f"后端生成失败: {message}")
        stage = _current_stage(page)
        if stage and stage != last_stage:
            stages.append(stage)
            print(f"  ... 阶段: {stage}  {_progress_text(page)}")
            last_stage = stage
        time.sleep(5)

    dump_diagnostics(page, recorder.artifacts, "generation_timeout")
    pytest.fail(f"生成超时（>{GEN_TIMEOUT_S:.0f}s），阶段记录: {stages}")


def _current_stage(page: Page) -> str:
    """Read the ``Current Stage`` label of the progress card."""
    try:
        return page.locator("p.text-apple-headline.font-semibold").first.inner_text(
            timeout=3_000
        )
    except Exception:  # noqa: BLE001
        return ""


def _progress_text(page: Page) -> str:
    """Read the percentage rendered by the progress bar (e.g. ``42%``)."""
    try:
        locator = page.locator("span").filter(has_text=re.compile(r"^\s*\d+%\s*$"))
        return locator.first.inner_text(timeout=3_000).strip()
    except Exception:  # noqa: BLE001
        return ""


def _step5_collect(
    page: Page, backend_api: BackendApi, artifacts: Path, recorder: Recorder
) -> Dict[str, object]:
    """Step 5: verify the result screen and download the produced video."""
    started = time.time()
    expect(page.get_by_role("heading", name="Video Generated Successfully!")).to_be_visible(
        timeout=180_000
    )
    video = page.locator("video").first
    expect(video).to_be_visible(timeout=60_000)
    video_url = video.get_attribute("src") or ""
    assert video_url, "结果页没有 video src"

    target = artifacts / "aragonmovie_e2e_output.mp4"
    backend_api.download(video_url, target)

    duration = ffprobe_duration(target)
    stream = ffprobe_stream_info(target)
    recorder.step("Step5 结果页 + 下载视频", started, recorder.shot(page, "step5_result"))
    return {
        "video_url": video_url,
        "video_path": str(target),
        "duration_s": round(duration, 2),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "codec": stream.get("codec_name"),
    }


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
def test_home_page_loads(page: Page, frontend_url: str) -> None:
    """Cheap smoke test: the frontend renders the project list."""
    page.goto(frontend_url, wait_until="domcontentloaded", timeout=180_000)
    expect(page.get_by_role("heading", name="My Projects")).to_be_visible(timeout=180_000)
    expect(page.locator('a[href="/projects/new"]').first).to_be_visible()


@pytest.mark.e2e
def test_full_workflow_generates_short_video(
    page: Page,
    frontend_url: str,
    backend_api: BackendApi,
    artifacts_dir: Path,
) -> None:
    """Step0 -> Step5 through the UI, ending with a < 60s mp4 on disk."""
    recorder = Recorder(artifacts_dir)
    recorder.attach_console(page)
    page.set_default_timeout(PAGE_TIMEOUT_MS)

    script_text = load_script_yaml()
    scenes = scene_ids(script_text)
    print(f"\n项目: {PROJECT_NAME} | 场景数: {len(scenes)} | 脚本: {len(script_text)} 字符")

    try:
        _open_new_project(page, frontend_url, recorder)
        _create_project(page, recorder)
        _step0_choose_type(page, recorder)
        _step1_paste_script(page, script_text, recorder)
        _step2_upload_character(page, backend_api, artifacts_dir, recorder)
        _step3_scene_images(page, len(scenes), recorder)
        _step4_wait_for_video(page, recorder)
        result = _step5_collect(page, backend_api, artifacts_dir, recorder)
    except Exception:
        dump_diagnostics(page, artifacts_dir, "unexpected")
        report_path = recorder.write()
        print(f"\n诊断信息已保存：{artifacts_dir}（报告 {report_path.name}）")
        raise

    report_path = recorder.write()
    summary = {**result, "report": str(report_path), "steps": recorder.steps}

    print("\n===== UI 自动化结果 =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # The video must be a real, playable file, shorter than one minute.
    assert Path(result["video_path"]).stat().st_size > 100_000, "视频文件过小"
    assert result["duration_s"] <= MAX_DURATION_S, (
        f"视频时长 {result['duration_s']}s 超过 {MAX_DURATION_S}s 上限"
    )
    assert int(result["width"] or 0) >= 640, "分辨率异常"

    (artifacts_dir / "e2e_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
