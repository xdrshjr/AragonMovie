"""End-to-end verification: a ~10 second short drama on Volcano (Doubao) + Ali Token Plan.

What it does (all real, nothing mocked):
  1. boots the FastAPI backend on a free loopback port
  2. writes the provider configuration through the Settings Center API
     (text/image: Ali Token Plan, video: 豆包 Seedance/Ark, voice: 火山 TTS 2.0)
  3. runs the settings-center connection tests and prints them
  4. submits a 2 scene x 5s short-drama workflow and polls it
  5. downloads the composed mp4 and verifies duration / streams / resolution with ffprobe

Usage (PowerShell):
    $env:DOUBAO_VIDEO_API_KEY="<ark key>"
    $env:TTS_VOLC_API_KEY="<volcano tts2 key>"
    $env:ALI_TOKEN_PLAN_API_KEY="<token plan key>"     # optional, falls back to .env
    venv\\Scripts\\python.exe scripts\\e2e_volcano_short_drama.py

Artifacts land in build/desktop/e2e/<timestamp>/.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = REPO_ROOT / "build" / "desktop" / "e2e"
LLM_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen3.8-flash"
VOLC_TTS_VOICE = "zh_female_xiaohe_uranus_bigtts"
VOLC_TTS_RESOURCE = "seed-tts-2.0"
VIDEO_MODEL = "doubao-seedance-2-0-260128"

SCRIPT_YAML = """title: "雨夜归途"
author: "AragonMovie E2E"
description: "十秒都市短剧：雨夜的街口，一个人的独白"

characters:
  - name: "林小满"
    description: "26岁都市女性，齐耳短发，米色风衣，背着帆布包"
    age: 26
    gender: "female"
    appearance: "黑色齐耳短发，米色风衣，白色帆布鞋"

scenes:
  - scene_id: "scene_001"
    location: "雨夜的城市街口"
    time: "夜晚"
    weather: "小雨"
    atmosphere: "霓虹映在湿漉漉的柏油路上，雨丝在路灯光里发亮"
    description: "雨夜的街口，林小满撑着一把浅色雨伞站在路灯下，霓虹倒影在积水里"
    shot_type: "medium_shot"
    camera_movement: "dolly"
    duration: 5.0
    visual_style: "cinematic"
    color_tone: "cool"
    action: "林小满缓缓抬头，雨水顺着伞沿滑落，她轻轻呼出一口气"
    extract_frame_index: -5
    base_image_filename: null
    characters:
      - "林小满"
    dialogues: []
    narrations:
      - content: "雨夜的街口，她停下了脚步。"
        voice_style: "温柔旁白"
    sound_effects: []
    sub_scenes: []

  - scene_id: "scene_002"
    location: "街角的咖啡店门口"
    time: "夜晚"
    weather: "小雨"
    atmosphere: "暖黄的橱窗灯光洒在雨幕上，水汽朦胧"
    description: "街角咖啡店的暖黄橱窗，林小满收伞走近，玻璃上映出她的身影与雨滴"
    shot_type: "full_shot"
    camera_movement: "tracking"
    duration: 5.0
    visual_style: "cinematic"
    color_tone: "warm"
    action: "林小满推门而入，暖光笼罩她的侧脸，嘴角浮起一点笑意"
    extract_frame_index: -5
    base_image_filename: null
    characters:
      - "林小满"
    dialogues: []
    narrations:
      - content: "总有一盏灯，为晚归的人亮着。"
        voice_style: "温柔旁白"
    sound_effects: []
    sub_scenes: []
