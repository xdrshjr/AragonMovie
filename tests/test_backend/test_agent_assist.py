"""Tests for the AragonAgent integration layer (agent_assist)."""
import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core import agent_assist  # noqa: E402
from backend.core.settings_store import get_settings_store  # noqa: E402


# ======================================================================
# NDJSON event normalization
# ======================================================================

class TestNormalizeEvents:
    def test_init_event(self):
        ev = agent_assist.normalize_exec_event({
            "type": "system", "subtype": "init", "sessionId": "s1",
            "model": {"provider": "openai", "id": "gpt-4o", "baseUrl": None},
            "tools": ["read_file"],
        })
        assert ev["type"] == "system"
        assert ev["model"]["id"] == "gpt-4o"

    def test_text_delta(self):
        ev = agent_assist.normalize_exec_event({"type": "text_delta", "delta": "你好"})
        assert ev == {"type": "text_delta", "text": "你好"}

    def test_tool_call(self):
        ev = agent_assist.normalize_exec_event({
            "type": "tool_call", "id": "t1", "name": "edit_file",
            "input": {"path": "x.json"},
        })
        assert ev["name"] == "edit_file"
        assert ev["input"] == {"path": "x.json"}

    def test_tool_result_preview_is_string(self):
        ev = agent_assist.normalize_exec_event({
            "type": "tool_result", "id": "t1", "content": {"nested": "x" * 500},
        })
        assert isinstance(ev["preview"], str)
        assert len(ev["preview"]) <= 200

    def test_result_event(self):
        ev = agent_assist.normalize_exec_event({
            "type": "result", "stopReason": "end_turn",
            "usage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3},
            "cost": {"amount": 0.01, "currency": "USD", "known": True},
            "sessionId": "s1",
        })
        assert ev["stop_reason"] == "end_turn"
        assert ev["usage"]["totalTokens"] == 3

    def test_unknown_event_skipped(self):
        assert agent_assist.normalize_exec_event({"type": "turn_state"}) is None
        assert agent_assist.normalize_exec_event({"type": "todo"}) is None


# ======================================================================
# JSON patch extraction (fallback mode)
# ======================================================================

class TestExtractJsonPatch:
    def test_extracts_fenced_block(self):
        text = "建议如下：\n```json\n{\"video\": {\"service_type\": \"sora2\"}}\n```\n完成"
        patch = agent_assist.extract_json_patch(text)
        assert patch == {"video": {"service_type": "sora2"}}

    def test_no_block_returns_none(self):
        assert agent_assist.extract_json_patch("no json here") is None

    def test_invalid_json_returns_none(self):
        assert agent_assist.extract_json_patch("```json\n{broken\n```") is None


# ======================================================================
# CLI resolution
# ======================================================================

class TestCommandResolution:
    def test_js_path_uses_node(self, tmp_path, monkeypatch):
        fake_node = tmp_path / "node.exe"
        fake_node.write_bytes(b"")
        launcher = tmp_path / "launcher.js"
        launcher.write_bytes(b"")
        monkeypatch.setattr(agent_assist.shutil, "which", lambda name: str(fake_node))
        cmd = agent_assist._command_for_path(str(launcher), str(fake_node))
        assert cmd == [str(fake_node), str(launcher)]

    def test_cmd_shim_resolves_sibling_launcher(self, tmp_path, monkeypatch):
        fake_node = tmp_path / "node.exe"
        fake_node.write_bytes(b"")
        shim = tmp_path / "aragon.cmd"
        shim.write_bytes(b"")
        launcher = (
            tmp_path / "node_modules" / "@aragon-agent" / "cli" / "dist" / "launcher.js"
        )
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes(b"")
        cmd = agent_assist._command_for_path(str(shim), str(fake_node))
        assert cmd == [str(fake_node), str(launcher)]

    def test_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(agent_assist.shutil, "which", lambda name: None)
        assert agent_assist._resolve_aragon_command("aragon") is None


