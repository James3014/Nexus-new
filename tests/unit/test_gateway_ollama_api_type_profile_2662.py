"""#2662: the Ollama chat/generate choice follows ModelProfile.get_api_type.

Found by the #2651 live witness (#2638 issuecomment-6256790914): the gateway
called ``LocalModelPolicy.get_api_type``, which does not exist, so every call
logged a lookup failure and fell back to /api/generate even when the model
profile asked for chat.
"""

from __future__ import annotations

import io
import json
import logging
import urllib.request

import pytest

from nexus.engine.local_model_policy import ModelProfile
from nexus.services.gateway import BattlesuitGateway

GATEWAY_LOGGER = "nexus.services.gateway"
CHAT_MODEL = "qwythos-coder:9b"  # ModelProfile.get_api_type -> "chat"
GENERATE_MODEL = "qwen2.5-coder:7b"  # ModelProfile.get_api_type -> "generate"


def _gateway() -> BattlesuitGateway:
    return object.__new__(BattlesuitGateway)


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv("NEXUS_OLLAMA_API_TYPE", raising=False)


def test_profile_fixture_models_have_expected_api_types():
    assert ModelProfile.get_api_type(CHAT_MODEL) == "chat"
    assert ModelProfile.get_api_type(GENERATE_MODEL) == "generate"


def test_chat_profile_model_selects_chat_without_lookup_warning(caplog):
    with caplog.at_level(logging.WARNING, logger=GATEWAY_LOGGER):
        assert _gateway()._ollama_api_type(CHAT_MODEL) == "chat"
        assert _gateway()._ollama_api_type(GENERATE_MODEL) == "generate"
    assert not [r for r in caplog.records if "API type lookup failed" in r.getMessage()]


def test_env_override_still_wins_over_profile(monkeypatch):
    monkeypatch.setenv("NEXUS_OLLAMA_API_TYPE", "generate")
    assert _gateway()._ollama_api_type(CHAT_MODEL) == "generate"


def test_profile_lookup_failure_still_logged_and_falls_back(monkeypatch, caplog):
    def _boom(_model):
        raise RuntimeError("profile exploded")

    monkeypatch.setattr(ModelProfile, "get_api_type", classmethod(lambda cls, m: _boom(m)))
    with caplog.at_level(logging.WARNING, logger=GATEWAY_LOGGER):
        assert _gateway()._ollama_api_type(CHAT_MODEL) == "generate"
    assert any("profile exploded" in r.getMessage() for r in caplog.records)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.mark.parametrize(
    ("model", "path", "body"),
    [
        (CHAT_MODEL, "/api/chat", {"message": {"role": "assistant", "content": "{}"}}),
        (GENERATE_MODEL, "/api/generate", {"response": "{}"}),
    ],
    ids=["chat-profile", "generate-profile"],
)
def test_ask_via_ollama_uses_profile_endpoint(monkeypatch, model, path, body):
    captured: list[urllib.request.Request] = []

    def _fake_urlopen(req, timeout=None):
        captured.append(req)
        return _Resp(json.dumps({**body, "prompt_eval_count": 3, "eval_count": 2}).encode())

    monkeypatch.setenv("NEXUS_OLLAMA_ENDPOINT", "http://127.0.0.1:1")
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    telemetry: dict = {}
    _gateway()._ask_via_ollama(
        content="say hi",
        model_name=model,
        sys_msg="sys",
        timeout_sec=5,
        gateway_telemetry=telemetry,
    )
    assert len(captured) == 1
    assert captured[0].full_url == f"http://127.0.0.1:1{path}"
    payload = json.loads(captured[0].data)
    if path == "/api/chat":
        assert payload["messages"][-1] == {"role": "user", "content": "say hi"}
        assert "prompt" not in payload
    else:
        assert payload["prompt"] == "say hi"
        assert "messages" not in payload
    assert telemetry["ollama_api_type"] == path.rsplit("/", 1)[-1]
