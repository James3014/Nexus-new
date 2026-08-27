"""Comprehensive verification suite for Nexus Fast Start G14 Hard-Enforced Admission."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nexus.contracts.fast_start_admission import (
    FastStartAdmissionDeniedError,
    FastStartAdmissionRequest,
    FastStartAdmissionResult,
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


@pytest.fixture(autouse=True)
def setup_codex_bin(monkeypatch):
    monkeypatch.setenv("NEXUS_CODEX_BIN", "/bin/sh")


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


def _make_lease(
    tmp_path: Path, task_id: str, base_rev: str = "74d91779347667b997eb2c51f1d0873bbdf3e6a6"
) -> TargetWorktreeLease:
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
        return {
            "pr_state": "open",
            "pr_merged": False,
            "pr_head_sha": "f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1",
        }

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
    executor = CodexCliExecutor(executable="/bin/sh", fast_start_snapshot=SAMPLE_549_SNAPSHOT)
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
    executor = CodexCliExecutor(executable="/bin/sh", fast_start_snapshot=SAMPLE_549_SNAPSHOT)
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
    assert (
        validate_admission_fence(
            receipt,
            current_main_sha="74d91779347667b997eb2c51f1d0873bbdf3e6a6",
            current_main_tree="826c9464f0746ff8265368452924102a4e77f92d",
        )
        is True
    )

    # Main drifted: fence fails
    assert (
        validate_admission_fence(
            receipt,
            current_main_sha="changed_sha_1234567890",
            current_main_tree="826c9464f0746ff8265368452924102a4e77f92d",
        )
        is False
    )


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
    monkeypatch.setenv("NEXUS_CODEX_BIN", "/bin/sh")

    contract = _make_contract(tmp_path, "local-refactor-cleanup")
    lease = _make_lease(tmp_path, contract.task_id)
    adapter = CodexWorkerAdapter(executor=CodexCliExecutor(fast_start_snapshot=SAMPLE_549_SNAPSHOT))
    receipt = adapter.invoke(contract, lease, prompt="Clean up unused imports")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1


def test_t11_no_snapshot_bypass_closed(tmp_path, monkeypatch):
    """T11: Issue #92 task with no snapshot provided triggers mandatory preflight and is denied."""
    launch_calls = []
    reg_calls = []
    meta_calls = []

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

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return {
            "pr_state": "open",
            "pr_merged": False,
            "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
            "issue_state": "open",
        }

    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    # Caller does NOT pass fast_start_snapshot
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=mock_reg_fetcher,
        metadata_fetcher=mock_meta_fetcher,
    )

    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
        )

    assert len(reg_calls) == 1
    assert len(meta_calls) == 1
    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert len(launch_calls) == 0  # Zero subprocess launch


def test_t12_registry_preflight_failure_does_not_launch(tmp_path, monkeypatch):
    """T12: If registry acquisition fails/is unavailable, fail closed and zero launch."""
    launch_calls = []
    reg_calls = []

    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def failing_reg_fetcher():
        reg_calls.append(True)
        raise RuntimeError("GitHub API 503 unavailable")

    contract = _make_contract(tmp_path, "github-issue-92-task")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=failing_reg_fetcher,
    )

    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Work on issue 92",
        )

    assert len(reg_calls) == 1
    assert exc_info.value.decision.decision == FastStartDecision.DENY_EVIDENCE_BLOCKED
    assert exc_info.value.decision.codex_launch_allowed is False
    assert exc_info.value.decision.cache_disposition == "CACHE_UNAVAILABLE"
    assert len(launch_calls) == 0


