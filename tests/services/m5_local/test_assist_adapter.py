"""Unit tests for Mode A — Local Assist service."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services.m5_local.assist_adapter import LocalAssistService
from nexus.services.m5_local.contracts import (
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_TIMEOUT,
    LocalAssistMutationAttemptedError,
    LocalAssistRequest,
)
from nexus.services.m5_local.runtimes import MockLocalRuntime


def test_deterministic_assist_without_inference(tmp_path: Path):
    f = tmp_path / "nexus" / "worker.py"
    f.parent.mkdir(parents=True)
    f.write_text("class Worker:\n    pass\n", encoding="utf-8")

    svc = LocalAssistService()
    req = LocalAssistRequest(
        task_id="t1",
        query="worker",
        repo_path=str(tmp_path),
        allow_inference=False,
    )
    res = svc.execute(req)
    assert res.status == "SUCCESS"
    assert any("worker.py" in c for c in res.candidate_files)
    assert res.claims_linked_to_evidence is True
    assert res.escalation_reason is None


def test_assist_mutation_attempt_raises_error(tmp_path: Path):
    svc = LocalAssistService()
    # Attempting to supply write_permitted should raise LocalAssistMutationAttemptedError
    req = LocalAssistRequest(
        task_id="t2",
        query="worker",
        repo_path=str(tmp_path),
    )
    # Monkeypatch write_permitted to simulate illegal mutation request
    object.__setattr__(req, "write_permitted", True)
    with pytest.raises(LocalAssistMutationAttemptedError):
        svc.execute(req)


def test_assist_with_mock_inference(tmp_path: Path):
    f = tmp_path / "nexus" / "logic.py"
    f.parent.mkdir(parents=True)
    f.write_text("def run(): pass\n", encoding="utf-8")

    mock_rt = MockLocalRuntime(
        output_text="Analysis: logic.py contains core execution logic.",
        observed_model="test-model",
    )
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t3",
        query="logic",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
        allow_inference=True,
    )
    res = svc.execute(req)
    assert res.status == "SUCCESS"
    assert "Analysis: logic.py" in res.findings
    assert res.observed_model == "test-model"


def test_assist_timeout_escalates_cleanly(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_timeout=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t4",
        query="query",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
        timeout_seconds=0.1,
    )
    res = svc.execute(req)
    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_TIMEOUT


def test_assist_model_mismatch_escalates(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_model_mismatch=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t5",
        query="query",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="expected-model",
    )
    res = svc.execute(req)
    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH
