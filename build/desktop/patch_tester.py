"""Patch settings_tester.py: Doubao (Ark Seedance) video probe + Volcano TTS 2.0 probe."""

from pathlib import Path

path = Path("backend/core/settings_tester.py")
text = path.read_text(encoding="utf-8")
EOL = "\r\n" if "\r\n" in text else "\n"


def must_replace(source: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"MISSING {label}:\n{old[:400]}")
    print(f"ok {label}")
    return source.replace(old, new, 1)


# ---------------------------------------------------------------- video probe
old_video = (
    "async def test_video(settings: ModelSettings) -> List[ConnectionTestResult]:" + EOL
    + "    video = settings.video" + EOL
    + "    async with httpx.AsyncClient(timeout=TIMEOUT) as client:" + EOL
    + "        selected = video.service_type" + EOL
    + "        providers = [" + EOL
    + '            ("veo3", video.veo3.base_url, video.veo3.api_key or "", video.veo3.model),' + EOL
    + '            ("sora2", video.sora2.base_url, video.sora2.api_key or "", video.sora2.model),' + EOL
    + '            ("ali_token_plan", video.ali_token_plan.base_url,' + EOL
    + '             video.ali_token_plan.api_key or "", video.ali_token_plan.model),' + EOL
    + "        ]" + EOL
    + "        results = []" + EOL
    + "        for name, url, key, model in providers:" + EOL
    + "            r = await _test_video_provider(client, name, url, key, model)" + EOL
    + "            if not key and name != selected:" + EOL
    + "                # Unconfigured alternative provider: not an error, just skip." + EOL
    + "                continue" + EOL
    + "            results.append(r)" + EOL
    + "        return results"
)

new_video = (
    "async def _test_doubao_video(" + EOL
    + "    client: httpx.AsyncClient, config" + EOL
    + ") -> ConnectionTestResult:" + EOL
    + '    """Probe the Volcano Ark key without spending a video generation."""' + EOL
    + "    if not config.api_key:" + EOL
    + "        return ConnectionTestResult(" + EOL
    + '            category="video", target="doubao", success=False,' + EOL
    + '            message="未配置 API Key", verified="full",' + EOL
    + "        )" + EOL
    + "    root = config.base_url.rstrip(\"/\")" + EOL
    + '    if root.endswith("/api/v3"):' + EOL
    + '        root = root[: -len("/api/v3")]' + EOL
    + "    start = time.time()" + EOL
    + "    try:" + EOL
    + "        resp = await client.get(" + EOL
    + '            f"{root}/api/v3/models",' + EOL
    + '            headers={"Authorization": f"Bearer {config.api_key}"},' + EOL
    + "        )" + EOL
    + "        latency = _latency(start)" + EOL
    + "        if resp.status_code in (401, 403):" + EOL
    + "            return ConnectionTestResult(" + EOL
    + '                category="video", target="doubao", success=False,' + EOL
    + "                latency_ms=latency," + EOL
    + '                message="Ark API Key 无效或无权限",' + EOL
    + '                detail=_excerpt(resp.text), verified="full",' + EOL
    + "            )" + EOL
    + "        if resp.status_code != 200:" + EOL
    + "            return ConnectionTestResult(" + EOL
    + '                category="video", target="doubao", success=False,' + EOL
    + "                latency_ms=latency," + EOL
    + '                message=f"Ark 返回 {resp.status_code}",' + EOL
    + '                detail=_excerpt(resp.text), verified="partial",' + EOL
    + "            )" + EOL
    + "        ids = {m.get(\"id\") for m in (resp.json().get(\"data\") or [])}" + EOL
    + "        model_ok = config.model in ids" + EOL
    + "        return ConnectionTestResult(" + EOL
    + '            category="video", target="doubao", success=True,' + EOL
    + "            latency_ms=latency," + EOL
    + "            message=(" + EOL
    + '                f"{config.model}: 认证通过，模型已开通"' + EOL
    + "                if model_ok" + EOL
    + '                else f"认证通过，但模型 {config.model} 不在可用列表中（可改用其他 Seedance 模型 ID）"' + EOL
    + "            )," + EOL
    + '            verified="partial",' + EOL
    + "        )" + EOL
    + "    except httpx.HTTPError as e:" + EOL
    + "        return ConnectionTestResult(" + EOL
    + '            category="video", target="doubao", success=False,' + EOL
    + "            latency_ms=_latency(start)," + EOL
    + '            message=f"连接失败: {e.__class__.__name__}",' + EOL
    + '            detail=str(e), verified="partial",' + EOL
    + "        )" + EOL
    + "" + EOL
    + "" + EOL
    + "async def test_video(settings: ModelSettings) -> List[ConnectionTestResult]:" + EOL
    + "    video = settings.video" + EOL
    + "    async with httpx.AsyncClient(timeout=TIMEOUT) as client:" + EOL
    + "        selected = video.service_type" + EOL
    + "        providers = [" + EOL
    + '            ("veo3", video.veo3.base_url, video.veo3.api_key or "", video.veo3.model),' + EOL
    + '            ("sora2", video.sora2.base_url, video.sora2.api_key or "", video.sora2.model),' + EOL
    + '            ("ali_token_plan", video.ali_token_plan.base_url,' + EOL
    + '             video.ali_token_plan.api_key or "", video.ali_token_plan.model),' + EOL
    + "        ]" + EOL
    + "        results = []" + EOL
    + "        for name, url, key, model in providers:" + EOL
    + "            r = await _test_video_provider(client, name, url, key, model)" + EOL
    + "            if not key and name != selected:" + EOL
    + "                # Unconfigured alternative provider: not an error, just skip." + EOL
    + "                continue" + EOL
    + "            results.append(r)" + EOL
    + "        doubao_cfg = getattr(video, \"doubao\", None)" + EOL
    + "        if doubao_cfg is not None and (doubao_cfg.api_key or selected == \"doubao\"):" + EOL
    + "            results.append(await _test_doubao_video(client, doubao_cfg))" + EOL
    + "        return results"
)
text = must_replace(text, old_video, new_video, "test_video")

