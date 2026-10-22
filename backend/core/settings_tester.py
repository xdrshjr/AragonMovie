"""Connection testers for the five settings categories.

Each test is explicitly user-initiated (Settings UI "测试连接" button) and
must never raise: every outcome becomes a :class:`ConnectionTestResult`.

Verification levels
-------------------
- ``full``    : a real generation-style request succeeded (LLM chat probe,
                TTS speech probe).
- ``partial`` : the gateway answered and did NOT reject the credentials,
                but no cheap standard endpoint exists to fully verify a
                generation (video/image gateways typically have no free
                "/models" route). The result says so explicitly instead of
                pretending a generation was verified.
"""
import time
from typing import List, Optional

import httpx

from backend.core.settings_models import (
    ConnectionTestResult,
    ModelSettings,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

TIMEOUT = httpx.Timeout(15.0, connect=8.0)
_DETAIL_LIMIT = 300


def _excerpt(body: str) -> str:
    body = (body or "").strip()
    return body[:_DETAIL_LIMIT] + ("..." if len(body) > _DETAIL_LIMIT else "")


def _latency(start: float) -> int:
    return int((time.time() - start) * 1000)


def _base(url: str) -> str:
    return (url or "").rstrip("/")


async def _probe_models(
    client: httpx.AsyncClient, base_url: str, api_key: str, *, path: str = "/models"
) -> ConnectionTestResult:
    """GET a models-style endpoint: 200 -> ok, 401/403 -> bad key, other -> partial."""
    start = time.time()
    try:
        resp = await client.get(
            f"{_base(base_url)}{path}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        latency = _latency(start)
        if resp.status_code == 200:
            return ConnectionTestResult(
                category="text", target="",
                success=True, latency_ms=latency,
                message="认证与连接正常",
                verified="partial",
            )
        if resp.status_code in (401, 403):
            return ConnectionTestResult(
                category="text", target="",
                success=False, latency_ms=latency,
                message="API Key 无效或无权限",
                detail=_excerpt(resp.text), verified="full",
            )
        # 404/405 etc.: reachable, endpoint not offered -> partial pass
        return ConnectionTestResult(
            category="text", target="",
            success=True, latency_ms=latency,
            message=f"服务可达（网关不支持 {path} 探测，仅验证连通性）",
            detail=_excerpt(resp.text), verified="partial",
        )
    except httpx.HTTPError as e:
        return ConnectionTestResult(
            category="text", target="",
            success=False, latency_ms=_latency(start),
            message=f"连接失败: {e.__class__.__name__}",
            detail=str(e), verified="partial",
        )


async def _test_llm(
    client: httpx.AsyncClient, name: str, api_url: str, api_key: str, model: str
) -> ConnectionTestResult:
    """Minimal chat/completions round-trip = full verification."""
    start = time.time()
    if not api_key:
        return ConnectionTestResult(
            category="text", target=name, success=False,
            message="未配置 API Key", verified="full",
        )
    if not model:
        return ConnectionTestResult(
            category="text", target=name, success=False,
            message="未配置模型名称", verified="full",
        )
    try:
        resp = await client.post(
            f"{_base(api_url)}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            },
        )
        latency = _latency(start)
        if resp.status_code == 200:
            body = resp.json()
            reply = ""
            try:
                reply = body["choices"][0]["message"]["content"]
            except Exception:  # noqa: BLE001
                pass
            return ConnectionTestResult(
                category="text", target=name, success=True,
                latency_ms=latency,
                message=f"对话测试成功（模型返回: {reply[:40]!r}）",
                verified="full",
            )
        return ConnectionTestResult(
            category="text", target=name, success=False,
            latency_ms=latency,
            message=f"API 返回 {resp.status_code}",
            detail=_excerpt(resp.text), verified="full",
        )
    except httpx.HTTPError as e:
        return ConnectionTestResult(
            category="text", target=name, success=False,
            latency_ms=_latency(start),
            message=f"连接失败: {e.__class__.__name__}",
            detail=str(e), verified="full",
        )
    except ValueError as e:
        return ConnectionTestResult(
            category="text", target=name, success=False,
            latency_ms=_latency(start),
            message="响应不是有效 JSON",
            detail=str(e), verified="full",
        )


async def test_text(settings: ModelSettings) -> List[ConnectionTestResult]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        fast = settings.text.fast_llm
        judge = settings.text.judge_llm
        return [
            await _test_llm(client, "fast_llm", fast.api_url, fast.api_key or "", fast.model),
            await _test_llm(client, "judge_llm", judge.api_url, judge.api_key or "", judge.model),
        ]


async def test_voice(settings: ModelSettings) -> List[ConnectionTestResult]:
    """Full verification via a minimal speech request (transport-aware).

    The transport and endpoint come from ``services.tts_service`` so the probe
    can never drift from what the pipeline will actually do.
    """
    from services.tts_service import native_endpoint_for, resolve_tts_transport

    voice = settings.voice
    name = "tts"
    has_native_key = bool(voice.native_api_key)
    transport = resolve_tts_transport(
        voice.base_url,
        voice.provider,
        has_native_key=has_native_key,
        strict=False,
    )

    if transport == "volc_tts2":
        from services.volc_tts_service import VolcTTS2Service, VolcTTSError

        volc_key = voice.volc_api_key or ""
        if not volc_key:
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                message=(
                    "未配置火山引擎语音合成 2.0 的 API Key："
                    "请在「语音合成」里选择火山 TTS 2.0 并填写 API Key"
                ),
                verified="full",
            )]
        start = time.time()
        service = VolcTTS2Service(
            api_key=volc_key,
            resource_id=voice.volc_resource_id,
            voice=voice.volc_voice,
        )
        try:
            audio = await service.synthesize("你好", timeout=45.0)
            return [ConnectionTestResult(
                category="voice", target=name, success=True,
                latency_ms=_latency(start),
                message=(
                    f"火山 TTS 2.0 合成成功（{voice.volc_resource_id}，"
                    f"{voice.volc_voice}，返回 {len(audio)} 字节音频）"
                ),
                verified="full",
            )]
        except VolcTTSError as e:
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                latency_ms=_latency(start),
                message=str(e)[:200],
                detail=str(e),
                verified="full",
            )]

    if transport == "dashscope_native":
        api_key = voice.native_api_key or voice.api_key
        if not api_key:
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                message=(
                    "未配置 DashScope Key：该网关没有 HTTP 合成接口，"
                    "请在“语音合成”里切换 TTS 通道为 dashscope_native 并填写 DashScope Key"
                ),
                verified="full",
            )]
        native_model = voice.native_model or "qwen-tts"
        url = f"{voice.native_base_url.rstrip('/')}{native_endpoint_for(native_model)}"
        payload = {
            "model": native_model,
            "input": {"text": "你好", "voice": voice.native_voice or voice.default_voice},
        }
    else:
        api_key = voice.api_key
        if not api_key:
            from services.tts_service import is_known_broken_speech_gateway

            if is_known_broken_speech_gateway(voice.base_url):
                return [ConnectionTestResult(
                    category="voice", target=name, success=False,
                    message=(
                        "该网关没有一次性 HTTP 合成接口：请切换 TTS 通道为 "
                        "dashscope_native 并填写 DashScope Key，或改用其他 "
                        "OpenAI 兼容 TTS 网关"
                    ),
                    verified="full",
                )]
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                message="未配置 API Key", verified="full",
            )]
        url = f"{_base(voice.base_url)}/audio/speech"
        payload = {
            "model": voice.model,
            "voice": voice.default_voice,
            "input": "你好",
            "response_format": voice.default_format,
        }

    start = time.time()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            latency = _latency(start)
            if resp.status_code == 200:
                size = len(resp.content)
                if transport == "dashscope_native":
                    # Native synthesis answers JSON (audio url/base64), not raw bytes
                    audio = ((resp.json().get("output") or {}).get("audio") or {})
                    size = len(audio.get("url") or audio.get("data") or "")
                    if not size:
                        return [ConnectionTestResult(
                            category="voice", target=name, success=False,
                            latency_ms=latency,
                            message=(
                                "接口可达但没有返回音频：当前原生模型可能只支持 "
                                "WebSocket 实时合成，请改用 qwen-tts / cosyvoice-v2"
                            ),
                            detail=_excerpt(resp.text), verified="partial",
                        )]
                return [ConnectionTestResult(
                    category="voice", target=name, success=True,
                    latency_ms=latency,
                    message=(
                        f"语音合成测试成功（{transport}，返回 {size} 字节音频）"
                        if transport == "openai_compatible"
                        else f"语音合成测试成功（{transport}，音频 {size} 字节）"
                    ),
                    verified="full",
                )]
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                latency_ms=latency,
                message=f"API 返回 {resp.status_code}（{transport}）",
                detail=_excerpt(resp.text), verified="full",
            )]
        except httpx.HTTPError as e:
            return [ConnectionTestResult(
                category="voice", target=name, success=False,
                latency_ms=_latency(start),
                message=f"连接失败: {e.__class__.__name__}",
                detail=str(e), verified="full",
            )]


