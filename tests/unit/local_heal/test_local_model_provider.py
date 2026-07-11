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


def test_recording_provider_records_success() -> None:
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider, RecordingLocalModelProvider, LocalModelProviderRequest

    base = InjectedLocalModelProvider(lambda req: "patch content")
    rec = RecordingLocalModelProvider(base)

    req = LocalModelProviderRequest(
        task_id="t_success", prompt="hello", evidence_refs=(),
        phase="patch", attempt_id="attempt-1", execution_profile="LITE"
    )
    resp = rec.generate(req)
    assert resp.output_text == "patch content"

    summary = rec.ledger_summary
    assert summary["total_calls"] == 1
    assert summary["by_phase"]["patch"] == 1
    assert summary["phase_complete"] is True
    assert summary["unknown_call_count"] == 0

    record = rec.ledger[0]
    assert record.status == "ok"
    assert record.attempt_id == "attempt-1"
    assert record.execution_profile == "LITE"
    assert record.phase == "patch"


def test_recording_provider_records_raised_exception() -> None:
    from nexus.services.local_heal.local_model_provider import RecordingLocalModelProvider, LocalModelProviderRequest
    import pytest
    from unittest import mock

    base = mock.MagicMock()
    base.generate.side_effect = ValueError("simulated provider crash")

    rec = RecordingLocalModelProvider(base)

    req = LocalModelProviderRequest(
        task_id="t_crash", prompt="hello", evidence_refs=(),
        phase="retry", attempt_id="attempt-2", execution_profile="STANDARD"
    )

    with pytest.raises(ValueError, match="simulated provider crash"):
        rec.generate(req)

    summary = rec.ledger_summary
    assert summary["total_calls"] == 1
    assert summary["by_phase"]["retry"] == 1
    assert summary["phase_complete"] is True

    record = rec.ledger[0]
    assert record.status == "error"
    assert "exception" in record.error
    assert "simulated provider crash" in record.error
    assert record.attempt_id == "attempt-2"
    assert record.execution_profile == "STANDARD"


def test_recording_provider_records_response_error() -> None:
    from nexus.services.local_heal.local_model_provider import RecordingLocalModelProvider, LocalModelProviderRequest

    class MockProvider:
        def generate(self, req):
            from nexus.services.local_heal.local_model_provider import LocalModelProviderResponse
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="mock_model",
                output_text="",
                error="some_error",
            )

    rec = RecordingLocalModelProvider(MockProvider())
    req = LocalModelProviderRequest(
        task_id="t_err", prompt="hello", evidence_refs=(),
        phase="patch", attempt_id="attempt-1", execution_profile="LITE"
    )
    resp = rec.generate(req)
    assert resp.error == "some_error"

    summary = rec.ledger_summary
    assert summary["total_calls"] == 1
    assert rec.ledger[0].status == "error"
    assert rec.ledger[0].error == "some_error"


def test_recording_provider_records_timeout() -> None:
    from nexus.services.local_heal.local_model_provider import RecordingLocalModelProvider, LocalModelProviderRequest

    class MockProvider:
        def generate(self, req):
            from nexus.services.local_heal.local_model_provider import LocalModelProviderResponse
            return LocalModelProviderResponse(
                provider_invoked=True,
                model_called=False,
                model_name="mock_model",
                output_text="",
                error="timed out",
                timed_out=True,
            )

    rec = RecordingLocalModelProvider(MockProvider())
    req = LocalModelProviderRequest(
        task_id="t_timeout", prompt="hello", evidence_refs=(),
        phase="patch", attempt_id="attempt-1", execution_profile="LITE"
    )
    resp = rec.generate(req)
    assert resp.timed_out is True

    summary = rec.ledger_summary
    assert summary["total_calls"] == 1
    assert rec.ledger[0].status == "timeout"


def test_ledger_summary_detects_missing_phase() -> None:
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider, RecordingLocalModelProvider, LocalModelProviderRequest

    base = InjectedLocalModelProvider(lambda req: "patch content")
    rec = RecordingLocalModelProvider(base)

    req = LocalModelProviderRequest(
        task_id="t_missing_phase", prompt="hello", evidence_refs=(),
        phase="", attempt_id="attempt-1", execution_profile="LITE"
    )
    rec.generate(req)

    summary = rec.ledger_summary
    assert summary["phase_complete"] is False
    assert summary["unknown_call_count"] == 1


def test_ledger_summary_detects_missing_attempt_id() -> None:
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider, RecordingLocalModelProvider, LocalModelProviderRequest

    base = InjectedLocalModelProvider(lambda req: "patch content")
    rec = RecordingLocalModelProvider(base)

    req = LocalModelProviderRequest(
        task_id="t_missing_attempt", prompt="hello", evidence_refs=(),
        phase="patch", attempt_id="", execution_profile="LITE"
    )
    rec.generate(req)

    summary = rec.ledger_summary
    assert summary["attempt_context_complete"] is False
    assert summary["missing_attempt_id_count"] == 1


def test_ledger_summary_detects_missing_execution_profile() -> None:
    from nexus.services.local_heal.local_model_provider import InjectedLocalModelProvider, RecordingLocalModelProvider, LocalModelProviderRequest

    base = InjectedLocalModelProvider(lambda req: "patch content")
    rec = RecordingLocalModelProvider(base)

    req = LocalModelProviderRequest(
        task_id="t_missing_profile", prompt="hello", evidence_refs=(),
        phase="patch", attempt_id="attempt-1", execution_profile=""
    )
    rec.generate(req)

    summary = rec.ledger_summary
    assert summary["profile_context_complete"] is False
    assert summary["missing_execution_profile_count"] == 1