# ======================================================================
# env mapping
# ======================================================================

class TestAgentEnv:
    def _agent(self, **kw):
        base = {
            "enabled": True, "provider": "openai", "api_key": "sk-k",
            "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat",
            "max_turns": 5, "timeout_seconds": 60, "aragon_cli_path": "aragon",
        }
        base.update(kw)
        from backend.core.settings_models import AgentSettings
        return AgentSettings.model_validate(base)

    def test_openai_mapping(self):
        env = agent_assist._agent_env(self._agent())
        assert env["ARAGON_PROVIDER"] == "openai"
        assert env["ARAGON_MODEL"] == "deepseek-chat"
        assert env["ARAGON_BASE_URL"] == "https://api.deepseek.com/v1"
        assert env["OPENAI_API_KEY"] == "sk-k"

    def test_anthropic_mapping(self):
        env = agent_assist._agent_env(self._agent(provider="anthropic", base_url=None))
        assert env["ANTHROPIC_API_KEY"] == "sk-k"
        assert "ARAGON_BASE_URL" not in env

    def test_stale_provider_keys_removed(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "old")
        monkeypatch.setenv("GOOGLE_API_KEY", "old")
        env = agent_assist._agent_env(self._agent())
        assert "ANTHROPIC_API_KEY" not in env
        assert "GOOGLE_API_KEY" not in env


# ======================================================================
# fallback stream
# ======================================================================

class TestFallbackStream:
    def _configure_agent(self, tmp_path, monkeypatch, reply_text):
        store = get_settings_store()
        monkeypatch.setattr(store, "file_path", tmp_path / "s.json")
        monkeypatch.setattr(store, "_current", None)
        monkeypatch.setattr(store, "_file_hash", None)

        from backend.core.settings_models import ModelSettings
        agent = ModelSettings.model_validate({
            "agent": {
                "enabled": True, "provider": "openai",
                "api_key": "sk-test", "model": "gpt-test",
            }
        }).agent
        monkeypatch.setattr(store, "current", lambda: ModelSettings.model_validate(
            {"agent": agent.model_dump()}))

        # pretend aragon is NOT installed -> fallback mode
        info = agent_assist.AragonCliInfo(False, note="not installed")
        async def fake_detect(cli_path=None, force=False):
            return info
        monkeypatch.setattr(agent_assist, "detect_aragon", fake_detect)

        class FakeLLM:
            def __init__(self, *a, **k):
                pass
            async def chat_completion(self, messages, temperature=0.7, max_tokens=None):
                return {"choices": [{"message": {"content": reply_text}}]}
            async def close(self):
                pass
        monkeypatch.setattr("services.llm_service.LLMService", FakeLLM)

    def test_fallback_yields_advice_and_patch(self, tmp_path, monkeypatch):
        reply = "把视频切到 sora2:\n```json\n{\"video\": {\"service_type\": \"sora2\"}}\n```"
        self._configure_agent(tmp_path, monkeypatch, reply)

        events = []
        async def collect():
            async for ev in agent_assist.agent_chat_stream("帮我切换视频服务"):
                events.append(ev)
        asyncio.run(collect())

        types = [e["type"] for e in events]
        assert "text_delta" in types
        assert "assistant" in types
        result = next(e for e in events if e["type"] == "result")
        assert result["suggested_patch"] == {"video": {"service_type": "sora2"}}
        assert result["mode"] == "llm_fallback"

    def test_unconfigured_agent_raises(self, tmp_path, monkeypatch):
        store = get_settings_store()
        monkeypatch.setattr(store, "file_path", tmp_path / "s.json")
        monkeypatch.setattr(store, "_current", None)
        monkeypatch.setattr(store, "_file_hash", None)
        store.load()

        with pytest.raises(agent_assist.AgentAssistError):
            async def run():
                async for _ in agent_assist.agent_chat_stream("hi"):
                    pass
            asyncio.run(run())