def test_t13_blocked_requires_fresh_metadata(tmp_path, monkeypatch):
    """T13: Cache shows blocked; insufficient fresh metadata denies and does not launch."""
    launch_calls = []
    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def _deny_issue_419(*, metadata_fetcher):
        contract = _make_contract(tmp_path, "github-issue-419-task")
        lease = _make_lease(tmp_path, contract.task_id)
        executor = CodexCliExecutor(
            executable="/bin/sh",
            registry_fetcher=lambda: SAMPLE_549_SNAPSHOT,
            metadata_fetcher=metadata_fetcher,
        )
        with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
            executor.invoke(contract, lease, prompt="Work on issue 419")
        return exc_info.value.decision

    meta_raise_calls = []

    def failing_meta_fetcher(pr=None, issue=None):
        meta_raise_calls.append((pr, issue))
        raise RuntimeError("PR metadata fetch error")

    raised = _deny_issue_419(metadata_fetcher=failing_meta_fetcher)
    assert len(meta_raise_calls) == 1
    assert raised.decision == FastStartDecision.DENY_EVIDENCE_BLOCKED
    assert raised.codex_launch_allowed is False
    assert len(launch_calls) == 0

    meta_empty_calls = []

    def empty_meta_fetcher(pr=None, issue=None):
        meta_empty_calls.append((pr, issue))
        return {}

    empty = _deny_issue_419(metadata_fetcher=empty_meta_fetcher)
    assert len(meta_empty_calls) == 1
    assert empty.decision == FastStartDecision.DENY_EVIDENCE_BLOCKED
    assert empty.codex_launch_allowed is False
    assert len(launch_calls) == 0

    stale_snapshot = {
        **SAMPLE_549_SNAPSHOT,
        "entries": [
            {
                "issue": 419,
                "dispatch_state": "BLOCKED_PR",
                "early_stop": True,
                "blocker": {
                    "pr": 402,
                    "reason": "stale cache already looks closed",
                    "state": "closed",
                    "head_sha": "f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1",
                    "type": "ACTIVE_PR_OVERLAP",
                },
            }
        ],
    }
    meta_stale_calls = []

    def stale_empty_meta_fetcher(pr=None, issue=None):
        meta_stale_calls.append((pr, issue))
        return {}

    contract = _make_contract(tmp_path, "github-issue-419-stale")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=lambda: stale_snapshot,
        metadata_fetcher=stale_empty_meta_fetcher,
    )
    with pytest.raises(FastStartAdmissionDeniedError) as stale_exc:
        executor.invoke(contract, lease, prompt="Work on issue 419")
    assert len(meta_stale_calls) == 1
    assert stale_exc.value.decision.decision == FastStartDecision.DENY_EVIDENCE_BLOCKED
    assert stale_exc.value.decision.codex_launch_allowed is False
    assert len(launch_calls) == 0


def test_t14_blocker_resolved_allows_launch(tmp_path, monkeypatch):
    """T14: Cache shows blocked, fresh metadata proves blocker merged -> allows launch once with evidence."""
    launch_calls = []
    meta_calls = []

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

    def mock_resolved_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return {
            "pr_state": "closed",
            "pr_merged": True,
            "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
            "issue_state": "closed",
        }

    contract = _make_contract(tmp_path, "github-issue-92-resolved")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=lambda: SAMPLE_549_SNAPSHOT,
        metadata_fetcher=mock_resolved_meta_fetcher,
    )

    receipt = executor.invoke(contract, lease, prompt="Work on issue 92")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1
    assert len(meta_calls) == 1
    assert receipt.admission_receipt is not None
    assert receipt.admission_receipt.decision == FastStartDecision.ALLOW_FULL_DISCOVERY
    assert receipt.admission_receipt.cache_disposition == "TARGETED_REBIND"
    assert receipt.admission_receipt.fresh_rebind_evidence.get("pr_merged") is True


def test_t15_ready_from_mandatory_preflight(tmp_path, monkeypatch):
    """T15: Caller provides no snapshot; mandatory preflight finds #129 READY -> launch once."""
    launch_calls = []
    reg_calls = []

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

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    contract = _make_contract(tmp_path, "github-issue-129-atomic-work-claim")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=mock_reg_fetcher,
    )

    receipt = executor.invoke(contract, lease, prompt="Execute issue 129 claim")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1
    assert len(reg_calls) == 1
    assert receipt.admission_receipt is not None
    assert receipt.admission_receipt.decision == FastStartDecision.ALLOW_READY


def test_t16_non_issue_unaffected(tmp_path, monkeypatch):
    """T16: Non-issue managed Codex task executes without fetching #549."""
    launch_calls = []
    reg_calls = []

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

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    contract = _make_contract(tmp_path, "local-refactor-task")
    lease = _make_lease(tmp_path, contract.task_id)
    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=mock_reg_fetcher,
    )

    receipt = executor.invoke(contract, lease, prompt="Clean up codebase")
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1
    assert len(reg_calls) == 0  # No #549 registry fetch for non-issue tasks
    assert receipt.admission_receipt is not None
    assert receipt.admission_receipt.cache_disposition == "NON_ISSUE_TASK"


