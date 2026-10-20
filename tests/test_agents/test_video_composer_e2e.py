"""Real end-to-end composition tests (moviepy 2.x + proglog wiring).

These tests write actual clips with ffmpeg, so they catch API drift that unit
tests with stubs cannot: the moviepy 1.x helpers that no longer exist in 2.x
(``subclip`` / ``volumex`` / ``set_audio`` / ``set_position``) and the proglog bar
name used for write progress (``frame_index``, not ``t``).

Skipped automatically when ffmpeg is unavailable.
"""

import asyncio
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg is required for real composition tests",
)

mp = pytest.importorskip("moviepy")
np = pytest.importorskip("numpy")

from agents.video_composer_agent import VideoComposerAgent  # noqa: E402


def _make_clips(tmp_path: Path, count: int = 3) -> list:
    colors = [(255, 0, 0), (0, 0, 255), (0, 200, 0), (120, 120, 0)]
    paths = []
    for i in range(count):
        path = tmp_path / f"clip_{i + 1:03d}.mp4"
        mp.ColorClip(size=(160, 96), color=colors[i % len(colors)], duration=0.4).write_videofile(
            str(path), fps=10, logger=None, codec="libx264", audio=False
        )
        paths.append(path)
    return paths


def _make_bgm(tmp_path: Path) -> Path:
    path = tmp_path / "bgm.wav"
    mp.AudioClip(
        frame_function=lambda t: 0.1 * np.sin(2 * np.pi * 440 * t),
        duration=0.3,
        fps=22050,
    ).write_audiofile(str(path), logger=None)
    return path


def _results(paths) -> list:
    return [
        {
            "scene_id": f"scene_{i:03d}",
            "success": True,
            "video_path": str(path),
            "dialogues": [{"content": f"line {i}", "duration": 0.3}],
        }
        for i, path in enumerate(paths, start=1)
    ]


@pytest.mark.asyncio
async def test_execute_writes_video_and_reports_progress(tmp_path):
    """The write itself must succeed and drive the progress callback."""
    results = _results(_make_clips(tmp_path))
    composer = VideoComposerAgent(output_dir=tmp_path / "final")

    reports = []

    async def on_progress(percent, message):
        reports.append((percent, message))

    output = await composer.execute(results, progress_callback=on_progress)

    assert Path(output).exists() and Path(output).stat().st_size > 0
    assert reports, "composition reported no progress (broken proglog wiring)"
    assert all(0.0 <= p <= 100.0 for p, _ in reports)
    assert reports[-1][0] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_execute_with_bgm_and_subtitles(tmp_path, caplog):
    """moviepy 2.x audio/subtitle helpers must actually work, not be swallowed."""
    results = _results(_make_clips(tmp_path, count=2))
    composer = VideoComposerAgent(output_dir=tmp_path / "final")

    with caplog.at_level("INFO"):
        output = await composer.execute(
            results,
            output_filename="with_extras.mp4",
            bgm_path=str(_make_bgm(tmp_path)),
            add_subtitles=True,
        )

    assert Path(output).exists() and Path(output).stat().st_size > 0

    # BGM/subtitles are best effort, so a broken moviepy call would be logged
    # and silently skipped: fail on that instead of accepting a silent downgrade.
    failures = [
        record.getMessage()
        for record in caplog.records
        if record.levelname in {"WARNING", "ERROR"}
        and ("BGM" in record.getMessage() or "subtitle" in record.getMessage().lower())
    ]
    assert not failures, f"composition silently degraded: {failures}"

    clip = mp.VideoFileClip(output)
    try:
        assert clip.duration > 0
        # The BGM must have been mixed into the final file
        assert clip.audio is not None, "background music was not applied"
    finally:
        clip.close()


@pytest.mark.asyncio
async def test_execute_skips_failed_scenes(tmp_path):
    """A failed scene (video_path=None) must not abort the whole composition.

    ``validate_input`` used to run on the unfiltered result list, so one failed
    scene raised "Invalid video results" even though the code below explicitly
    supports composing the successful clips only.
    """
    results = _results(_make_clips(tmp_path, count=2))
    results.insert(
        1,
        {
            "scene_id": "scene_999",
            "success": False,
            "video_path": None,
            "error": "veo rejected the prompt",
            "error_type": "generation_failed",
        },
    )
    composer = VideoComposerAgent(output_dir=tmp_path / "final")

    output = await composer.execute(results, output_filename="partial.mp4")

    assert Path(output).exists() and Path(output).stat().st_size > 0


@pytest.mark.asyncio
async def test_execute_skips_missing_files(tmp_path):
    """A successful scene whose file disappeared is skipped, not fatal."""
    results = _results(_make_clips(tmp_path, count=2))
    results.append(
        {
            "scene_id": "scene_zzz",
            "success": True,
            "video_path": str(tmp_path / "does_not_exist.mp4"),
        }
    )
    composer = VideoComposerAgent(output_dir=tmp_path / "final")

    output = await composer.execute(results, output_filename="missing.mp4")

    assert Path(output).exists()


@pytest.mark.asyncio
async def test_execute_raises_when_nothing_is_composable(tmp_path):
    composer = VideoComposerAgent(output_dir=tmp_path / "final")
    results = [
        {
            "scene_id": "scene_001",
            "success": False,
            "video_path": None,
            "error": "failed",
        }
    ]

    with pytest.raises(ValueError):
        await composer.execute(results)


@pytest.mark.asyncio
async def test_compose_progress_does_not_leak_past_completion(tmp_path):
    """Progress updates are drained before execute() returns (monotonic task %)."""
    results = _results(_make_clips(tmp_path, count=2))
    composer = VideoComposerAgent(output_dir=tmp_path / "final")

    seen = []

    async def on_progress(percent, message):
        seen.append(percent)
        await asyncio.sleep(0)  # force a scheduling point

    await composer.execute(results, progress_callback=on_progress)
    assert seen[-1] == pytest.approx(100.0)

    # Nothing can be scheduled afterwards: the callbacks were awaited
    count_after_return = len(seen)
    await asyncio.sleep(0.1)
    assert len(seen) == count_after_return
