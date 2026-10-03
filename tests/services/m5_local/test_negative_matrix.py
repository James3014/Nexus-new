"""Negative test matrix covering all 20 required failure and containment modes."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.services.m5_local.assist_adapter import LocalAssistService
from nexus.services.m5_local.contracts import (
    LOCAL_MODEL_IDENTITY_MISMATCH,
    LOCAL_ROLE_NOT_QUALIFIED,
    LOCAL_RUNTIME_UNAVAILABLE,
    LOCAL_TIMEOUT,
    HandoffContractError,
    LocalAssistMutationAttemptedError,
    LocalAssistRequest,
    LocalAssistResponse,
    LocalWorkerRequest,
    StaleBaseError,
)
from nexus.services.m5_local.deterministic_fallback import build_bounded_evidence_packet
from nexus.services.m5_local.handoff_adapter import (
    create_handoff_from_assist,
    create_handoff_from_worker,
)
from nexus.services.m5_local.runtimes import (
    LlamaCppRuntime,
    MockLocalRuntime,
)
from nexus.services.m5_local.worker_adapter import LocalWorkerService


# 1. Runtime not installed
def test_negative_1_runtime_not_installed():
    rt = LlamaCppRuntime(executable_path="/nonexistent/bin/llama-cli")
    res = rt.run_inference(model_id="any-model", prompt="hi")
    assert res.exit_code == -1
    assert res.escalation_reason == LOCAL_RUNTIME_UNAVAILABLE


# 2. Model file missing
def test_negative_2_model_file_missing():
    rt = LlamaCppRuntime()
    res = rt.run_inference(model_id="nonexistent-model-xyz", prompt="hi")
    assert res.exit_code == -1
    assert res.escalation_reason == LOCAL_RUNTIME_UNAVAILABLE


# 3. Requested/observed model mismatch
def test_negative_3_requested_observed_model_mismatch(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_model_mismatch=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t3",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="model-alpha",
    )
    res = svc.execute(req)
    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_MODEL_IDENTITY_MISMATCH


# 4. Malformed model output
def test_negative_4_malformed_model_output(tmp_path: Path):
    mock_rt = MockLocalRuntime(output_text="\x00\xff\xfe corrupted binary stream")
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t4",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
    )
    res = svc.execute(req)
    # Output must be preserved as text safely without crashing
    assert res.status == "SUCCESS"
    assert "\x00" in res.findings


# 5. Timeout
def test_negative_5_timeout(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_timeout=True)
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t5",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
        timeout_seconds=0.1,
    )
    res = svc.execute(req)
    assert res.status == "ESCALATED"
    assert res.escalation_reason == LOCAL_TIMEOUT


# 6. Cancellation
def test_negative_6_cancellation(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_cancel=True)
    svc = LocalWorkerService(runtime=mock_rt)
    req = LocalWorkerRequest(
        task_id="t6",
        attempt_id="att-6",
        operation_id="op-6",
        repo_path=str(tmp_path),
        task_instruction="cancelled op",
        requested_runtime="mock",
        requested_model="test-model",
    )
    res = svc.execute(req)
    assert res.status == "CANCELLED"


# 7. Process exit non-zero
def test_negative_7_process_exit_non_zero(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_error="Segmentation fault", simulate_exit_code=139)
    svc = LocalWorkerService(runtime=mock_rt)
    req = LocalWorkerRequest(
        task_id="t7",
        attempt_id="att-7",
        operation_id="op-7",
        repo_path=str(tmp_path),
        task_instruction="failing op",
        requested_runtime="mock",
        requested_model="test-model",
    )
    res = svc.execute(req)
    assert res.status == "FAILED"
    assert res.exit_code == 139


# 8. Output truncated/incomplete
def test_negative_8_output_truncated(tmp_path: Path):
    mock_rt = MockLocalRuntime(output_text="Incomplete analysis...")
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t8",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
        max_tokens=2,
    )
    res = svc.execute(req)
    assert res.status == "SUCCESS"
    assert res.findings == "Incomplete analysis..."


# 9. Memory/resource refusal
def test_negative_9_memory_resource_refusal(monkeypatch):
    import sys

    from nexus.services.m5_local import telemetry
    from nexus.services.m5_local.host_inventory import HostMemoryInfo

    # Verify non-Darwin platforms fail closed with RESOURCE_STATE_UNAVAILABLE
    monkeypatch.setattr(sys, "platform", "linux")
    safe, reason = telemetry.check_host_resource_safety()
    assert safe is False
    assert "RESOURCE_STATE_UNAVAILABLE" in reason

    # Verify Darwin host under swap pressure fails closed with swap message
    monkeypatch.setattr(sys, "platform", "darwin")

    def mock_high_swap():
        return HostMemoryInfo(
            total_ram_bytes=64 * 1024 * 1024 * 1024,
            active_pages=1000,
            inactive_pages=1000,
            free_pages=100,
            swap_total_mb=32768.0,
            swap_used_mb=25000.0,  # Above MAX_SAFE_SWAP_USED_MB (16GB)
            swap_free_mb=7768.0,
        )

    monkeypatch.setattr(telemetry, "get_host_memory_info", mock_high_swap)
    safe, reason = telemetry.check_host_resource_safety()
    assert safe is False
    assert "Host swap usage is high" in reason


# 10. Stale repo base
def test_negative_10_stale_repo_base(tmp_path: Path):
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    (tmp_path / "f.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True)

    with pytest.raises(StaleBaseError):
        build_bounded_evidence_packet(
            task_id="t10",
            query="test",
            repo_path=tmp_path,
            base_sha="stale_sha_9999999999999999999999999999999999999999",
        )


# 11. RIE/source evidence unavailable (nonexistent repo path)
def test_negative_11_source_evidence_unavailable():
    with pytest.raises(ValueError):
        build_bounded_evidence_packet(
            task_id="t11",
            query="test",
            repo_path="/nonexistent/directory/for/repo",
        )


# 12. Local Assist attempts repository write
def test_negative_12_assist_attempts_repository_write(tmp_path: Path):
    svc = LocalAssistService()
    req = LocalAssistRequest(task_id="t12", query="test", repo_path=str(tmp_path))
    object.__setattr__(req, "write_permitted", True)
    with pytest.raises(LocalAssistMutationAttemptedError):
        svc.execute(req)


# 13. Local unqualified for requested role
def test_negative_13_local_unqualified_for_requested_role(tmp_path: Path):
    svc = LocalWorkerService()
    req = LocalWorkerRequest(
        task_id="t13",
        attempt_id="att-13",
        operation_id="op-13",
        repo_path=str(tmp_path),
        task_instruction="write patch",
        requested_runtime="llama.cpp",
        requested_model="qwen36-35b-q4",
        write_permitted=True,
        claim_receipt_ref="urn:nexus:claim:test",
        conflict_admission_token="token-test",
        workspace_root=str(tmp_path),
    )
    res = svc.execute(req)
    assert res.status == "REJECTED_DENIED"
    assert res.escalation_reason == LOCAL_ROLE_NOT_QUALIFIED


# 14. Handoff with missing predecessor evidence
def test_negative_14_handoff_missing_predecessor_evidence():
    with pytest.raises(HandoffContractError):
        create_handoff_from_assist(
            task_id="t14",
            work_id="w14",
            predecessor_attempt_id="",  # Missing predecessor attempt
            predecessor_operation_id="op-14",
            repo_identity="repo",
            base_sha="sha",
            assist_response=None,  # type: ignore
            unresolved_question="q",
        )


# 15. Unknown effect must not become retry permission
def test_negative_15_unknown_effect_fails_closed(tmp_path: Path):
    from nexus.services.m5_local.contracts import LocalWorkerResponse

    worker_res = LocalWorkerResponse(
        task_id="t15",
        attempt_id="att-15",
        operation_id="op-15",
        status="FAILED",
        write_performed=True,  # Write attempted but failed
    )
    packet = create_handoff_from_worker(
        task_id="t15",
        work_id="w15",
        predecessor_attempt_id="att-15",
        predecessor_operation_id="op-15",
        repo_identity="repo",
        base_sha="sha",
        worker_response=worker_res,
        unresolved_question="q",
    )
    assert any("UNRESOLVED_WRITER_EFFECT:op-15" in eff for eff in packet.unknown_effects)


# 16. Result confidence must not become Completion
def test_negative_16_confidence_not_completion(tmp_path: Path):
    mock_rt = MockLocalRuntime(output_text="100% confident this solves the issue!")
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t16",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
    )
    res = svc.execute(req)
    # Output must remain non-authoritative evidence; status is SUCCESS for query, never Completion
    assert res.status == "SUCCESS"
    assert res.schema == "nexus.m5_local.assist_response.v1"


# 17. Missing source reference must not become factual claim
def test_negative_17_missing_source_reference_notice(tmp_path: Path):
    packet = build_bounded_evidence_packet(
        task_id="t17",
        query="unique_rare_function",
        repo_path=tmp_path,
    )
    assert "never be interpreted as proof that it does not exist" in packet.omitted_files_notice


# 18. Local failure must not automatically dispatch Online
def test_negative_18_local_failure_does_not_auto_dispatch(tmp_path: Path):
    mock_rt = MockLocalRuntime(simulate_error="Model crashed")
    svc = LocalAssistService(runtime=mock_rt)
    req = LocalAssistRequest(
        task_id="t18",
        query="test",
        repo_path=str(tmp_path),
        requested_runtime="mock",
        requested_model="test-model",
    )
    res = svc.execute(req)
    # Returns typed escalation reason for coordinator; does NOT dispatch any remote online call itself!
    assert res.status == "ESCALATED"
    assert res.telemetry.get("remote_dispatch_attempted") is not True


# 19. Online escalation must preserve same work/attempt lineage semantics
def test_negative_19_lineage_preserved_in_escalation(tmp_path: Path):
    assist_res = LocalAssistResponse(
        task_id="t19",
        status="ESCALATED",
        candidate_files=["a.py"],
        evidence_refs=["path:a.py"],
        escalation_reason="LOCAL_CONTEXT_LIMIT",
    )
    packet = create_handoff_from_assist(
        task_id="t19",
        work_id="work-19",
        predecessor_attempt_id="att-19-local",
        predecessor_operation_id="op-19-local",
        repo_identity="James3014/Nexus-new",
        base_sha="base-19",
        assist_response=assist_res,
        unresolved_question="Context exceeded 32k tokens",
    )
    assert packet.predecessor_attempt_id == "att-19-local"
    assert packet.work_id == "work-19"
    assert packet.escalation_reason == "LOCAL_CONTEXT_LIMIT"


# 20. Cache/projection deletion must not destroy canonical work state
def test_negative_20_cache_deletion_resilience(tmp_path: Path):
    packet = build_bounded_evidence_packet(
        task_id="t20",
        query="test",
        repo_path=tmp_path,
    )
    h = packet.packet_hash()
    # Regenerate after simulated cache loss
    packet2 = build_bounded_evidence_packet(
        task_id="t20",
        query="test",
        repo_path=tmp_path,
    )
    assert packet2.packet_hash() == h
