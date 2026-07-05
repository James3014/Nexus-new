from __future__ import annotations

import os
from unittest import mock
import urllib.error

import pytest

from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    InertLocalModelProvider,
    InjectedLocalModelProvider,
    OllamaLocalModelProvider,
)


def test_inert_local_model_provider() -> None:
    provider = InertLocalModelProvider()
    req = LocalModelProviderRequest(task_id="t1", prompt="hello", evidence_refs=())
    resp = provider.generate(req)
    assert resp.provider_invoked is True
    assert resp.model_called is False
    assert resp.error == "provider_not_configured"
    assert resp.public_claim_allowed is False
    assert resp.production_ready is False


def test_injected_local_model_provider_success() -> None:
    def fake_generate(request: LocalModelProviderRequest) -> str:
        return "response: " + request.prompt
        
    provider = InjectedLocalModelProvider(fake_generate)
    req = LocalModelProviderRequest(task_id="t2", prompt="test prompt", evidence_refs=(), model_name="qwen")
    resp = provider.generate(req)
    assert resp.provider_invoked is True
    assert resp.model_called is True
    assert resp.output_text == "response: test prompt"
    assert resp.output_truncated is False
    assert resp.model_name == "qwen"


def test_injected_local_model_provider_truncation() -> None:
    def fake_generate(request: LocalModelProviderRequest) -> str:
        return "A" * 10
        
    provider = InjectedLocalModelProvider(fake_generate)
    req = LocalModelProviderRequest(task_id="t3", prompt="test", evidence_refs=(), max_output_chars=5)
    resp = provider.generate(req)
    assert resp.output_text == "AAAAA"
    assert resp.output_truncated is True


def test_injected_local_model_provider_exception() -> None:
    def fake_generate(request: LocalModelProviderRequest) -> str:
        raise ValueError("simulated crash")
        
    provider = InjectedLocalModelProvider(fake_generate)
    req = LocalModelProviderRequest(task_id="t4", prompt="test", evidence_refs=())
    
    resp = provider.generate(req)
    assert resp.provider_invoked is True
    assert resp.model_called is False
    assert "simulated crash" in resp.error


def test_ollama_local_model_provider_not_configured() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        provider = OllamaLocalModelProvider()
        req = LocalModelProviderRequest(task_id="t5", prompt="test", evidence_refs=())
        resp = provider.generate(req)
        assert resp.model_called is False
        assert resp.error == "provider_not_configured"


def test_ollama_local_model_provider_missing_model_name() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "",
    }):
        provider = OllamaLocalModelProvider()
        req = LocalModelProviderRequest(task_id="t6", prompt="test", evidence_refs=())
        resp = provider.generate(req)
        assert resp.model_called is False
        assert resp.error == "model_name_missing"


def test_ollama_local_model_provider_success() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder:7b",
    }):
        provider = OllamaLocalModelProvider()
        req = LocalModelProviderRequest(task_id="t7", prompt="test code", evidence_refs=())
        
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "suggested patch code"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response):
            resp = provider.generate(req)
            assert resp.provider_invoked is True
            assert resp.model_called is True
            assert resp.model_name == "qwen2.5-coder:7b"
            assert resp.output_text == "suggested patch code"


def test_ollama_provider_passes_options_to_api() -> None:
    with mock.patch.dict(os.environ, {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder:7b",
    }):
        provider = OllamaLocalModelProvider()
        opts = {"num_ctx": 4096, "num_predict": 128, "temperature": 0.0}
        req = LocalModelProviderRequest(
            task_id="t8",
            prompt="test code",
            evidence_refs=(),
            options=opts,
        )
        
        mock_response = mock.MagicMock()
        mock_response.read.return_value = b'{"response": "suggested patch code"}'
        mock_response.__enter__.return_value = mock_response
        
        with mock.patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            resp = provider.generate(req)
            assert resp.provider_invoked is True
            assert resp.model_called is True
            
            mock_urlopen.assert_called_once()
            call_args = mock_urlopen.call_args[0]
            req_obj = call_args[0]
            
            import json
            payload = json.loads(req_obj.data.decode("utf-8"))
            assert "options" in payload
            assert payload["options"] == opts

