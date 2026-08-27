"""Comprehensive verification suite for Nexus Fast Start G14 Hard-Enforced Admission."""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.contracts.fast_start_admission import (
    FastStartAdmissionDeniedError,
    FastStartAdmissionRequest,
    FastStartDecision,
)
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.codex_executor import CodexCliExecutor
from nexus.executors.worker_registry import CodexWorkerAdapter
from nexus.orchestrator.fast_start_admission import (
    evaluate_fast_start_admission,
    validate_admission_fence,
)
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectTaskContract,
    ArchitectureDecision,
    DevelopmentGoal,
    HumanApprovalPolicy,
    MutationMode,
)
from nexus.orchestrator.worktree_manager import TargetWorktreeLease
from nexus.services.unified_runtime import OnlineCliSpec, build_subprocess_online_invoker

SAMPLE_549_SNAPSHOT = {
    "schema": "nexus.fast_start_cache.v1",
    "repository": "James3014/Nexus-new",
    "registry_revision": 10,
    "snapshot": {
        "main_sha": "74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        "main_tree": "826c9464f0746ff8265368452924102a4e77f92d",
    },
    "entries": [
        {
            "issue": 92,
            "dispatch_state": "BLOCKED_UPSTREAM",
            "early_stop": True,
            "blocker": {
                "issue": 29,
                "pr": 403,
                "reason": "Issue #92 implementation serialized after #29 terminal state.",
                "state": "open",
                "head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
                "type": "UPSTREAM_SERIALIZATION",
            },
        },
        {
            "issue": 419,
            "dispatch_state": "BLOCKED_PR",
            "early_stop": True,
            "blocker": {
                "pr": 402,
                "reason": "PR #402 active overlap in AGENTS.md",
                "state": "open",
                "head_sha": "f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1",
                "type": "ACTIVE_PR_OVERLAP",
            },
        },
        {
            "issue": 526,
            "dispatch_state": "HOST_REBIND_REQUIRED",
            "early_stop": True,
            "kind": "HOST_BOUND_REFERENCE",
        },
        {
            "issue": 398,
            "dispatch_state": "EVIDENCE_BLOCKED",
            "early_stop": True,
            "kind": "HOST_BOUND_REFERENCE",
        },
        {
            "issue": 129,
            "dispatch_state": "READY_CANDIDATE",
            "early_stop": False,
            "kind": "IMPLEMENTATION_BASE",
        },
    ],
}


def _make_lease(tmp_path: Path, task_id: str, base_rev: str = "74d91779347667b997eb2c51f1d0873bbdf3e6a6") -> TargetWorktreeLease:
    target = tmp_path / f"target_{task_id}"
    target.mkdir(parents=True, exist_ok=True)
    return TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1",
        lease_id="lease_1",
        task_id=task_id,
        controller_revision=base_rev,
        target_base_revision=base_rev,
        target_worktree=str(target),
        target_branch="nexus/task/test",
        initial_head=base_rev,
        initial_status_sha256="0" * 64,
        controller_status_sha256="1" * 64,
        created_from_exact_revision=True,
        commit_created=False,
        merge_performed=False,
    )


def _make_contract(tmp_path: Path, task_id: str) -> ArchitectTaskContract:
    return ArchitectTaskContract(
        task_id=task_id,
        objective="Execute task",
        goal=DevelopmentGoal(what="Execute task", why="G14 test"),
        architecture_decisions=[
            ArchitectureDecision(
                decision_id="provider-boundary",
                selected_option="Fresh Codex exec",
                rationale="Avoid ambient session reuse",
                rejected_alternatives=["resume --last"],
            )
        ],
        acceptance_profile=AcceptanceProfile(
            verifier_commands=["pytest -q"],
            protected_contracts=["candidate-receipt-v1"],
            required_evidence=["stdout_sha256"],
        ),
        human_approval_policy=HumanApprovalPolicy(approver_roles=["James"]),
        controller_revision="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        target_base_revision="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        controller_repo_root=str(tmp_path),
        target_repo_root=str(tmp_path / f"target_{task_id}"),
        target_worktree_root=str(tmp_path),
        allowed_files=["nexus/"],
        verifier_commands=["pytest -q"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def test_t1_blocked_upstream_issue_92_denied_zero_launch(tmp_path, monkeypatch):
    """T1: #92 BLOCKED_UPSTREAM denies launch, launch calls = 0, zero retrieval."""
    launch_calls = []

    def fake_worker(request):
        launch_calls.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}",
            stderr=b"",
            wall_time_ms=10,
            process_group_id=1,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)

    def mock_metadata_fetcher(pr=None, issue=None):
        assert pr == 403 or issue == 29
        return {
            "pr_state": "open",
            "pr_merged": False,
            "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
            "issue_state": "open",
        }

    # Evaluate admission explicitly
    req = FastStartAdmissionRequest(
        issue_number=92,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req, metadata_fetcher=mock_metadata_fetcher)
    assert admission.decision == FastStartDecision.DENY_BLOCKED
    assert admission.codex_launch_allowed is False
    assert "PR #403 is still OPEN" in admission.reason

    # Attempt Codex execution through executor
    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT)

    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
            metadata_fetcher=mock_metadata_fetcher,
        )

    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert len(launch_calls) == 0  # Zero subprocess launch


