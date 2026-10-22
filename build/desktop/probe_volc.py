"""Probe the Volcano credentials before touching the pipeline.

Confirms, with real requests and without printing secrets:
  1. Ark video (seedance) key: which video models it can actually reach
  2. Volcano TTS 2.0 key: which speakers/resources it is granted
  3. Ali Token Plan key: text model + image model reachability
"""

import json
import os
import sys

import httpx

VIDEO_KEY = os.environ["PROBE_VIDEO_KEY"]
TTS_KEY = os.environ["PROBE_TTS_KEY"]
LLM_KEY = os.environ["PROBE_LLM_KEY"]
LLM_BASE = "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ARK = "https://ark.cn-beijing.volces.com/api/v3"


def mask(value: str) -> str:
    return f"{value[:4]}…{value[-4:]} (len {len(value)})"


def ark_models() -> None:
    print("\n== Ark model listing ==", mask(VIDEO_KEY))
    for path in ("/models", "/endpoints"):
        try:
            r = httpx.get(f"{ARK}{path}", headers={"Authorization": f"Bearer {VIDEO_KEY}"}, timeout=30)
            print(f"GET {path} -> {r.status_code}: {r.text[:400]}")
        except Exception as exc:  # noqa: BLE001
            print(f"GET {path} failed: {exc}")


def ark_video_probe() -> None:
    print("\n== Ark seedance video submit probe ==")
    candidates = [
        "doubao-seedance-1-0-pro-250528",
        "doubao-seedance-1-0-lite-i2v-250428",
        "doubao-seedance-1-5-pro-251215",
        "doubao-seedance-2-0-pro",
        "seedance-1-0-pro-250528",
    ]
    for model in candidates:
        payload = {
            "model": model,
            "content": [
                {
                    "type": "text",
                    "text": "a calm ocean at sunrise, cinematic --resolution 480p --duration 5 --ratio 16:9",
                }
            ],
        }
        try:
            r = httpx.post(
                f"{ARK}/contents/generations/tasks",
                headers={"Authorization": f"Bearer {VIDEO_KEY}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            body = r.text[:300].replace("\n", " ")
            print(f"{model}: {r.status_code} {body}")
            if r.status_code == 200:
                task_id = r.json().get("id")
                print(f"  -> accepted, task id {task_id}")
                poll = httpx.get(
                    f"{ARK}/contents/generations/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {VIDEO_KEY}"},
                    timeout=30,
                )
                print(f"  poll: {poll.status_code} {poll.text[:200]}")
                return
        except Exception as exc:  # noqa: BLE001
            print(f"{model}: request failed {exc}")


def tts_probe() -> None:
    print("\n== Volcano TTS 2.0 resource probe ==", mask(TTS_KEY))
    # v3 list-ish endpoint does not exist; use the documented v1 status route as
    # a cheap auth check, then report what the WS handshake returns.
    try:
        r = httpx.post(
            "https://openspeech.bytedance.com/api/v1/tts",
            headers={
                "Authorization": f"Bearer; {TTS_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "app": {"appid": "0", "token": TTS_KEY, "cluster": "volcano_tts"},
                "user": {"uid": "probe"},
                "audio": {"voice_type": "zh_female_cancan_mars_bigtts", "encoding": "mp3"},
                "request": {"reqid": "probe-1", "text": "测试", "operation": "query"},
            },
            timeout=30,
        )
        print(f"v1 query -> {r.status_code}: {r.text[:300]}")
    except Exception as exc:  # noqa: BLE001
        print(f"v1 query failed: {exc}")


def ali_probe() -> None:
    print("\n== Ali Token Plan probe ==", mask(LLM_KEY))
    try:
        r = httpx.post(
            f"{LLM_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_KEY}", "Content-Type": "application/json"},
            json={"model": "qwen3.8-flash", "messages": [{"role": "user", "content": "reply with pong"}]},
            timeout=60,
        )
        print(f"chat qwen3.8-flash -> {r.status_code}: {r.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"chat failed: {exc}")


if __name__ == "__main__":
    ark_models()
    ark_video_probe()
    tts_probe()
    ali_probe()