"""


def make_scene_image(kind: str) -> str:
    """Flat-illustration 1280x720 still (data URI) for one scene.

    Deliberately stylised: Ark rejects photo-like stills that its safety
    filter reads as a real person.
    """
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), (10, 12, 20))
    draw = ImageDraw.Draw(img)
    if kind == "street":
        # night sky gradient
        for y in range(height):
            t = y / height
            draw.line([(0, y), (width, y)], fill=(int(12 + 26 * t), int(16 + 30 * t), int(34 + 58 * t)))
        # skyline blocks
        for x in range(0, width, 96):
            h = 120 + (x * 13) % 220
            draw.rectangle([x + 8, height - 190 - h, x + 84, height - 170], fill=(18, 22, 34))
            for wy in range(height - 180 - h, height - 186, 30):
                draw.rectangle([x + 22, wy, x + 34, wy + 14], fill=(250, 214, 150))
        # wet road
        draw.rectangle([0, height - 170, width, height], fill=(14, 16, 24))
        for x in range(40, width, 150):
            draw.ellipse([x, height - 120, x + 96, height - 84], fill=(30, 40, 70))
        # lamp post + light cone
        draw.rectangle([188, 120, 200, height - 170], fill=(60, 64, 78))
        draw.ellipse([150, 96, 238, 148], fill=(255, 228, 168))
        draw.polygon([(150, 140), (238, 140), (330, height - 170), (70, height - 170)], fill=(60, 52, 34))
        # umbrella silhouette (no face, pure graphic)
        draw.pieslice([470, 330, 810, 560], start=180, end=360, fill=(226, 88, 106))
        draw.rectangle([636, 440, 644, 610], fill=(40, 42, 52))
        # rain streaks
        for x in range(30, width, 46):
            draw.line([(x, 30 + (x % 60)), (x - 8, 120 + (x % 60))], fill=(120, 150, 190), width=2)
    else:
        # cafe front: warm window, awning, wet pavement
        draw.rectangle([0, 0, width, height], fill=(16, 18, 26))
        draw.rectangle([120, 150, 1160, 560], fill=(28, 26, 30))
        draw.rectangle([170, 200, 1110, 520], fill=(255, 206, 128))
        draw.rectangle([170, 200, 1110, 250], fill=(214, 150, 84))
        for x in range(230, 1100, 190):
            draw.rectangle([x, 250, x + 12, 520], fill=(46, 40, 36))
        # awning stripes
        for x in range(120, 1160, 120):
            draw.polygon([(x, 150), (x + 120, 150), (x + 96, 92), (x + 24, 92)], fill=(198, 74, 88) if (x // 120) % 2 == 0 else (238, 232, 224))
        # pavement + reflection
        draw.rectangle([0, 560, width, height], fill=(20, 22, 30))
        draw.ellipse([220, 600, 1060, 700], fill=(58, 46, 34))
        # raindrops
        for x in range(60, width, 52):
            draw.line([(x, 20 + (x % 50)), (x - 6, 96 + (x % 50))], fill=(110, 130, 170), width=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def dotenv_value(key: str) -> str:
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def require(name: str, fallback_env: str = "") -> str:
    value = os.environ.get(name) or (dotenv_value(fallback_env) if fallback_env else "")
    if not value:
        raise SystemExit(f"missing credential: set {name}")
    return value


def ffprobe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration,size,bit_rate",
            "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed: {result.stderr[:400]}")
    return json.loads(result.stdout)


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifacts = ARTIFACT_ROOT / stamp
    artifacts.mkdir(parents=True, exist_ok=True)

    llm_key = require("FAST_LLM_API_KEY", "FAST_LLM_API_KEY")
    image_key = os.environ.get("ALI_TOKEN_PLAN_API_KEY") or dotenv_value("ALI_TOKEN_PLAN_API_KEY") or llm_key
    video_key = require("DOUBAO_VIDEO_API_KEY")
    voice_key = require("TTS_VOLC_API_KEY")

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    api = f"{base}/api/v1"
    backend_log = artifacts / "backend.log"

    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        # Ark rejects photorealistic frames cut from a generated clip with
        # InputImageSensitiveContentDetected.PrivacyInformation ("real person"),
        # so scene-to-scene reference frames are disabled for this run.
        "ENABLE_SCENE_CONTINUITY": "false",
        "ENABLE_SMART_CONTINUITY_JUDGE": "false",
    }
    for name in ("FAST_LLM_API_KEY", "JUDGE_LLM_API_KEY", "ALI_TOKEN_PLAN_API_KEY", "TTS_VOLC_API_KEY", "DOUBAO_VIDEO_API_KEY"):
        env.pop(name, None)

    log_stream = backend_log.open("w", encoding="utf-8")
    print(f"[1/6] starting backend on {port}")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--app-dir", str(REPO_ROOT), "--log-level", "info"],
        cwd=REPO_ROOT, env=env, stdout=log_stream, stderr=subprocess.STDOUT,
    )

    report: dict = {"started_at": stamp, "base_url": base, "artifacts": str(artifacts)}
    client = httpx.Client(base_url=api, timeout=120.0)
    try:
        # ---------------------------------------------------------------- boot
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/health", timeout=5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        else:
            raise SystemExit("backend did not become healthy")

        # ------------------------------------------------------------ settings
        settings_payload = {
            "text": {
                "fast_llm": {"api_key": llm_key, "api_url": LLM_BASE, "model": LLM_MODEL},
                "judge_llm": {"api_key": llm_key, "api_url": LLM_BASE, "model": LLM_MODEL},
                "enable_prompt_optimization": True,
                "enable_character_consistency_judge": False,
            },
            "image": {
                "service_type": "ali_token_plan",
                "ali_token_plan": {"api_key": image_key, "base_url": LLM_BASE, "model": "wan2.7-image-pro"},
            },
            "video": {
                "service_type": "doubao",
                "doubao": {
                    "api_key": video_key,
                    "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                    "endpoint": "/contents/generations/tasks",
                    "model": VIDEO_MODEL,
                    "t2v_model": VIDEO_MODEL,
                    "default_resolution": "720p",
                    "default_ratio": "16:9",
                    "default_duration": 5,
                },
            },
            "voice": {
                "enabled": True,
                "provider": "volc_tts2",
                "volc_api_key": voice_key,
                "volc_resource_id": VOLC_TTS_RESOURCE,
                "volc_voice": VOLC_TTS_VOICE,
            },
        }
        print("[2/6] writing provider configuration via the Settings Center API")
        response = client.put("/settings", json=settings_payload)
        if response.status_code != 200:
            raise SystemExit(f"settings update failed: {response.status_code} {response.text[:400]}")
        masked = response.json()["settings"]
        report["configured"] = {
            "text_model": masked["text"]["fast_llm"]["model"],
            "image_service": masked["image"]["service_type"],
            "video_service": masked["video"]["service_type"],
            "video_model": masked["video"]["doubao"]["model"],
            "voice_provider": masked["voice"]["provider"],
            "voice_resource": masked["voice"]["volc_resource_id"],
            "keys": {
                "fast_llm": masked["text"]["fast_llm"]["api_key"],
                "image": masked["image"]["ali_token_plan"]["api_key"],
                "video": masked["video"]["doubao"]["api_key"],
                "voice": masked["voice"]["volc_api_key"],
            },
        }
        print(json.dumps(report["configured"], ensure_ascii=False, indent=2))

        # --------------------------------------------------------- connection tests
        print("[3/6] running connection tests (text / image / video / voice)")
        tests = {}
        for category in ("text", "video", "voice", "image"):
            started = time.time()
            result = client.post(f"/settings/test/{category}")
            body = result.json() if result.status_code == 200 else result.text
            tests[category] = body
            ok = result.status_code == 200 and all(item.get("success") for item in body)
            print(f"  {category}: {'OK' if ok else 'FAIL'} ({time.time() - started:.1f}s)")
            for item in body if isinstance(body, list) else []:
                print(f"    - {item.get('target')}: {item.get('success')} {item.get('message')}")
        report["tests"] = tests
        if not all(isinstance(v, list) and all(i.get("success") for i in v) for v in tests.values()):
            raise SystemExit("connection tests failed — see report/tests")

        # -------------------------------------------------------------- workflow
        print("[4/6] submitting the 10s short-drama workflow (2 scenes x 5s)")
        submitted = client.post(
            "/workflow/generate",
            json={
                "script": SCRIPT_YAML,
                "video_type": "short_drama",
                "scene_images": {
                    "scene_001": make_scene_image("street"),
                    "scene_002": make_scene_image("cafe"),
                },
                "config": {
                    "video_fps": 24,
                    "video_duration": 5.0,
                    "image_width": 1280,
                    "image_height": 720,
                    "add_transitions": False,
                    "transition_duration": 0.0,
                    "add_subtitles": True,
                    "enable_character_references": False,
                    "max_concurrent_requests": 2,
                },
            },
        )
        if submitted.status_code != 200:
            raise SystemExit(f"workflow submit failed: {submitted.status_code} {submitted.text[:500]}")
        task_id = submitted.json()["task_id"]
        report["task_id"] = task_id
        print(f"      task_id = {task_id}")

        print("[5/6] polling the task (video generation takes a few minutes)")
        started = time.time()
        final = None
        last_progress = -1
        while time.time() - started < 1800:
            status = client.get(f"/tasks/{task_id}")
            if status.status_code != 200:
                time.sleep(2)
                continue
            payload = status.json()
            progress = int(payload.get("progress") or 0)
            if progress != last_progress:
                print(f"      {progress:3d}%  {payload.get('message') or ''}")
                last_progress = progress
            if payload.get("status") in ("completed", "failed", "cancelled"):
                final = payload
                break
            time.sleep(4)
        if final is None:
            raise SystemExit("workflow timed out")
        report["task"] = {k: final.get(k) for k in ("status", "progress", "message", "error")}
        print(f"      final status: {final.get('status')}")
        (artifacts / "task.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        if final.get("status") != "completed":
            raise SystemExit(f"workflow failed: {json.dumps(final.get('error'), ensure_ascii=False)[:600]}")

        result = final.get("result") or {}
        video_url = result.get("video_url")
        report["result"] = {
            "video_url": video_url,
            "scene_count": result.get("scene_count"),
            "character_count": result.get("character_count"),
            "duration_s": result.get("duration"),
        }
        if not video_url:
            raise SystemExit("workflow completed without a video_url")

        # ------------------------------------------------------------- download
        print("[6/6] downloading + verifying the final video")
        target = artifacts / (re.sub(r"[^A-Za-z0-9_.-]", "_", Path(video_url).name) or "final.mp4")
        with httpx.stream("GET", f"{base}{video_url}" if video_url.startswith("/") else video_url,
                          timeout=300.0, follow_redirects=True) as stream:
            stream.raise_for_status()
            with target.open("wb") as handle:
                for chunk in stream.iter_bytes():
                    handle.write(chunk)
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"      saved {target} ({size_mb:.1f} MB)")

        probe = ffprobe(target)
        streams = probe.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(probe.get("format", {}).get("duration") or 0)
        report["video"] = {
            "path": str(target),
            "size_mb": round(size_mb, 2),
            "duration_s": round(duration, 2),
            "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}",
            "fps": video_stream.get("r_frame_rate"),
            "video_codec": video_stream.get("codec_name"),
            "has_audio": audio_stream is not None,
            "audio_codec": (audio_stream or {}).get("codec_name"),
        }
        print(json.dumps(report["video"], ensure_ascii=False, indent=2))

        (artifacts / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # Narration proof: the composer writes one audio file per scene into
        # the temp project before mixing it onto the timeline.
        project_output = REPO_ROOT / "backend" / "temp_projects" / task_id / "output"
        audio_dir = project_output / "final" / "audio"
        if not audio_dir.exists():
            audio_dir = project_output / "audio"
        narration_files = sorted(audio_dir.glob("*.mp3")) + sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        report["narration"] = {
            "dir": str(audio_dir),
            "files": [f.name for f in narration_files],
            "total_bytes": sum(f.stat().st_size for f in narration_files),
        }
        print(f"      narration files: {report['narration']['files']}")

        problems = []
        if not narration_files:
            problems.append("no narration audio was synthesized (TTS did not reach the composer)")
        if not (8.0 <= duration <= 13.0):
            problems.append(f"duration {duration:.2f}s outside the 8-13s window")
        if not audio_stream:
            problems.append("no audio stream (TTS narration missing)")
        if not video_stream.get("width"):
            problems.append("no video stream")
        report["verdict"] = "PASS" if not problems else "FAIL"
        report["problems"] = problems
        (artifacts / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nVERDICT: {report['verdict']}")
        for problem in problems:
            print(f"  - {problem}")
        return 0 if not problems else 1
    finally:
        client.close()
        backend.terminate()
        try:
            backend.wait(timeout=20)
        except subprocess.TimeoutExpired:
            backend.kill()
        log_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
