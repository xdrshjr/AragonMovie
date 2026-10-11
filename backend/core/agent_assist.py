"""Agent-assisted configuration, powered by AragonAgent.

Two modes
---------
1. ``aragon`` (primary)  — the user-configured Agent LLM drives a real
   AragonAgent session through ``aragon exec --output-format stream-json``.
   The agent runs in ``--permission-mode strict`` with a file-tool
   allow-list (read_file / write_file / edit_file / list_dir / glob /
   grep) so it can read the project and edit exactly ONE file: the
   runtime settings JSON. Each NDJSON event is translated into a small
   normalized dict re-emitted to the caller (the SSE endpoint).

2. ``llm_fallback`` — when the aragon CLI is not installed but an
   OpenAI-compatible Agent LLM IS configured, a single-shot chat gives
   configuration advice plus an optional JSON patch the UI can apply.

Session continuity
------------------
Each conversation owns an aragon session id (``settings-<uuid>``); the
first turn uses ``--session-id``, later turns ``--resume``.

After every turn the settings file is checked for external changes; when
the agent edited it, the store re-validates + hot-applies and a
``settings_updated`` event is emitted so the UI refreshes.
"""
import asyncio
import json
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Tuple

from backend.core.settings_store import get_settings_store
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# aragon exec tool allow-list: file tools only. bash is deliberately absent.
ARAGON_ALLOW_TOOLS = ["read_file", "write_file", "edit_file", "list_dir", "glob", "grep"]

REPO_ROOT = Path(__file__).parent.parent.parent

# Windows: avoid a console window for the spawned node process
_CREATIONFLAGS = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

# Conversation bookkeeping: session_id -> {"started": bool}
_sessions: Dict[str, Dict] = {}


# ======================================================================
# aragon CLI detection & command resolution
# ======================================================================

class AragonCliInfo:
    def __init__(self, installed: bool, version: Optional[str] = None,
                 path: Optional[str] = None, note: str = ""):
        self.installed = installed
        self.version = version
        self.path = path
        self.note = note


_detect_cache: Optional[Tuple[AragonCliInfo, float]] = None
_DETECT_TTL = 30.0  # seconds


async def detect_aragon(cli_path: Optional[str] = None, force: bool = False) -> AragonCliInfo:
    """Locate the aragon CLI and read its version via ``aragon info --json``."""
    global _detect_cache
    now = asyncio.get_event_loop().time()
    if not force and _detect_cache is not None and now - _detect_cache[1] < _DETECT_TTL:
        return _detect_cache[0]

    info = await _detect_aragon_impl(cli_path or "aragon")
    _detect_cache = (info, now)
    return info


async def _detect_aragon_impl(cli_path: str) -> AragonCliInfo:
    cmd = _resolve_aragon_command(cli_path)
    if cmd is None:
        return AragonCliInfo(
            False, note=(
                "aragon CLI not found. Install with: npm i -g @aragon-agent/cli "
                "(requires Node.js >= 18)"
            )
        )
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, "info", "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            creationflags=_CREATIONFLAGS,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            try:
                payload = json.loads(out.decode("utf-8", errors="replace"))
                return AragonCliInfo(True, version=str(payload.get("cli", "")) or None,
                                     path=cli_path)
            except ValueError:
                return AragonCliInfo(True, path=cli_path)
        # info failed but the binary exists
        return AragonCliInfo(True, path=cli_path, note="aragon found, but 'info' failed")
    except (OSError, asyncio.TimeoutError) as e:
        return AragonCliInfo(False, note=f"aragon check failed: {e}")


def _resolve_aragon_command(cli_path: str) -> Optional[List[str]]:
    """Return the argv prefix that launches the aragon CLI, or None.

    Prefers invoking ``node <launcher.js>`` directly: it sidesteps the
    .cmd shim quoting problems on Windows and lets terminate() hit the
    real process.
    """
    node = shutil.which("node")

    # 1. Explicit absolute/relative path setting
    p = Path(cli_path)
    if p.is_absolute() and p.exists():
        return _command_for_path(str(p), node)

    # 2. On PATH
    which = shutil.which(cli_path)
    if which:
        return _command_for_path(which, node)
    return None


def _command_for_path(path: str, node: Optional[str]) -> Optional[List[str]]:
    lower = path.lower()
    if lower.endswith(".js"):
        if not node:
            return None
        return [node, path]
    if lower.endswith((".exe",)):
        return [path]
    if lower.endswith((".cmd", ".bat")):
        # npm shim: resolve .../npm/aragon.cmd -> .../npm/node_modules/@aragon-agent/cli/dist/launcher.js
        shim_dir = Path(path).parent
        launcher = shim_dir / "node_modules" / "@aragon-agent" / "cli" / "dist" / "launcher.js"
        if node and launcher.exists():
            return [node, str(launcher)]
        if os.name == "nt":
            # Fallback: cmd.exe wrapper (prompts travel via files, so args stay simple)
            return ["cmd.exe", "/c", path]
        return None
    if os.name == "nt":
        # Plain name on Windows resolved to something odd; give up cleanly.
        return None
    return [path]


