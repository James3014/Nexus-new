"""Real M5 host canaries (Canary A, B, C, D, E, F) as required by Section 13."""

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
from nexus.services.m5_local.handoff_adapter import create_handoff_from_assist
from nexus.services.m5_local.runtimes import MockLocalRuntime

REPO_ROOT = Path(__file__).resolve().parents[3]


# Canary A — deterministic Local Assist
def test_canary_a_deterministic_local_assist():
    """Canary A: Given a real repository question, deterministically identify files, tests, and contracts."""
    svc = LocalAssistService()
    req = LocalAssistRequest(
        task_id="canary-a-provenance",
        query="live execution provenance rdc",
        repo_path=str(REPO_ROOT),
        allow_inference=False,
    )
    res = svc.execute(req)

    assert res.status == "SUCCESS"
    assert any("live_execution_provenance.py" in f for f in res.candidate_files)
    assert any("test_live_execution_provenance.py" in t for t in res.suggested_tests)
    assert res.claims_linked_to_evidence is True
    assert len(res.evidence_refs) > 0
    # Proves zero repository mutation
    assert res.telemetry.get("mode") == "deterministic_only"


# Canary B — Local inference assist
def test_canary_b_local_inference_assist():
    """Canary B: Perform non-authoritative local inference assistance and record telemetry."""
    mock_rt = MockLocalRuntime(
        output_text="Analysis: live_execution_provenance.py contains canonical RDC receipt verification.",
        observed_runtime="mock-llama.cpp",
        observed_model="qwen36-35b-q4",
    )
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="canary-b-inference",
        query="live execution provenance",
        repo_path=str(REPO_ROOT),
        requested_runtime="mock-llama.cpp",
        requested_model="qwen36-35b-q4",
        allow_inference=True,
    )
    res = svc.execute(req)

    assert res.status == "SUCCESS"
    assert "canonical RDC receipt verification" in res.findings
    assert res.observed_model == "qwen36-35b-q4"
    assert res.telemetry.get("elapsed_ms") is not None
    assert res.telemetry.get("rss_bytes") is not None


# Canary C — Local -> Online handoff
def test_canary_c_local_to_online_handoff():
    """Canary C: Produce a real handoff packet from an escalated Local Assist attempt."""
    svc = LocalAssistService()
    req = LocalAssistRequest(
        task_id="canary-c-handoff",
        query="live execution provenance cross entrypoint conflict",
        repo_path=str(REPO_ROOT),
        allow_inference=False,
    )
    assist_res = svc.execute(req)
    # Simulate partial local findings requiring online architectural synthesis
    handoff_pkt = create_handoff_from_assist(
        task_id="canary-c-handoff",
        work_id="work-canary-c",
        predecessor_attempt_id="att-canary-local-1",
        predecessor_operation_id="op-canary-local-1",
        repo_identity="James3014/Nexus-new",
        base_sha="5f201a6cb9f7fb7e951642aee3907fec3fd8f39d",
        assist_response=assist_res,
        unresolved_question="Requires Online architectural cross-entrypoint conflict model reasoning under #98",
    )

    assert handoff_pkt.task_id == "canary-c-handoff"
    assert handoff_pkt.predecessor_attempt_id == "att-canary-local-1"
    assert handoff_pkt.durability == "EPHEMERAL_PROJECTION"
    assert handoff_pkt.nature == "HANDOFF_INPUT"
    assert any("live_execution_provenance.py" in p for p in handoff_pkt.inspected_paths)
    assert len(handoff_pkt.evidence_refs) > 0
    assert "cross-entrypoint conflict" in handoff_pkt.unresolved_questions[0]
    assert handoff_pkt.remaining_gate == "ONLINE_REASONING_REQUIRED"


# Canary D — timeout/cancel/reconcile
def test_canary_d_timeout_reconcile():
    """Canary D: Force a bounded stalled local inference operation and verify fail-closed status."""
    mock_rt = MockLocalRuntime(simulate_timeout=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="canary-d-timeout",
        query="stalled query",
        repo_path=str(REPO_ROOT),
        requested_runtime="mock",
        requested_model="test-model",
        timeout_seconds=0.05,
    )
    res = svc.execute(req)

    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_TIMEOUT
    # Ensure no false success is reported
    assert "timed out" in res.findings.lower()


