"""Provider-boundary resolution integration: planning/patch/retry/committee phases."""
from __future__ import annotations

import json
from unittest import mock
import os

from nexus.services.local_heal.local_model_provider import (
    LocalModelProviderRequest,
    OllamaLocalModelProvider,
    RecordingLocalModelProvider,
)


def _ollama_env():
    return {
        "NEXUS_LOCAL_MODEL_CALL_ALLOWED": "1",
        "NEXUS_LOCAL_MODEL_PROVIDER": "ollama",
        "NEXUS_LOCAL_MODEL_NAME": "qwen2.5-coder:7b",
    }


def _mock_ok_response(text: str = "patch ok"):
    mock_response = mock.MagicMock()
    mock_response.read.return_value = json.dumps({"response": text}).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    return mock_response


def _run_phase(phase: str) -> tuple[str, object]:
    with mock.patch.dict(os.environ, _ollama_env()):
        inner = OllamaLocalModelProvider()
        rec = RecordingLocalModelProvider(inner)
        req = LocalModelProviderRequest(
            task_id="t_phase",
            prompt=f"phase {phase} prompt",
            evidence_refs=(),
            model_name="qwen2.5-coder:7b",
            phase=phase,
            attempt_id="attempt-1",
            execution_profile="STANDARD",
        )
        with mock.patch("urllib.request.urlopen", return_value=_mock_ok_response()) as mock_urlopen:
            resp = rec.generate(req)
            payload = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
            return payload["model"], rec.ledger[0], resp


def test_planning_phase_uses_resolved_model() -> None:
    model, record, resp = _run_phase("planning")
    assert model == "qwen2.5-coder:7b-instruct"
    assert resp.model_name == "qwen2.5-coder:7b-instruct"
    assert record.resolved_model == "qwen2.5-coder:7b-instruct"
    assert record.requested_model == "qwen2.5-coder:7b"
    assert record.phase == "planning"


def test_patch_phase_uses_resolved_model() -> None:
    model, record, _ = _run_phase("patch")
    assert model == "qwen2.5-coder:7b-instruct"
    assert record.phase == "patch"


def test_retry_phase_uses_resolved_model() -> None:
    model, record, _ = _run_phase("retry")
    assert model == "qwen2.5-coder:7b-instruct"
    assert record.phase == "retry"


def test_committee_proposer_judge_use_resolved_model() -> None:
    for phase in ("proposer", "judge"):
        model, record, _ = _run_phase(phase)
        assert model == "qwen2.5-coder:7b-instruct"
        assert record.resolved_model == "qwen2.5-coder:7b-instruct"
        assert record.phase == phase


def test_404_leaves_error_ledger() -> None:
    with mock.patch.dict(os.environ, _ollama_env()):
        inner = OllamaLocalModelProvider()
        rec = RecordingLocalModelProvider(inner)
        req = LocalModelProviderRequest(
            task_id="t_404",
            prompt="hello",
            evidence_refs=(),
            model_name="qwen2.5-coder:7b",
            phase="patch",
            attempt_id="attempt-1",
            execution_profile="LITE",
        )
        import urllib.error

        err = urllib.error.HTTPError(
            url="http://127.0.0.1:11434/api/generate",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with mock.patch("urllib.request.urlopen", side_effect=err):
            resp = rec.generate(req)
        assert resp.model_called is False
        assert "ollama_http_error_404" in resp.error
        assert resp.model_name == "qwen2.5-coder:7b-instruct"
        record = rec.ledger[0]
        assert record.status == "error"
        assert "ollama_http_error_404" in record.error
        assert record.requested_model == "qwen2.5-coder:7b"
        assert record.resolved_model == "qwen2.5-coder:7b-instruct"
        assert record.model_alias_applied is True