# ---------------------------------------------------------------- voice probe
old_voice_head = (
    "    from services.tts_service import native_endpoint_for, resolve_tts_transport" + EOL
    + "" + EOL
    + "    voice = settings.voice" + EOL
    + '    name = "tts"' + EOL
    + "    has_native_key = bool(voice.native_api_key)" + EOL
    + "    transport = resolve_tts_transport(" + EOL
    + "        voice.base_url," + EOL
    + "        voice.provider," + EOL
    + "        has_native_key=has_native_key," + EOL
    + "        strict=False," + EOL
    + "    )" + EOL
)
new_voice_head = (
    "    from services.tts_service import native_endpoint_for, resolve_tts_transport" + EOL
    + "" + EOL
    + "    voice = settings.voice" + EOL
    + '    name = "tts"' + EOL
    + "    has_native_key = bool(voice.native_api_key)" + EOL
    + "    transport = resolve_tts_transport(" + EOL
    + "        voice.base_url," + EOL
    + "        voice.provider," + EOL
    + "        has_native_key=has_native_key," + EOL
    + "        strict=False," + EOL
    + "    )" + EOL
    + "" + EOL
    + '    if transport == "volc_tts2":' + EOL
    + "        from services.volc_tts_service import VolcTTS2Service, VolcTTSError" + EOL
    + "" + EOL
    + "        volc_key = voice.volc_api_key or \"\"" + EOL
    + "        if not volc_key:" + EOL
    + "            return [ConnectionTestResult(" + EOL
    + '                category="voice", target=name, success=False,' + EOL
    + "                message=(" + EOL
    + '                    "未配置火山引擎语音合成 2.0 的 API Key："' + EOL
    + '                    "请在“语音合成”里选择 火山 TTS 2.0 并填写 API Key"' + EOL
    + "                )," + EOL
    + '                verified="full",' + EOL
    + "            )]" + EOL
    + "        start = time.time()" + EOL
    + "        service = VolcTTS2Service(" + EOL
    + "            api_key=volc_key," + EOL
    + "            resource_id=voice.volc_resource_id," + EOL
    + "            voice=voice.volc_voice," + EOL
    + "        )" + EOL
    + "        try:" + EOL
    + "            audio = await service.synthesize(\"你好\", timeout=45.0)" + EOL
    + "            return [ConnectionTestResult(" + EOL
    + '                category="voice", target=name, success=True,' + EOL
    + "                latency_ms=_latency(start)," + EOL
    + "                message=(" + EOL
    + '                    f"火山 TTS 2.0 合成成功（{voice.volc_resource_id}，"' + EOL
    + '                    f"{voice.volc_voice}，返回 {len(audio)} 字节音频）"' + EOL
    + "                )," + EOL
    + '                verified="full",' + EOL
    + "            )]" + EOL
    + "        except VolcTTSError as e:" + EOL
    + "            return [ConnectionTestResult(" + EOL
    + '                category="voice", target=name, success=False,' + EOL
    + "                latency_ms=_latency(start)," + EOL
    + "                message=str(e)[:200]," + EOL
    + "                detail=str(e)," + EOL
    + '                verified="full",' + EOL
    + "            )]" + EOL
    + "" + EOL
    + "    if transport == \"dashscope_native\":" + EOL
)
text = must_replace(text, old_voice_head + '    if transport == "dashscope_native":' + EOL, new_voice_head, "test_voice")

path.write_text(text, encoding="utf-8")
print("patched backend/core/settings_tester.py")