# ======================================================================
# System prompt
# ======================================================================

def _settings_file_abs() -> str:
    return str(get_settings_store().file_path.resolve())


def build_system_prompt() -> str:
    settings_path = _settings_file_abs()
    return f"""You are the configuration assistant for AragonMovie (AI drama video generation system).

YOUR JOB: help the user configure model services through conversation, and when the user
asks for a change, apply it DIRECTLY by editing the settings file.

THE SETTINGS FILE (the only file you may modify):
  {settings_path}

Its JSON structure (fields under "settings"):
- text.fast_llm {{api_key, api_url, model}} - LLM for script polishing / prompt optimization
  text.judge_llm {{api_key, api_url, model}} - multimodal LLM for image consistency scoring
  text.enable_prompt_optimization (bool), text.enable_character_consistency_judge (bool)
- voice {{enabled(bool), api_key, base_url, model, default_voice, default_format
  (mp3/opus/aac/flac/wav/pcm), default_speed(0.25-4.0)}} - OpenAI-compatible TTS (/audio/speech)
- video.service_type ("veo3"|"sora2"|"ali_token_plan")
  video.veo3 {{api_key, base_url, endpoint, model, skip_upload}}
  video.sora2 {{api_key, base_url, endpoint, model, default_size, default_duration,
  default_style, watermark, private}}
  video.ali_token_plan {{api_key, base_url,
  endpoint(/api/v1/services/aigc/video-generation/video-synthesis),
  model(happyhorse-1.1-i2v), t2v_model(happyhorse-1.1-t2v),
  r2v_model(happyhorse-1.1-r2v), default_size, default_duration}} -
  Ali Token Plan (Ali Coding Plan) DashScope-native async gateway
- image.service_type ("doubao"|"nano_banana"|"midjourney"|"ali_token_plan")
  image.doubao {{api_key, base_url, endpoint, model, watermark}}
  image.nano_banana {{api_key, base_url, endpoint, model}}
  image.midjourney {{api_key, base_url, bot_type(MID_JOURNEY|NIJI_JOURNEY), poll_interval,
  max_poll_attempts, auto_upscale, upscale_index}}
  image.ali_token_plan {{api_key, base_url,
  endpoint(/api/v1/services/aigc/multimodal-generation/generation),
  model(wan2.7-image-pro)}}
- Ali Token Plan uses ONE shared key for text/voice/image/video; setting either
  video.ali_token_plan.api_key or image.ali_token_plan.api_key mirrors it to both.
  Default gateway: https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
  (image/video clients strip the /compatible-mode/v1 suffix automatically for the
  DashScope-native endpoints; text LLM uses the URL as-is).
  Default models: text qwen3.8-max, TTS qwen-audio-3.0-tts-plus, image wan2.7-image-pro,
  video happyhorse-1.1-i2v/t2v/r2v.
- agent {{enabled(bool), provider("openai"|"anthropic"|"google"), api_key, base_url, model,
  max_turns, timeout_seconds, aragon_cli_path}} - the LLM powering YOU

RULES:
1. You may READ any file in the project for context, but you may only WRITE/EDIT the
   settings file above. Never touch any other file.
2. Keep the file valid JSON. Keep the top-level "version" and "updated_at" keys; change
   only the fields the user asked about and leave everything else untouched.
3. api_key fields are plain strings holding REAL keys. When the user gives you a key,
   write it verbatim. Never invent or guess keys, URLs, or model names - if unsure, ask.
4. After editing, re-read the settings file and verify it parses as JSON before replying.
5. The backend hot-reloads this file after your turn - no restart is needed.
6. Reply in the user's language (default: Chinese). Keep answers concise and practical.
7. Useful knowledge: fast LLM and most gateways use OpenAI-compatible chat endpoints;
   judge LLM must support multimodal input; TTS uses /audio/speech; video/image services
   are submit+poll gateways whose base_url+endpoint form the full request URL."""


# ======================================================================
# Event normalization from aragon exec NDJSON
# ======================================================================

_FORWARDED_EVENTS = {"system", "text_delta", "tool_call", "tool_result", "assistant", "result"}