async def _test_doubao_video(
    client: httpx.AsyncClient, config
) -> ConnectionTestResult:
    """Probe the Volcano Ark key cheaply: list models instead of generating."""
    if not config.api_key:
        return ConnectionTestResult(
            category="video", target="doubao", success=False,
            message="未配置 API Key", verified="full",
        )
    root = config.base_url.rstrip("/")
    if root.endswith("/api/v3"):
        root = root[: -len("/api/v3")]
    start = time.time()
    try:
        resp = await client.get(
            f"{root}/api/v3/models",
            headers={"Authorization": f"Bearer {config.api_key}"},
        )
        latency = _latency(start)
        if resp.status_code in (401, 403):
            return ConnectionTestResult(
                category="video", target="doubao", success=False,
                latency_ms=latency,
                message="Ark API Key 无效或无权限",
                detail=_excerpt(resp.text), verified="full",
            )
        if resp.status_code != 200:
            return ConnectionTestResult(
                category="video", target="doubao", success=False,
                latency_ms=latency,
                message=f"Ark 返回 {resp.status_code}",
                detail=_excerpt(resp.text), verified="partial",
            )
        ids = {m.get("id") for m in (resp.json().get("data") or [])}
        model_ok = config.model in ids
        return ConnectionTestResult(
            category="video", target="doubao", success=True,
            latency_ms=latency,
            message=(
                f"{config.model}: 认证通过，模型已开通"
                if model_ok
                else f"认证通过，但 {config.model} 不在可用模型列表中"
            ),
            verified="partial",
        )
    except httpx.HTTPError as e:
        return ConnectionTestResult(
            category="video", target="doubao", success=False,
            latency_ms=_latency(start),
            message=f"连接失败: {e.__class__.__name__}",
            detail=str(e), verified="partial",
        )