def test_t2_blocked_pr_overlap_denied_zero_launch(tmp_path, monkeypatch):
    """T2: Active PR overlap (#419 on PR #402) denies launch."""
    launch_calls = []
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def mock_metadata_fetcher(pr=None, issue=None):
        return {"pr_state": "open", "pr_merged": False, "pr_head_sha": "f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1"}

    req = FastStartAdmissionRequest(
        issue_number=419,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req, metadata_fetcher=mock_metadata_fetcher)
    assert admission.decision == FastStartDecision.DENY_BLOCKED
    assert admission.codex_launch_allowed is False

    contract = _make_contract(tmp_path, "github-issue-419-bootstrap-budget")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT)

    with pytest.raises(FastStartAdmissionDeniedError):
        executor.invoke(
            contract,
            lease,
            prompt="Reduce AGENTS.md size",
            metadata_fetcher=mock_metadata_fetcher,
        )
    assert len(launch_calls) == 0


def test_t3_host_and_evidence_blocked(tmp_path, monkeypatch):
    """T3: HOST_REBIND_REQUIRED (#526) and EVIDENCE_BLOCKED (#398) denied."""
    # #526
    req_526 = FastStartAdmissionRequest(
        issue_number=526,
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    adm_526 = evaluate_fast_start_admission(req_526)
    assert adm_526.decision == FastStartDecision.DENY_HOST_BOUND
    assert adm_526.codex_launch_allowed is False

    # #398
    req_398 = FastStartAdmissionRequest(
        issue_number=398,
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    adm_398 = evaluate_fast_start_admission(req_398)
    assert adm_398.decision == FastStartDecision.DENY_EVIDENCE_BLOCKED
    assert adm_398.codex_launch_allowed is False


def test_t4_blocker_transition_unblocks_to_discovery(tmp_path):
    """T4: Cache says blocked, but fresh blocker has merged -> unblocks to full discovery."""
    def mock_resolved_fetcher(pr=None, issue=None):
        return {
            "pr_state": "closed",
            "pr_merged": True,
            "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
            "issue_state": "closed",
        }

    req = FastStartAdmissionRequest(
        issue_number=92,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req, metadata_fetcher=mock_resolved_fetcher)
    assert admission.decision == FastStartDecision.ALLOW_FULL_DISCOVERY
    assert admission.codex_launch_allowed is True
    assert "resolved in fresh metadata" in admission.reason


def test_t5_malformed_registry_safe_fallback(tmp_path):
    """T5: Malformed registry does NOT crash or cause false block; falls back to full discovery."""
    malformed = {"schema": "corrupted_schema", "entries": "not_a_list"}
    req = FastStartAdmissionRequest(
        issue_number=92,
        registry_snapshot=malformed,
    )
    admission = evaluate_fast_start_admission(req)
    assert admission.decision == FastStartDecision.ALLOW_FULL_DISCOVERY
    assert admission.codex_launch_allowed is True
    assert admission.cache_disposition == "CACHE_MALFORMED"


def test_t6_cache_miss_allows_full_discovery(tmp_path, monkeypatch):
    """T6: Issue not in cache allows full discovery and normal execution."""
    launch_calls = []

    def fake_worker(request):
        launch_calls.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}",
            stderr=b"",
            wall_time_ms=10,
            process_group_id=1,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)

    req = FastStartAdmissionRequest(
        issue_number=9999,  # Unknown issue
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req)
    assert admission.decision == FastStartDecision.ALLOW_FULL_DISCOVERY
    assert admission.codex_launch_allowed is True
    assert admission.cache_disposition == "CACHE_MISS"

    # Codex can run normally for cache miss
    contract = _make_contract(tmp_path, "github-issue-9999-new-feature")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT)
    receipt = executor.invoke(contract, lease, prompt="Build new feature")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1