def test_t17_unified_runtime_bypass_closed():
    """T17: build_subprocess_online_invoker blocks Codex without snapshot when registry shows blocked."""
    runner_calls = []
    reg_calls = []
    meta_calls = []

    def fake_runner(*args, **kwargs):
        runner_calls.append(args)

        class FakeCompleted:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return FakeCompleted()

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return {
            "pr_state": "open",
            "pr_merged": False,
            "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
            "issue_state": "open",
        }

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
        # No "fast_start_snapshot" in context!
        "registry_fetcher": mock_reg_fetcher,
        "metadata_fetcher": mock_meta_fetcher,
        "online_prompt": "Implement issue 92",
    }

    result = invoker(context)

    assert result["invoked"] is False
    assert result["provider_call_count"] == 0
    assert "fast_start_admission_denied" in result["error"]
    assert len(runner_calls) == 0
    assert len(reg_calls) == 1
    assert len(meta_calls) == 1
    assert "fast_start_admission" in result


def _open_blocker_metadata(pr=None, issue=None):
    return {
        "pr_state": "open",
        "pr_merged": False,
        "pr_head_sha": "9cebb6457a06cf696964e5902c33075f53395be0",
        "issue_state": "open",
    }


def test_t18_fabricated_allow_receipt_cannot_bypass_blocked_issue(tmp_path, monkeypatch):
    """T18: Caller ALLOW_READY receipt does not skip blocked-issue preflight."""
    launch_calls = []
    reg_calls = []
    meta_calls = []

    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return _open_blocker_metadata(pr=pr, issue=issue)

    ready_snapshot = {
        **SAMPLE_549_SNAPSHOT,
        "entries": [
            {
                "issue": 92,
                "dispatch_state": "READY_CANDIDATE",
                "early_stop": False,
                "kind": "IMPLEMENTATION_BASE",
            }
        ],
    }
    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    fabricated = evaluate_fast_start_admission(
        FastStartAdmissionRequest(
            issue_number=92,
            current_main_sha=lease.initial_head,
            task_id=contract.task_id,
            registry_snapshot=ready_snapshot,
        )
    )
    assert fabricated.decision == FastStartDecision.ALLOW_READY
    assert fabricated.codex_launch_allowed is True

    executor = CodexCliExecutor(executable="/bin/sh")
    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
            admission_receipt=fabricated,
            registry_fetcher=mock_reg_fetcher,
            metadata_fetcher=mock_meta_fetcher,
        )

    assert len(reg_calls) == 1
    assert len(meta_calls) == 1
    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert exc_info.value.decision.codex_launch_allowed is False
    assert len(launch_calls) == 0


def test_t19_flipped_codex_launch_allowed_cannot_bypass(tmp_path, monkeypatch):
    """T19: Copying a blocked receipt and flipping codex_launch_allowed cannot launch."""
    launch_calls = []
    reg_calls = []
    meta_calls = []

    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return _open_blocker_metadata(pr=pr, issue=issue)

    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    blocked = evaluate_fast_start_admission(
        FastStartAdmissionRequest(
            issue_number=92,
            current_main_sha=lease.initial_head,
            task_id=contract.task_id,
            registry_snapshot=SAMPLE_549_SNAPSHOT,
        ),
        metadata_fetcher=mock_meta_fetcher,
    )
    assert blocked.decision == FastStartDecision.DENY_BLOCKED
    assert blocked.codex_launch_allowed is False
    tampered = replace(blocked, codex_launch_allowed=True)
    assert tampered.fence_digest == blocked.fence_digest
    assert tampered.decision == FastStartDecision.DENY_BLOCKED
    assert tampered.codex_launch_allowed is True

    executor = CodexCliExecutor(executable="/bin/sh")
    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
            admission_receipt=tampered,
            registry_fetcher=mock_reg_fetcher,
            metadata_fetcher=mock_meta_fetcher,
        )

    assert len(reg_calls) == 1
    assert len(meta_calls) >= 1
    assert exc_info.value.decision.codex_launch_allowed is False
    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert len(launch_calls) == 0


