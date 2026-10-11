# -*- coding: utf-8 -*-
"""Regression tests for the reasoning-model usage payload bug.

qwen3.8-max (and other reasoning models) return nested dicts inside
``usage``; ChatResponse used to declare Dict[str, int] and FastAPI raised
ResponseValidationError -> HTTP 500 on /api/v1/llm/chat.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.models import ChatResponse  # noqa: E402

REASONING_USAGE = {
    "prompt_tokens": 1181,
    "completion_tokens": 4024,
    "total_tokens": 5205,
    "prompt_tokens_details": {"cached_tokens": 0, "text_tokens": 1181},
    "completion_tokens_details": {"reasoning_tokens": 1247, "text_tokens": 2777},
}


class TestChatResponseUsage:
    def test_accepts_nested_reasoning_usage(self):
        resp = ChatResponse.model_validate({
            "id": "chatcmpl-1",
            "created": 1791714326,
            "model": "qwen3.8-max",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "title: x"},
                "finish_reason": "stop",
            }],
            "usage": REASONING_USAGE,
        })
        assert resp.usage["prompt_tokens"] == 1181
        assert resp.usage["completion_tokens_details"]["reasoning_tokens"] == 1247

    def test_still_accepts_plain_int_usage(self):
        resp = ChatResponse.model_validate({
            "id": "chatcmpl-2",
            "created": 1,
            "model": "m",
            "choices": [],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2,
                      "total_tokens": 3},
        })
        assert resp.usage["total_tokens"] == 3

    def test_usage_optional(self):
        resp = ChatResponse.model_validate({
            "id": "chatcmpl-3", "created": 1, "model": "m", "choices": [],
        })
        assert resp.usage is None