async def _test_video_provider(
    client: httpx.AsyncClient, name: str, base_url: str, api_key: str, model: str
) -> ConnectionTestResult:
    if not api_key:
        # Only surface as failure when this provider is the selected one.
        return ConnectionTestResult(
            category="video", target=name, success=False,
            message="未配置 API Key", verified="full",
        )
    result = await _probe_models(client, base_url, api_key)
    return result.model_copy(update={
        "category": "video",
        "target": name,
        "message": f"{model}: {result.message}" if model else result.message,
    })


async def test_video(settings: ModelSettings) -> List[ConnectionTestResult]:
    video = settings.video
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        selected = video.service_type
        providers = [
            ("veo3", video.veo3.base_url, video.veo3.api_key or "", video.veo3.model),
            ("sora2", video.sora2.base_url, video.sora2.api_key or "", video.sora2.model),
            ("ali_token_plan", video.ali_token_plan.base_url,
             video.ali_token_plan.api_key or "", video.ali_token_plan.model),
        ]
        results = []
        for name, url, key, model in providers:
            r = await _test_video_provider(client, name, url, key, model)
            if not key and name != selected:
                # Unconfigured alternative provider: not an error, just skip.
                continue
            results.append(r)
        doubao_cfg = getattr(video, "doubao", None)
        if doubao_cfg is not None and (doubao_cfg.api_key or selected == "doubao"):
            results.append(await _test_doubao_video(client, doubao_cfg))
        return results