def test_t20_cross_issue_ready_receipt_reuse_denied(tmp_path, monkeypatch):
    """T20: Issue #129 READY receipt cannot authorize blocked Issue #92."""
    launch_calls = []
    reg_calls = []
    meta_calls = []

    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return _open_blocker_metadata(pr=pr, issue=issue)

    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    ready_129 = evaluate_fast_start_admission(
        FastStartAdmissionRequest(
            issue_number=129,
            current_main_sha=lease.initial_head,
            task_id="github-issue-129-atomic-work-claim",
            registry_snapshot=SAMPLE_549_SNAPSHOT,
        )
    )
    assert ready_129.issue == 129
    assert ready_129.decision == FastStartDecision.ALLOW_READY
    assert ready_129.codex_launch_allowed is True

    executor = CodexCliExecutor(executable="/bin/sh")
    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        executor.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
            admission_receipt=ready_129,
            registry_fetcher=mock_reg_fetcher,
            metadata_fetcher=mock_meta_fetcher,
        )

    assert len(reg_calls) == 1
    assert len(meta_calls) == 1
    assert exc_info.value.decision.issue == 92
    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert len(launch_calls) == 0


def test_t21_worker_registry_caller_receipt_bypass_closed(tmp_path, monkeypatch):
    """T21: CodexWorkerAdapter cannot forward an ALLOW receipt as launch authority."""
    launch_calls = []
    reg_calls = []
    meta_calls = []

    monkeypatch.setattr(
        "nexus.executors.codex_executor.run_cli_worker",
        lambda req: launch_calls.append(req),
    )

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    def mock_meta_fetcher(pr=None, issue=None):
        meta_calls.append((pr, issue))
        return _open_blocker_metadata(pr=pr, issue=issue)

    contract = _make_contract(tmp_path, "github-issue-92-source-identity")
    lease = _make_lease(tmp_path, contract.task_id)
    allow_receipt = FastStartAdmissionResult(
        issue=92,
        decision=FastStartDecision.ALLOW_READY,
        codex_launch_allowed=True,
        reason="caller fabricated worker-registry receipt",
        observed_main_sha=lease.initial_head,
    )

    adapter = CodexWorkerAdapter(
        executor=CodexCliExecutor(
            executable="/bin/sh",
            registry_fetcher=mock_reg_fetcher,
            metadata_fetcher=mock_meta_fetcher,
        )
    )
    with pytest.raises(FastStartAdmissionDeniedError) as exc_info:
        adapter.invoke(
            contract,
            lease,
            prompt="Implement issue 92 declared source hash validation",
            admission_receipt=allow_receipt,
            registry_fetcher=mock_reg_fetcher,
            metadata_fetcher=mock_meta_fetcher,
        )

    assert len(reg_calls) >= 1
    assert len(meta_calls) >= 1
    assert exc_info.value.decision.decision == FastStartDecision.DENY_BLOCKED
    assert exc_info.value.decision.codex_launch_allowed is False
    assert len(launch_calls) == 0


def test_t22_issue_ready_with_irrelevant_caller_receipt_launches_once(tmp_path, monkeypatch):
    """T22: Fresh ALLOW_READY evaluation launches once; caller receipt is not returned."""
    launch_calls = []
    reg_calls = []

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

    def mock_reg_fetcher():
        reg_calls.append(True)
        return SAMPLE_549_SNAPSHOT

    contract = _make_contract(tmp_path, "github-issue-129-atomic-work-claim")
    lease = _make_lease(tmp_path, contract.task_id)
    caller_receipt = FastStartAdmissionResult(
        issue=92,
        decision=FastStartDecision.DENY_BLOCKED,
        codex_launch_allowed=False,
        reason="irrelevant caller deny receipt",
    )

    executor = CodexCliExecutor(
        executable="/bin/sh",
        registry_fetcher=mock_reg_fetcher,
    )
    receipt = executor.invoke(
        contract,
        lease,
        prompt="Execute issue 129 claim",
        admission_receipt=caller_receipt,
    )
    assert receipt.worker_status == "COMPLETED"
    assert len(launch_calls) == 1
    assert len(reg_calls) == 1
    assert receipt.admission_receipt is not None
    assert receipt.admission_receipt.issue == 129
    assert receipt.admission_receipt.decision == FastStartDecision.ALLOW_READY
    assert receipt.admission_receipt.reason != caller_receipt.reason


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