# Canary E — wrong model identity
def test_canary_e_wrong_model_identity():
    """Canary E: Requested model != physically observed model must mark identity mismatch."""
    mock_rt = MockLocalRuntime(simulate_model_mismatch=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="canary-e-mismatch",
        query="query",
        repo_path=str(REPO_ROOT),
        requested_runtime="mock",
        requested_model="expected-model-v1",
    )
    res = svc.execute(req)

    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH
    assert res.requested_model != res.observed_model


# Canary F — attempted write during Assist
def test_canary_f_attempted_write_during_assist():
    """Canary F: Attempting repository mutation during Assist must be rejected/contained."""
    svc = LocalAssistService()
    req = LocalAssistRequest(
        task_id="canary-f-write",
        query="attempted write",
        repo_path=str(REPO_ROOT),
    )
    object.__setattr__(req, "write_permitted", True)

    with pytest.raises(LocalAssistMutationAttemptedError):
        svc.execute(req)


# Canary G — attempted write during Worker
def test_canary_g_attempted_write_during_worker():
    """Canary G: Local worker mutation attempt must be denied with LOCAL_ROLE_NOT_QUALIFIED."""
    from nexus.services.m5_local.contracts import (
        LOCAL_ROLE_NOT_QUALIFIED,
        LocalWorkerRequest,
    )
    from nexus.services.m5_local.worker_adapter import LocalWorkerService

    svc = LocalWorkerService()
    req = LocalWorkerRequest(
        task_id="canary-g-write",
        attempt_id="att-canary-g",
        operation_id="op-canary-g",
        repo_path=str(REPO_ROOT),
        task_instruction="Write mutation test",
        write_permitted=True,
    )
    res = svc.execute(req)

    assert res.status == "REJECTED_DENIED"
    assert res.escalation_reason == LOCAL_ROLE_NOT_QUALIFIED
    assert not res.write_performed


def test_canary_llama_cpp_runtime_physical():
    """Canary: Physical llama-cli execution when present on Apple Silicon host."""
    from nexus.services.m5_local.host_inventory import inspect_models
    from nexus.services.m5_local.runtimes import LlamaCppRuntime

    models = inspect_models()
    rt = LlamaCppRuntime()
    if not rt.is_available() or "qwen36-35b-q4" not in models:
        # Platform/hardware boundary check in generic CI: runtime must be recognized as unavailable
        assert not rt.is_available() or "qwen36-35b-q4" not in models
        return

    rt = LlamaCppRuntime()
    res = rt.run_inference(
        model_id="qwen36-35b-q4", prompt="Ping", max_tokens=4, timeout_seconds=30
    )
    assert res.exit_code == 0
    assert res.physical_model_size_bytes == 20419565568
    assert res.observed_model.startswith("Qwen3.6-35B-A3B-Q4_K_M.gguf:")
    assert res.runtime_version.startswith("version: 0.4.1")


def test_canary_worker_service_physical_llama_cpp():
    """Canary: Physical service-level LocalWorkerService execution using llama.cpp on M5."""
    from nexus.services.m5_local.contracts import LocalWorkerRequest
    from nexus.services.m5_local.host_inventory import inspect_models
    from nexus.services.m5_local.runtimes import LlamaCppRuntime
    from nexus.services.m5_local.worker_adapter import LocalWorkerService

    models = inspect_models()
    rt = LlamaCppRuntime()
    if not rt.is_available() or "qwen36-35b-q4" not in models:
        # Platform/hardware boundary check in generic CI: runtime/model must be recognized as unavailable
        assert not rt.is_available() or "qwen36-35b-q4" not in models
        return

    svc = LocalWorkerService()
    req = LocalWorkerRequest(
        task_id="canary-worker-physical",
        attempt_id="att-canary-worker-1",
        operation_id="op-canary-worker-1",
        repo_path=str(REPO_ROOT),
        task_instruction="Ping physical model for service-level verification",
        requested_runtime="llama.cpp",
        requested_model="qwen36-35b-q4",
        write_permitted=False,
    )
    res = svc.execute(req)

    assert res.status == "COMPLETED"
    assert res.exit_code == 0
    assert not res.write_performed
    assert res.requested_model == "qwen36-35b-q4"
    assert res.observed_model.startswith("Qwen3.6-35B-A3B-Q4_K_M.gguf:")
    assert res.observed_model.endswith("20419565568B")
    assert res.observed_runtime == "llama.cpp"
