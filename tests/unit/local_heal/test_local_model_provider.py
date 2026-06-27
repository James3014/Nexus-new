from __future__ import annotations

import pytest

from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    InertLocalModelProvider,
    InjectedLocalModelProvider,
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
