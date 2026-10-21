"""Regression tests: reconcile effect identity and honest Core-bound receipt claim.

1. ``reconcile_attempt(..., expected_effect_identity=...)`` must not adopt a
   stored attempt whose identity differs from the expected one.
2. ``launch_managed_agent`` must not claim
   ``pre_write_machine_enforced_core_bound=True`` when the Core envelope was
   not required and no Core port was bound.
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

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
    ManagedLocalAgentLauncher,
    ManagedLocalAgentRequest,
    ReconcileAction,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

_BLOCKING_ACTIONS = {ReconcileAction.BLOCK.value, ReconcileAction.REBIND_REQUIRED.value}


def _git(path: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "Regression Test",
        "GIT_AUTHOR_EMAIL": "regression@example.invalid",
        "GIT_COMMITTER_NAME": "Regression Test",
        "GIT_COMMITTER_EMAIL": "regression@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return subprocess.check_output(["git", *args], cwd=path, text=True, env=env).strip()


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    (path / "README.md").write_text("# Repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "-c", "commit.gpgsign=false", "commit", "-qm", "initial commit")
    return _git(path, "rev-parse", "HEAD")


class _FakeCorePort(AmbientCoreControlPort):
    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
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
        return None

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        candidate = kwargs.get("candidate")
        if isinstance(candidate, Mapping):
            state_hash = candidate.get("candidate_state_hash")
        else:
            state_hash = getattr(candidate, "candidate_state_hash", "a" * 64)
        return {
            "session_id": "cms_" + "1" * 32,
            "binding_hash": "sha256:" + "2" * 64,
            "candidate_state_hash": state_hash,
            "core_response": {
                "schema": CORE_RESPONSE_SCHEMA,
                "protocol_version": "1.0",
                "verification": {"status": "VERIFIED"},
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


def _service(tmp_path: Path) -> SelfHostedTaskService:
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    registry = MagicMock()

    def fake_invoke(provider, contract_arg, lease_arg, *, prompt, **kwargs):
        target = Path(lease_arg.target_worktree)
        (target / "src").mkdir(parents=True, exist_ok=True)
        (target / "src" / "worker.txt").write_text("bounded mutation\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity=f"fake-{provider}",
            argv=(f"fake-{provider}",),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=10,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    registry.invoke = fake_invoke
    registry.preflight.return_value = WorkerPreflight(
        provider="codex",
        executable="fake-codex",
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


def _launch(tmp_path: Path, task_id: str, *, core_bound: bool):
    repo = tmp_path / "repo"
    base_sha = _init_repo(repo)
    launcher = ManagedLocalAgentLauncher(service=_service(tmp_path))
    request = ManagedLocalAgentRequest(
        task_id=task_id,
        what="exercise managed launch",
        why="regression for reconcile identity and receipt honesty",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets"),
        ambient_core_port=_FakeCorePort() if core_bound else None,
        core_envelope_required=core_bound,
        verifier_commands=("git --version",),
    )
    receipt = launcher.launch_managed_agent(request)
    return launcher, receipt, base_sha


def _stored_attempt_id(launcher: ManagedLocalAgentLauncher, task_id: str) -> str:
    baseline = launcher.reconcile_attempt(task_id)
    assert baseline["action"] == ReconcileAction.RECONCILE_EXISTING.value
    attempt_id = baseline.get("attempt_id")
    assert isinstance(attempt_id, str) and attempt_id
    return attempt_id


def test_reconcile_with_mismatched_effect_identity_does_not_adopt_attempt(tmp_path: Path):
    task_id = "rg2760-mismatch"
    launcher, _receipt, base_sha = _launch(tmp_path, task_id, core_bound=True)
    stored = _stored_attempt_id(launcher, task_id)

    other = "attempt-of-a-different-effect"
    assert other != stored
    result = launcher.reconcile_attempt(task_id, expected_effect_identity=other)

    assert result["action"] != ReconcileAction.RECONCILE_EXISTING.value
    assert result["action"] in _BLOCKING_ACTIONS

    # Still blocked when the base also matches (identity is checked on its own).
    result_same_base = launcher.reconcile_attempt(
        task_id, expected_effect_identity=other, observed_base_revision=base_sha
    )
    assert result_same_base["action"] != ReconcileAction.RECONCILE_EXISTING.value
    assert result_same_base["action"] in _BLOCKING_ACTIONS


def test_reconcile_with_matching_effect_identity_reconciles_existing(tmp_path: Path):
    task_id = "rg2760-match"
    launcher, _receipt, base_sha = _launch(tmp_path, task_id, core_bound=True)
    stored = _stored_attempt_id(launcher, task_id)

    result = launcher.reconcile_attempt(
        task_id, expected_effect_identity=stored, observed_base_revision=base_sha
    )
    assert result["action"] == ReconcileAction.RECONCILE_EXISTING.value
    assert result["task_id"] == task_id
    assert result["attempt_id"] == stored


def test_reconcile_without_effect_identity_behaves_as_before(tmp_path: Path):
    task_id = "rg2760-absent"
    launcher, _receipt, base_sha = _launch(tmp_path, task_id, core_bound=True)

    result = launcher.reconcile_attempt(task_id)
    assert result["action"] == ReconcileAction.RECONCILE_EXISTING.value
    assert result["task_id"] == task_id

    drift = launcher.reconcile_attempt(task_id, observed_base_revision="0" * 40)
    assert drift["action"] == ReconcileAction.REBIND_REQUIRED.value

    missing = launcher.reconcile_attempt(
        "rg2760-no-such-task", expected_effect_identity="attempt-anything"
    )
    assert missing["action"] == ReconcileAction.BLOCK.value


def test_receipt_without_core_envelope_does_not_claim_core_bound(tmp_path: Path):
    _launcher, receipt, _base = _launch(tmp_path, "rg2760-no-core", core_bound=False)
    assert receipt.pre_write_machine_enforced_core_bound is False


def test_receipt_with_bound_core_envelope_keeps_core_bound_claim(tmp_path: Path):
    _launcher, receipt, _base = _launch(tmp_path, "rg2760-core", core_bound=True)
    assert receipt.pre_write_machine_enforced_core_bound is True
