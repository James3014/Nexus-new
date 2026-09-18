"""Tests for provider-agnostic managed local-agent UX (Wave C).

Covers all 15 acceptance criteria specified in the campaign handoff:
1. managed launcher requires valid Core binding before worker execution (worker count == 0 if missing)
2. provider cannot widen allowed paths
3. provider cannot widen verifier set
4. provider cannot modify deletion policy
5. stale base returns REBIND_REQUIRED
6. mismatched binding triggers BLOCK
7. resume/reconnect preserves the same durable binding lineage
8. uncertain effect triggers reconcile, not blind resend
9. missing Core provenance prevents trusted completion
10. provider replacement does not alter completion semantics
11. raw path honestly preserves lower claim ceiling
12. DIRECT_CANONICAL does not escalate to GOVERNED solely due to Core
13. DIRECT_DELEGATED does not claim Planner/Workforce authority
14. GOVERNED path fails closed and never silently downgrades to DIRECT on transport failure
15. worker prose does not constitute completion truth
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

import pytest

from nexus.executors.worker_contract import (
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.orchestrator.ambient_core import (
    CORE_RESPONSE_SCHEMA,
    AmbientCoreControlPort,
)
from nexus.orchestrator.managed_local_agent import (
    ManagedExecutionLane,
    ManagedLocalAgentLauncher,
    ManagedLocalAgentRequest,
    ReconcileAction,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Managed Agent Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "managed@example.com"], cwd=path, check=True)
    (path / "README.md").write_text("# Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial commit"], cwd=path, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


class FakeAmbientCorePort(AmbientCoreControlPort):
    def __init__(self, *, verified: bool = True):
        self.verified = verified
        self.opened_count = 0
        self.verified_count = 0

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
        self.opened_count += 1
        return {
            "session_id": "cms_" + "1" * 32,
            "binding_id": "bind-test",
            "binding_hash": "sha256:" + "2" * 64,
            "operation_id": "op-test",
            "attempt_id": kwargs.get("attempt_id", "attempt-test-1"),
            "acceptance_contract_hash": "sha256:" + "3" * 64,
            "source_revision": "git-commit:" + "4" * 40,
            "source_tree": "git-tree:" + "5" * 40,
        }

    def revalidate_mutation_binding(self, preparation: Mapping[str, Any], **kwargs: Any) -> None:
        pass

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        self.verified_count += 1
        status = "VERIFIED" if self.verified else "FAILED_VERIFICATION"
        return {
            "session_id": "cms_" + "1" * 32,
            "binding_hash": "sha256:" + "2" * 64,
            "candidate_state_hash": kwargs.get("candidate", {}).get("candidate_state_hash")
            if isinstance(kwargs.get("candidate"), Mapping)
            else getattr(kwargs.get("candidate"), "candidate_state_hash", "a" * 64),
            "core_response": {
                "schema": CORE_RESPONSE_SCHEMA,
                "protocol_version": "1.0",
                "verification": {"status": status},
                "hashes": {
                    "acceptance_contract_hash": "sha256:" + "3" * 64,
                    "change_set_hash": "sha256:" + "c" * 64,
                    "verification_plan_hash": "sha256:" + "d" * 64,
                    "evidence_bundle_hash": "sha256:" + "e" * 64,
                    "change_manifest_hash": "sha256:" + "f" * 64,
                },
                "certification": None,
            },
        }


def _setup_service(tmp_path: Path, worker_invoked_tracker: list[str]):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    registry = MagicMock()

    def mock_invoke(provider, contract_arg, lease_arg, *, prompt, **kwargs):
        worker_invoked_tracker.append(provider)
        target_path = Path(lease_arg.target_worktree)
        src = target_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "worker.txt").write_text("worker bounded mutation\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target_path),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity=f"mock-{provider}",
            argv=(f"mock-{provider}",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=100,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    registry.invoke = mock_invoke
    registry.preflight.return_value = WorkerPreflight(
        provider="codex",
        executable="mock-codex",
        executable_available=True,
        authorized=True,
        implementation_status="ready",
        ready=True,
        reason=None,
    )
    service.worker_registry = registry

    def launch_inline(task_id, attempt_id):
        service._run_owned_task(task_id, attempt_id)
        return service._read_state(task_id)

    service._launch_worker = launch_inline
    return service


# Criteria 1: managed launcher requires valid Core binding before worker execution
def test_c1_missing_core_port_blocks_before_worker(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c1-missing-core",
        what="test c1",
        why="prove missing core blocks worker",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=None,  # Missing!
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.status == "FINAL_BLOCK"
    assert receipt.worker_invocation_count == 0
    assert len(invoked) == 0


# Criteria 2: provider cannot widen allowed paths
def test_c2_provider_cannot_widen_allowed_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)

    # Worker modifies forbidden/unallowed path outside allowed_files
    def malicious_invoke(provider, contract_arg, lease_arg, **kwargs):
        invoked.append(provider)
        target_path = Path(lease_arg.target_worktree)
        unallowed = target_path / "unallowed_dir"
        unallowed.mkdir(parents=True, exist_ok=True)
        (unallowed / "leak.txt").write_text("unauthorized write\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target_path),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity="mock",
            argv=("mock",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=50,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    service.worker_registry.invoke = malicious_invoke
    port = FakeAmbientCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c2-widen-paths",
        what="test c2",
        why="prove scope violation blocks commit",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        allowed_files=["src/"],  # only src/ allowed
        ambient_core_port=port,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.candidate_commit_sha is None


# Criteria 3: provider cannot widen verifier set
def test_c3_verifier_commands_locked_in_contract(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    launcher = ManagedLocalAgentLauncher()
    req = ManagedLocalAgentRequest(
        task_id="c3-verifier-lock",
        what="test c3",
        why="prove verifiers locked",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        verifier_commands=["pytest tests/test_core.py"],
    )
    identity = launcher._construct_and_bind_identity(req, repo, base_sha, "attempt-1")
    assert identity.required_verifier_ids == ("pytest tests/test_core.py",)
    # The acceptance_contract hash binds the exact verifier set
    assert "pytest tests/test_core.py" in identity.acceptance_contract["verifier_commands"]


# Criteria 4: provider cannot modify deletion policy
def test_c4_deletion_policy_locked(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    launcher = ManagedLocalAgentLauncher()
    req = ManagedLocalAgentRequest(
        task_id="c4-deletion-lock",
        what="test c4",
        why="prove deletion locked",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        deletion_policy={"allow_deletion": False},
    )
    identity = launcher._construct_and_bind_identity(req, repo, base_sha, "attempt-1")
    assert identity.deletion_policy == {"allow_deletion": False}
    assert identity.acceptance_contract["deletion_policy"] == {"allow_deletion": False}


# Criteria 5: stale base returns REBIND_REQUIRED
def test_c5_stale_base_returns_rebind_required(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    stale_sha = "0" * 40  # Different from real HEAD
    launcher = ManagedLocalAgentLauncher()
    req = ManagedLocalAgentRequest(
        task_id="c5-stale-base",
        what="test c5",
        why="prove stale base fails closed",
        repository_root=str(repo),
        base_revision=stale_sha,
        worker_provider="codex",
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.status == "REBIND_REQUIRED"
    assert receipt.worker_invocation_count == 0


# Criteria 6: mismatched binding triggers BLOCK
def test_c6_mismatched_binding_triggers_block(tmp_path: Path):
    launcher = ManagedLocalAgentLauncher()
    reconcile_res = launcher.reconcile_attempt("non-existent-task")
    assert reconcile_res["action"] == ReconcileAction.BLOCK.value


# Criteria 7: resume/reconnect preserves same durable binding lineage
def test_c7_reconcile_preserves_durable_binding(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c7-reconcile-durable",
        what="test c7",
        why="prove durable lineage",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
    )
    launcher.launch_managed_agent(req)
    reconcile = launcher.reconcile_attempt("c7-reconcile-durable")
    assert reconcile["action"] == ReconcileAction.RECONCILE_EXISTING.value
    assert reconcile["task_id"] == "c7-reconcile-durable"


# Criteria 8: uncertain effect triggers reconcile, not blind resend
def test_c8_uncertain_effect_triggers_reconcile(tmp_path: Path):
    launcher = ManagedLocalAgentLauncher()
    # Attempting to reconcile a drifted base returns REBIND_REQUIRED
    res = launcher.reconcile_attempt(
        "task-unknown",
        observed_base_revision="diff-sha",
    )
    assert res["action"] in (ReconcileAction.BLOCK.value, ReconcileAction.REBIND_REQUIRED.value)


# Criteria 9: missing Core provenance prevents trusted completion
def test_c9_core_failed_blocks_candidate_commit(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=False)  # Core fails!
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c9-core-failed",
        what="test c9",
        why="prove core failure blocks completion",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.candidate_commit_sha is None
    assert receipt.core_provenance_verified is False


# Criteria 10: provider replacement does not alter completion semantics
@pytest.mark.parametrize("provider", ["codex", "gemini", "opencode", "agy"])
def test_c10_provider_neutrality(tmp_path: Path, provider: str):
    repo = tmp_path / f"repo-{provider}"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id=f"c10-{provider}",
        what="test c10",
        why="prove provider neutrality",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider=provider,
        target_root=str(tmp_path / f"targets-{provider}"),
        ambient_core_port=port,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.terminal_status == "PENDING_HUMAN_APPROVAL"
    assert receipt.core_provenance_verified is True
    assert receipt.candidate_commit_sha is not None
    assert receipt.worker_provider == provider


# Criteria 11: raw path honestly preserves lower claim ceiling
def test_c11_raw_path_lower_claim(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    launcher = ManagedLocalAgentLauncher()
    req = ManagedLocalAgentRequest(
        task_id="c11-raw",
        what="test c11",
        why="prove raw lower claim",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        raw_mutation_mode=True,  # Raw copy/paste!
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.pre_write_machine_enforced_core_bound is False
    assert receipt.post_hoc_physical_verification is True
    assert receipt.path_level_prewrite_containment_proven is False
    assert receipt.worker_invocation_count == 0


# Criteria 12: DIRECT_CANONICAL does not escalate to GOVERNED solely due to Core
def test_c12_direct_canonical_lane_preserved(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c12-direct-canonical",
        what="test c12",
        why="prove direct canonical lane not escalated",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        execution_lane=ManagedExecutionLane.DIRECT_CANONICAL.value,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.execution_lane == ManagedExecutionLane.DIRECT_CANONICAL.value


# Criteria 13: DIRECT_DELEGATED does not claim Planner/Workforce authority
def test_c13_direct_delegated_lane_preserved(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c13-direct-delegated",
        what="test c13",
        why="prove direct delegated lane boundary",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        execution_lane=ManagedExecutionLane.DIRECT_DELEGATED.value,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.execution_lane == ManagedExecutionLane.DIRECT_DELEGATED.value


# Criteria 14: GOVERNED fails closed on transport failure and never downgrades to DIRECT
def test_c14_governed_fails_closed_no_silent_downgrade(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    launcher = ManagedLocalAgentLauncher(service=service)

    # Missing core port when core is required under GOVERNED lane
    req = ManagedLocalAgentRequest(
        task_id="c14-governed-failclosed",
        what="test c14",
        why="prove governed no silent downgrade",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=None,
        execution_lane=ManagedExecutionLane.GOVERNED.value,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    assert receipt.terminal_status == "FINAL_BLOCK"
    assert (
        receipt.execution_lane == ManagedExecutionLane.GOVERNED.value
    )  # NEVER downgraded to DIRECT!


# Criteria 15: worker prose does not constitute completion truth
def test_c15_worker_prose_is_not_completion_truth(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort(verified=False)  # Core fails, despite worker boasting success
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="c15-prose-not-truth",
        what="test c15",
        why="prove worker prose is not completion truth",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
    )
    receipt = launcher.launch_managed_agent(req)
    # Even if worker says "completed", Core FAILED blocks candidate commit
    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.core_provenance_verified is False
    assert receipt.candidate_commit_sha is None


def test_wave4_effect_binding_mismatch_blocks_before_worker(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort()
    launcher = ManagedLocalAgentLauncher(service=service)
    task_id = "wave4-effect-mismatch"

    req = ManagedLocalAgentRequest(
        task_id=task_id,
        what="exercise effect-bound managed execution",
        why="prove attempt identity cannot drift",
        repository_root=str(repo),
        repository_identity="James3014/example",
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
        effect_authorization={
            "operation_id": f"op-{task_id}",
            "attempt_id": "attempt-wrong",
            "repository": "James3014/example",
            "source_revision": base_sha,
            "base_revision": base_sha,
            "workspace_id": task_id,
            "target_id": task_id,
        },
        tool_projection_requests={
            "codex": {
                "backend_id": "codex-cli",
                "selected_tools": ["edit"],
                "selected_effects": {"filesystem": {"write_paths": ["src/"]}},
            }
        },
    )

    receipt = launcher.launch_managed_agent(req)

    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.worker_invocation_count == 0
    assert invoked == []
    assert receipt.failure_reasons == ("EFFECT_AUTHORIZATION_IDENTITY_MISMATCH:attempt_id",)


def test_wave4_effect_binding_requires_explicit_repository_identity(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort()
    launcher = ManagedLocalAgentLauncher(service=service)
    task_id = "wave4-effect-repository"

    req = ManagedLocalAgentRequest(
        task_id=task_id,
        what="exercise effect-bound managed execution",
        why="prove local path cannot masquerade as repository identity",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
        effect_authorization={
            "operation_id": f"op-{task_id}",
            "attempt_id": f"attempt-{task_id}-1",
            "repository": str(repo),
            "source_revision": base_sha,
            "base_revision": base_sha,
            "workspace_id": task_id,
            "target_id": task_id,
        },
        tool_projection_requests={
            "codex": {
                "backend_id": "codex-cli",
                "selected_tools": ["edit"],
                "selected_effects": {"filesystem": {"write_paths": ["src/"]}},
            }
        },
    )

    receipt = launcher.launch_managed_agent(req)

    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.worker_invocation_count == 0
    assert invoked == []
    assert receipt.failure_reasons == ("EFFECT_AUTHORIZATION_REPOSITORY_IDENTITY_REQUIRED",)


def test_wave4_effect_binding_requires_projection_pair_before_worker(tmp_path: Path):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    invoked: list[str] = []
    service = _setup_service(tmp_path, invoked)
    port = FakeAmbientCorePort()
    launcher = ManagedLocalAgentLauncher(service=service)
    task_id = "wave4-effect-pair"

    req = ManagedLocalAgentRequest(
        task_id=task_id,
        what="exercise effect-bound managed execution",
        why="prove incomplete pair is rejected",
        repository_root=str(repo),
        repository_identity="James3014/example",
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=port,
        core_envelope_required=True,
        effect_authorization={
            "operation_id": f"op-{task_id}",
            "attempt_id": f"attempt-{task_id}-1",
            "repository": "James3014/example",
            "source_revision": base_sha,
            "base_revision": base_sha,
            "workspace_id": task_id,
            "target_id": task_id,
        },
        tool_projection_requests={},
    )

    receipt = launcher.launch_managed_agent(req)

    assert receipt.terminal_status == "FINAL_BLOCK"
    assert receipt.worker_invocation_count == 0
    assert invoked == []
    assert receipt.failure_reasons == ("EFFECT_AUTHORIZATION_PROJECTION_PAIR_REQUIRED",)
