from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _module():
    return importlib.import_module("nexus.services.open_swe_external_intelligence")


def test_nexus_adapter_is_thin_and_has_no_deepagents_or_langchain_imports():
    source = Path("nexus/services/open_swe_external_intelligence.py").read_text(encoding="utf-8")
    assert "import deepagents" not in source
    assert "from deepagents" not in source
    assert "import langchain" not in source
    assert "from langchain" not in source


def test_semantic_transport_maps_external_protocol_and_reconcile_is_separate(tmp_path, monkeypatch):
    module = _module()
    calls = []
    envelope = {"schema": "external_execution_envelope.v1", "binding": {"task": "t1"}}

    def runtime_call(executable, payload, *, provider_id, timeout):
        calls.append((executable, dict(payload), provider_id, timeout))
        return (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "google_genai",
                "model_id": "gemini-test",
                "raw": json.dumps(envelope),
                "process_started": payload["operation"] == "semantic_run",
                "outcome_unknown": False,
                "retry_safe": False,
                "started_at": "2026-09-01T00:00:00Z",
                "finished_at": "2026-09-01T00:00:01Z",
            },
            "",
            True,
            "",
        )

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
        executable="runtime-bin",
        runtime_state_root=tmp_path / "runtime-state",
    )

    first = transport.invoke("prompt")
    reconciled = transport.reconcile("prompt")

    assert first.status == "INTELLIGENCE_COMPLETED"
    assert json.loads(first.raw) == envelope
    assert reconciled.status == "INTELLIGENCE_COMPLETED"
    assert [call[1]["operation"] for call in calls] == ["semantic_run", "semantic_reconcile"]
    assert calls[0][1]["operation_id"] == calls[1][1]["operation_id"]
    assert first.safe_argv == ("runtime-bin", "<json-stdin>")


def test_semantic_timeout_is_unknown_and_never_retry_safe(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_runtime_call",
        lambda *_args, **_kwargs: (None, "", True, "runtime_timeout"),
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.retry_safe is False


def test_semantic_runtime_missing_before_start_is_retry_safe(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_runtime_call",
        lambda *_args, **_kwargs: (None, "", False, "runtime_not_found"),
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_RUNTIME_NOT_FOUND"
    assert result.outcome_unknown is False
    assert result.retry_safe is True


def test_semantic_model_attestation_mismatch_fails_closed(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(
        module,
        "_runtime_call",
        lambda *_args, **_kwargs: (
            {
                "schema": module.PROTOCOL_RESULT_SCHEMA,
                "kind": "semantic",
                "status": "INTELLIGENCE_COMPLETED",
                "provider_id": "other",
                "model_id": "wrong",
                "raw": "{}",
            },
            "",
            True,
            "",
        ),
    )
    transport = module.OpenSWEExternalIntelligenceTransport(
        repository_root=tmp_path,
        model_provider="google_genai",
        model_id="gemini-test",
    )

    result = transport.invoke("prompt")

    assert result.status == "OPEN_SWE_MODEL_ATTESTATION_MISMATCH"
    assert result.outcome_unknown is True


def test_runtime_environment_passes_selected_provider_key_but_not_github_credentials(monkeypatch):
    module = _module()
    monkeypatch.setenv("GEMINI_API_KEY", "provider-sentinel")
    monkeypatch.setenv("GITHUB_TOKEN", "github-sentinel")
    monkeypatch.setenv("GH_TOKEN", "gh-sentinel")
    monkeypatch.setenv("UNRELATED_SECRET", "unrelated-sentinel")

    env = module._runtime_env("google_genai")

    assert "GEMINI_API_KEY" in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "UNRELATED_SECRET" not in env


def test_empty_external_runtime_executable_is_rejected(tmp_path):
    module = _module()
    with pytest.raises(module.OpenSWEExternalIntelligenceError, match="OPEN_SWE_EXECUTABLE_REQUIRED"):
        module.OpenSWEExternalIntelligenceTransport(
            repository_root=tmp_path,
            model_provider="google_genai",
            model_id="gemini-test",
            executable="",
        )