def normalize_exec_event(raw: Dict) -> Optional[Dict]:
    """Map one aragon exec NDJSON event to our wire format (or None to skip)."""
    etype = raw.get("type")
    if etype not in _FORWARDED_EVENTS:
        return None

    if etype == "system":
        return {
            "type": "system",
            "session_id": raw.get("sessionId"),
            "model": raw.get("model"),
            "tools": raw.get("tools", []),
        }
    if etype == "text_delta":
        return {"type": "text_delta", "text": raw.get("delta", "")}
    if etype == "tool_call":
        return {
            "type": "tool_call",
            "id": raw.get("id"),
            "name": raw.get("name"),
            "input": raw.get("input", {}),
        }
    if etype == "tool_result":
        content = raw.get("content", "")
        if isinstance(content, str):
            preview = content[:200]
        else:
            try:
                preview = json.dumps(content, ensure_ascii=False)[:200]
            except (TypeError, ValueError):
                preview = str(content)[:200]
        return {
            "type": "tool_result",
            "id": raw.get("id"),
            "name": raw.get("name"),
            "preview": preview,
            "is_error": bool(raw.get("is_error", False)),
        }
    if etype == "assistant":
        return {"type": "assistant", "text": raw.get("text", "")}
    if etype == "result":
        return {
            "type": "result",
            "stop_reason": raw.get("stopReason"),
            "usage": raw.get("usage"),
            "cost": raw.get("cost"),
            "session_id": raw.get("sessionId"),
        }
    return None


# ======================================================================
# The chat runner
# ======================================================================

class AgentAssistError(Exception):
    pass


def _agent_env(agent_cfg) -> Dict[str, str]:
    env = os.environ.copy()
    env["ARAGON_PROVIDER"] = agent_cfg.provider
    env["ARAGON_MODEL"] = agent_cfg.model
    if agent_cfg.base_url:
        env["ARAGON_BASE_URL"] = agent_cfg.base_url
    # Provider secrets
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        env.pop(var, None)
    if agent_cfg.provider == "openai":
        env["OPENAI_API_KEY"] = agent_cfg.api_key or ""
    elif agent_cfg.provider == "anthropic":
        env["ANTHROPIC_API_KEY"] = agent_cfg.api_key or ""
    elif agent_cfg.provider == "google":
        env["GOOGLE_API_KEY"] = agent_cfg.api_key or ""
    env["ARAGON_LOG_LEVEL"] = env.get("ARAGON_LOG_LEVEL", "error")
    return env


async def agent_chat_stream(
    message: str,
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict]:
    """Stream one assistant turn as normalized event dicts.

    Raises AgentAssistError only for pre-flight failures (nothing configured);
    runtime failures become {"type": "error"} events so the UI can show them.
    """
    store = get_settings_store()
    agent = store.current().agent

    if session_id is None:
        session_id = f"settings-{uuid.uuid4().hex[:12]}"
    yield {"type": "meta", "session_id": session_id, "mode": None}

    if not agent.api_key or not agent.model:
        raise AgentAssistError(
            "Agent LLM is not configured. Set provider / API key / model in Settings → Agent."
        )

    cli = await detect_aragon(agent.aragon_cli_path)
    if cli.installed:
        async for event in _run_aragon_turn(message, session_id, agent, cli):
            yield event
    elif agent.provider == "openai":
        yield {"type": "meta", "session_id": session_id, "mode": "llm_fallback",
               "note": cli.note}
        yield {"type": "status",
               "message": "aragon CLI 未安装，已降级为纯 LLM 建议模式（不会自动修改配置文件）"}
        async for event in _run_fallback_turn(message, agent):
            yield event
    else:
        raise AgentAssistError(
            f"aragon CLI is not installed and the fallback mode requires an OpenAI-compatible "
            f"provider. {cli.note}"
        )

    # Post-turn: pick up external edits made by the agent itself
    try:
        if store.reload_if_changed():
            yield {"type": "settings_updated", "settings": store.masked()}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to reload settings after agent turn: {e}")


