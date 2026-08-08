from pathlib import Path

import pytest

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.codex_executor import CodexCliExecutor
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectureDecision,
    ArchitectTaskContract,
    DevelopmentGoal,
    HumanApprovalPolicy,
    MutationMode,
)
from nexus.orchestrator.worktree_manager import TargetWorktreeLease


def _lease(tmp_path: Path, contract: ArchitectTaskContract) -> TargetWorktreeLease:
    target = tmp_path / "target"
    target.mkdir()
    return TargetWorktreeLease(
        schema="nexus.target_worktree_lease.v1",
        lease_id="lease",
        task_id=contract.task_id,
        controller_revision=contract.controller_revision,
        target_base_revision=contract.target_base_revision,
        target_worktree=str(target),
        target_branch="nexus/task/codex-vertical",
        initial_head=contract.target_base_revision,
        initial_status_sha256="0" * 64,
        controller_status_sha256="1" * 64,
        created_from_exact_revision=True,
        commit_created=False,
        merge_performed=False,
    )


def _contract(tmp_path: Path) -> ArchitectTaskContract:
    return ArchitectTaskContract(
        task_id="codex-vertical",
        objective="Run one bounded Codex worker",
        goal=DevelopmentGoal(what="Run one bounded Codex worker", why="Prove target-only execution"),
        architecture_decisions=[
            ArchitectureDecision(
                decision_id="provider-boundary",
                selected_option="Fresh Codex exec",
                rationale="Avoid ambient session reuse",
                rejected_alternatives=["resume --last"],
            )
        ],
        acceptance_profile=AcceptanceProfile(
            verifier_commands=["python3 -m pytest -q"],
            protected_contracts=["candidate-receipt-v1"],
            required_evidence=["stdout_sha256"],
        ),
        human_approval_policy=HumanApprovalPolicy(approver_roles=["James"]),
        controller_revision="a" * 40,
        target_base_revision="b" * 40,
        controller_repo_root=str(tmp_path / "controller"),
        target_repo_root=str(tmp_path / "target"),
        target_worktree_root=str(tmp_path),
        allowed_files=["nexus/"],
        verifier_commands=["python3 -m pytest -q"],
        protected_contracts=["candidate-receipt-v1"],
        preferred_provider="codex",
        maximum_provider_calls=1,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def test_codex_executor_builds_fresh_target_bound_command(tmp_path, monkeypatch):
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    monkeypatch.delenv("NEXUS_CODEX_WORKER_MODEL", raising=False)
    captured = {}

    def fake_worker(request):
        captured["request"] = request
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}\n",
            stderr=b"",
            wall_time_ms=12,
            process_group_id=42,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)
    receipt = CodexCliExecutor(executable="codex").invoke(
        contract,
        lease,
        prompt="Edit only files allowed by the contract.",
    )

    request = captured["request"]
    assert receipt.provider == "codex"
    assert request.argv[:2] == ("exec", "--ephemeral")
    assert request.argv[request.argv.index("-m") + 1] == "gpt-5.6-luna"
    assert request.argv[request.argv.index("-c") + 1] == "model_reasoning_effort=medium"
    assert "resume" not in request.argv
    assert "--json" in request.argv
    assert "--sandbox" in request.argv
    assert request.argv[request.argv.index("--cd") + 1] == str(Path(lease.target_worktree).resolve())
    assert request.cwd == str(Path(lease.target_worktree).resolve())
    assert receipt.commit_created is False
    assert receipt.merge_performed is False


@pytest.mark.parametrize("configured_model", [None, "", "   "])
def test_codex_executor_uses_environment_model_or_blank_fallback(
    monkeypatch, configured_model
):
    if configured_model is None:
        monkeypatch.delenv("NEXUS_CODEX_WORKER_MODEL", raising=False)
    else:
        monkeypatch.setenv("NEXUS_CODEX_WORKER_MODEL", configured_model)

    executor = CodexCliExecutor()

    assert executor.model == (configured_model.strip() if configured_model and configured_model.strip() else "gpt-5.6-luna")
    assert executor.reasoning_effort == "medium"


def test_codex_executor_rejects_invalid_reasoning_effort(monkeypatch):
    monkeypatch.setenv("NEXUS_CODEX_REASONING_EFFORT", "invalid")
    with pytest.raises(ValueError, match="NEXUS_CODEX_REASONING_EFFORT"):
        CodexCliExecutor()


def test_codex_executor_uses_configured_reasoning_effort(monkeypatch):
    monkeypatch.setenv("NEXUS_CODEX_REASONING_EFFORT", "high")
    executor = CodexCliExecutor()
    assert executor.reasoning_effort == "high"


def test_codex_executor_explicit_model_overrides_environment(monkeypatch):
    monkeypatch.setenv("NEXUS_CODEX_WORKER_MODEL", "environment-model")

    assert CodexCliExecutor(model="explicit-model").model == "explicit-model"


def test_codex_worker_reconstruction_preserves_selected_model(tmp_path, monkeypatch):
    from nexus.executors.worker_registry import CodexWorkerAdapter

    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    captured = {}

    def fake_worker(request):
        captured["request"] = request
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=0,
            stdout=b"{}\n",
            stderr=b"",
            wall_time_ms=12,
            process_group_id=42,
        )

    monkeypatch.setattr("nexus.executors.codex_executor.run_cli_worker", fake_worker)
    CodexWorkerAdapter(executor=CodexCliExecutor(model="selected-model")).invoke(
        contract,
        lease,
        prompt="Preserve the selected model.",
        timeout_seconds=30,
    )

    request = captured["request"]
    assert request.argv[request.argv.index("-m") + 1] == "selected-model"