async def _test_image_provider(
    client: httpx.AsyncClient, name: str, base_url: str, api_key: str,
    endpoint: str, model: str,
) -> ConnectionTestResult:
    if not api_key:
        return ConnectionTestResult(
            category="image", target=name, success=False,
            message="未配置 API Key", verified="full",
        )
    if name == "midjourney":
        # Midjourney proxies have no models endpoint; probe base reachability.
        start = time.time()
        try:
            resp = await client.get(
                f"{_base(base_url)}/mj/task/list",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            latency = _latency(start)
            if resp.status_code in (401, 403):
                return ConnectionTestResult(
                    category="image", target=name, success=False,
                    latency_ms=latency, message="API Key 无效或无权限",
                    detail=_excerpt(resp.text), verified="full",
                )
            return ConnectionTestResult(
                category="image", target=name, success=True, latency_ms=latency,
                message="代理可达（Midjourney 无标准探测端点，仅验证连通性）",
                detail=_excerpt(resp.text), verified="partial",
            )
        except httpx.HTTPError as e:
            return ConnectionTestResult(
                category="image", target=name, success=False,
                latency_ms=_latency(start),
                message=f"连接失败: {e.__class__.__name__}",
                detail=str(e), verified="partial",
            )

    result = await _probe_models(client, base_url, api_key)
    return result.model_copy(update={
        "category": "image",
        "target": name,
        "message": f"{model}: {result.message}" if model else result.message,
    })


async def test_image(settings: ModelSettings) -> List[ConnectionTestResult]:
    image = settings.image
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        selected = image.service_type
        providers = [
            ("doubao", image.doubao.base_url, image.doubao.api_key or "",
             image.doubao.endpoint, image.doubao.model),
            ("nano_banana", image.nano_banana.base_url, image.nano_banana.api_key or "",
             image.nano_banana.endpoint, image.nano_banana.model),
            ("midjourney", image.midjourney.base_url, image.midjourney.api_key or "",
             "", image.midjourney.bot_type),
            ("ali_token_plan", image.ali_token_plan.base_url,
             image.ali_token_plan.api_key or "", image.ali_token_plan.endpoint,
             image.ali_token_plan.model),
        ]
        results = []
        for name, url, key, endpoint, model in providers:
            if not key and name != selected:
                continue  # unconfigured alternative provider: skip quietly
            results.append(await _test_image_provider(
                client, name, url, key, endpoint, model))
        return results


async def test_agent(settings: ModelSettings) -> List[ConnectionTestResult]:
    """Validate agent LLM config; for OpenAI-compatible endpoints also probe
    the models endpoint (anthropic uses a different header, google has none)."""
    agent = settings.agent
    problems = []
    if not agent.api_key:
        problems.append("未配置 API Key")
    if not agent.model:
        problems.append("未配置模型名称")
    if problems:
        return [ConnectionTestResult(
            category="agent", target="agent_llm", success=False,
            message="；".join(problems), verified="full",
        )]

    if agent.provider == "openai":
        base = agent.base_url or "https://api.openai.com/v1"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await _probe_models(client, base, agent.api_key)
            return [r.model_copy(update={
                "category": "agent", "target": "agent_llm",
                "message": f"{agent.model}: {r.message}",
            })]
    if agent.provider == "anthropic":
        base = _base(agent.base_url or "https://api.anthropic.com")
        start = time.time()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                resp = await client.get(
                    f"{base}/v1/models",
                    headers={
                        "x-api-key": agent.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                latency = _latency(start)
                if resp.status_code == 200:
                    return [ConnectionTestResult(
                        category="agent", target="agent_llm", success=True,
                        latency_ms=latency, message=f"{agent.model}: 认证与连接正常",
                        verified="partial",
                    )]
                if resp.status_code in (401, 403):
                    return [ConnectionTestResult(
                        category="agent", target="agent_llm", success=False,
                        latency_ms=latency, message="API Key 无效或无权限",
                        detail=_excerpt(resp.text), verified="full",
                    )]
                return [ConnectionTestResult(
                    category="agent", target="agent_llm", success=True,
                    latency_ms=latency,
                    message=f"{agent.model}: 服务可达（仅验证连通性）",
                    detail=_excerpt(resp.text), verified="partial",
                )]
            except httpx.HTTPError as e:
                return [ConnectionTestResult(
                    category="agent", target="agent_llm", success=False,
                    latency_ms=_latency(start),
                    message=f"连接失败: {e.__class__.__name__}",
                    detail=str(e), verified="partial",
                )]
    # google: no cheap probe endpoint; configuration check only
    return [ConnectionTestResult(
        category="agent", target="agent_llm", success=True,
        message=f"{agent.model}: 配置完整（Google 端点无通用探测接口，未做连通验证）",
        verified="partial",
    )]


TESTERS = {
    "text": test_text,
    "voice": test_voice,
    "video": test_video,
    "image": test_image,
    "agent": test_agent,
}


async def run_tests(category: str, settings: ModelSettings) -> List[ConnectionTestResult]:
    tester = TESTERS.get(category)
    if tester is None:
        raise ValueError(f"Unknown settings category: {category}")
    try:
        return await tester(settings)
    except Exception as e:  # noqa: BLE001 - never leak exceptions to the UI
        logger.error(f"Settings test crashed for category={category}: {e}")
        return [ConnectionTestResult(
            category=category, target="", success=False,
            message=f"测试过程出错: {e.__class__.__name__}",
            detail=str(e), verified="full",
        )]