async def _run_aragon_turn(message: str, session_id: str, agent, cli: AragonCliInfo):
    cmd_prefix = _resolve_aragon_command(agent.aragon_cli_path)
    if cmd_prefix is None:  # detected earlier but resolution raced
        yield {"type": "error", "message": "aragon CLI became unavailable"}
        return

    session_state = _sessions.setdefault(session_id, {"started": False})
    args: List[str] = list(cmd_prefix) + [
        "exec",
        "--output-format", "stream-json",
        "--permission-mode", "strict",
        "--allow-tool", ",".join(ARAGON_ALLOW_TOOLS),
        "--max-turns", str(agent.max_turns),
        "--max-duration", str(agent.timeout_seconds * 1000),
    ]
    if session_state["started"]:
        args += ["--resume", session_id]
    else:
        args += ["--session-id", session_id]
        session_state["started"] = True

    # Pass prompts via files to avoid any shell/quoting pitfalls on Windows
    prompt_file = _write_temp(message, suffix=".txt")
    system_file = _write_temp(build_system_prompt(), suffix=".md")
    args += ["--prompt-file", prompt_file, "--append-system-prompt-file", system_file]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=_agent_env(agent),
            creationflags=_CREATIONFLAGS,
        )
    except OSError as e:
        yield {"type": "error", "message": f"Failed to launch aragon: {e}"}
        return

    logger.info(f"aragon exec started | session={session_id} | pid={proc.pid}")

    saw_result = False
    try:
        assert proc.stdout is not None
        async for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line.decode("utf-8", errors="replace"))
            except ValueError:
                logger.debug(f"aragon exec non-JSON line: {line[:120]!r}")
                continue
            event = normalize_exec_event(raw)
            if event is not None:
                if event["type"] == "meta":
                    event = dict(event, mode="aragon")
                yield event
                if event["type"] == "result":
                    saw_result = True

        await asyncio.wait_for(proc.wait(), timeout=30)
        if not saw_result:
            stderr = b""
            if proc.stderr is not None:
                try:
                    stderr = await asyncio.wait_for(proc.stderr.read(), timeout=5)
                except asyncio.TimeoutError:
                    pass
            yield {
                "type": "error",
                "message": f"aragon exited without a result (code {proc.returncode})",
                "detail": stderr.decode("utf-8", errors="replace")[:500],
            }
    except asyncio.CancelledError:
        logger.info(f"aragon turn cancelled | session={session_id}")
        raise
    finally:
        _cleanup_temp(prompt_file)
        _cleanup_temp(system_file)
        if proc.returncode is None:
            try:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    proc.kill()
            except ProcessLookupError:
                pass


async def _run_fallback_turn(message: str, agent):
    """Single-shot LLM advice without file tools. Yields text_delta(s) + result."""
    from services.llm_service import LLMService

    base_url = agent.base_url or "https://api.openai.com/v1"
    service = LLMService(api_key=agent.api_key, api_url=base_url, model=agent.model)
    system = (
        build_system_prompt()
        + "\n\nFALLBACK MODE: you cannot edit files. Give precise advice. When you propose "
        "concrete setting changes, ALSO output one fenced ```json block containing a partial "
        "settings patch (same structure as the file, only changed fields, api_key=null unless "
        "the user provided a real key). The UI will offer an Apply button for that patch."
    )
    try:
        response = await service.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            temperature=0.3,
        )
        text = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not text:
            raise ValueError("empty response from agent LLM")
    except Exception as e:  # noqa: BLE001
        yield {"type": "error", "message": f"Agent LLM call failed: {e}"}
        return
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass

    yield {"type": "text_delta", "text": text}
    yield {"type": "assistant", "text": text}
    patch = extract_json_patch(text)
    yield {
        "type": "result",
        "stop_reason": "end_turn",
        "mode": "llm_fallback",
        "suggested_patch": patch,
    }


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json_patch(text: str) -> Optional[Dict]:
    """Pull the first fenced JSON object out of fallback advice."""
    match = _JSON_BLOCK_RE.search(text or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        return None


# ======================================================================
# Small helpers
# ======================================================================

def _write_temp(content: str, suffix: str = ".txt") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="aragonmovie_agent_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _cleanup_temp(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


async def get_agent_status() -> Dict:
    """Assemble AgentStatusResponse data (mode + aragon availability)."""
    store = get_settings_store()
    agent = store.current().agent
    cli = await detect_aragon(agent.aragon_cli_path)
    configured = bool(agent.api_key and agent.model)

    if cli.installed and configured:
        mode = "aragon"
    elif configured and agent.provider == "openai":
        mode = "llm_fallback"
    else:
        mode = "unavailable"

    if mode == "aragon":
        message = "AragonAgent 就绪：助手可直接读写设置文件"
    elif mode == "llm_fallback":
        message = "aragon CLI 未安装，将以纯 LLM 建议模式运行（建议安装 aragon 解锁自动配置）"
    elif not configured:
        message = "请先配置 Agent 大模型（提供方 / API Key / 模型）"
    else:
        message = "aragon 未安装且当前提供方不支持降级模式"

    return {
        "aragon_installed": cli.installed,
        "aragon_version": cli.version,
        "aragon_path": cli.path,
        "agent_configured": configured,
        "agent_enabled": agent.enabled,
        "mode": mode,
        "message": message,
    }