def test_t7_ready_candidate_fresh_evidence_allows_launch(tmp_path, monkeypatch):
    """T7: READY_CANDIDATE with matching main evidence allows launch exactly once."""
    launch_calls = []

    def fake_worker(request):
        launch_calls.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}",
            stderr=b"",
            wall_time_ms=10,
            process_group_id=1,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)

    req = FastStartAdmissionRequest(
        issue_number=129,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req)
    assert admission.decision == FastStartDecision.ALLOW_READY
    assert admission.codex_launch_allowed is True
    assert admission.cache_disposition == "CACHE_HIT"

    contract = _make_contract(tmp_path, "github-issue-129-atomic-work-claim")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT)
    receipt = executor.invoke(contract, lease, prompt="Execute issue 129 claim")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1


def test_t8_ready_becomes_stale_on_main_drift(tmp_path):
    """T8: READY_CANDIDATE rebinds to full discovery if main SHA drifted."""
    req = FastStartAdmissionRequest(
        issue_number=129,
        current_main_sha="deadbeef11112222333344445555666677778888",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    admission = evaluate_fast_start_admission(req)
    assert admission.decision == FastStartDecision.ALLOW_FULL_DISCOVERY
    assert admission.codex_launch_allowed is True
    assert admission.cache_disposition == "TARGETED_REBIND"


def test_t9_launch_time_fence_rejects_drifted_receipt(tmp_path):
    """T9: Launch fence rejects receipt if main SHA or blockers drifted before execution."""
    req = FastStartAdmissionRequest(
        issue_number=129,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        current_main_tree="826c9464f0746ff8265368452924102a4e77f92d",
        registry_snapshot=SAMPLE_549_SNAPSHOT,
    )
    receipt = evaluate_fast_start_admission(req)
    assert receipt.decision == FastStartDecision.ALLOW_READY

    # Matching state: fence valid
    assert validate_admission_fence(
        receipt,
        current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
        current_main_tree="826c9464f0746ff8265368452924102a4e77f92d",
    ) is True

    # Main drifted: fence fails
    assert validate_admission_fence(
        receipt,
        current_main_sha="changed_sha_1234567890",
        current_main_tree="826c9464f0746ff8265368452924102a4e77f92d",
    ) is False


def test_t10_unrelated_non_issue_task_works_unimpeded(tmp_path, monkeypatch):
    """T10: Non-issue managed Codex tasks execute without obstruction."""
    launch_calls = []

    def fake_worker(request):
        launch_calls.append(request)
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}",
            stderr=b"",
            wall_time_ms=10,
            process_group_id=1,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)

    contract = _make_contract(tmp_path, "local-refactor-cleanup")
    lease = _make_lease(tmp_path, contract.task_id)
    adapter = CodexWorkerAdapter(executor=CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT))
    receipt = adapter.invoke(contract, lease, prompt="Clean up unused imports")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1


def test_online_cli_worker_codex_admission_denied(monkeypatch):
    """Verify build_subprocess_online_invoker blocks Codex when admission denies."""
    runner_calls = []

    def fake_runner(*args, **kwargs):
        runner_calls.append(args)
        class FakeCompleted:
            returncode = 0
            stdout = "{}"
            stderr = ""
        return FakeCompleted()

    spec = OnlineCliSpec(
        provider="codex",
        command=("codex", "exec"),
        model_name="gpt-5.6-luna",
        timeout_sec=60,
    )
    invoker = build_subprocess_online_invoker(spec, runner=fake_runner)

    context = {
        "task_id": "github-issue-92-source-identity",
        "issue": 92,
        "fast_start_snapshot": SAMPLE_549_SNAPSHOT,
        "online_prompt": "Implement issue 92",
    }

    result = invoker(context)

    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert "fast_start_admission_denied" in result["error"]
    assert len(runner_calls) == 0
