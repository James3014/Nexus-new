import sys
from pathlib import Path

import pytest

from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerResult,
    CliWorkerStatus,
    run_cli_worker,
)
from nexus.executors.codex_executor import CodexCliExecutor
from nexus.orchestrator.task_contract import (
    AcceptanceProfile,
    ArchitectTaskContract,
    ArchitectureDecision,
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
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
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
    receipt = CodexCliExecutor(executable=str(executable)).invoke(
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
    assert receipt.provider_calls == 1
    assert receipt.provider_attempt_count == 1


@pytest.mark.parametrize(
    ("status", "provider_calls", "provider_attempt_count"),
    [
        (CliWorkerStatus.START_FAILED, 0, 0),
        (CliWorkerStatus.COMPLETED, 1, 1),
        (CliWorkerStatus.TIMED_OUT, 1, 1),
    ],
)
def test_codex_executor_receipt_counts_started_invocation_once(
    tmp_path, status, provider_calls, provider_attempt_count
):
    contract = _contract(tmp_path)
    lease = _lease(tmp_path, contract)
    result = CliWorkerResult(
        status=status,
        executable_identity="codex",
        argv=("exec",),
        cwd=str(lease.target_worktree),
        exit_code=None if status == CliWorkerStatus.START_FAILED else 0,
        stdout=b"",
        stderr=b"",
        wall_time_ms=1,
        process_group_id=None if status == CliWorkerStatus.START_FAILED else 42,
        process_group_killed=status == CliWorkerStatus.TIMED_OUT,
        timed_out=status == CliWorkerStatus.TIMED_OUT,
    )

    receipt = CodexCliExecutor._receipt(contract, lease, result)

    assert receipt.provider_calls == provider_calls
    assert receipt.provider_attempt_count == provider_attempt_count


@pytest.mark.parametrize(
    ("executable_factory", "expected_status", "expected_count"),
    [
        ("completed", CliWorkerStatus.COMPLETED, 1),
        ("start_failed", CliWorkerStatus.START_FAILED, 0),
    ],
)
def test_codex_receipt_counts_real_local_cli_invocation(
    tmp_path, executable_factory, expected_status, expected_count
):
    if executable_factory == "completed":
        request = CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", "print('ready')"),
            cwd=str(tmp_path),
            timeout_seconds=5,
        )
    else:
        executable = tmp_path / "missing-interpreter"
        executable.write_text("#!/no/such/interpreter\n", encoding="utf-8")
        executable.chmod(0o755)
        request = CliWorkerRequest(
            executable=str(executable),
            argv=("worker",),
            cwd=str(tmp_path),
            timeout_seconds=5,
        )

    result = run_cli_worker(request)
    contract = _contract(tmp_path)
    receipt = CodexCliExecutor._receipt(contract, _lease(tmp_path, contract), result)

    assert result.status is expected_status
    assert receipt.provider_calls == expected_count
    assert receipt.provider_attempt_count == expected_count


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
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("NEXUS_CODEX_BIN", str(executable))
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
