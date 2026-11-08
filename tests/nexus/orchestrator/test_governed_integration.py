import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import nexus.orchestrator.governed_integration as governed_integration
from nexus.executors.cli_worker import (
    CliWorkerResult,
    CliWorkerStatus,
    bounded_environment_receipt,
)
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
)


def _verifier_evidence(
    executable: Path,
    command: str,
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    bounded_env = env or {"PYTHONDONTWRITEBYTECODE": "1"}
    return {
        "command": command,
        "status": "COMPLETED",
        "exit_code": 0,
        "executable_identity": str(executable),
        "argv": argv,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "env": bounded_environment_receipt(bounded_env),
        "timed_out": False,
        "process_group_killed": False,
    }


def _python3_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "python3"
    executable.symlink_to(Path(sys.executable))
    return executable


def test_staging_verifier_binds_persisted_executable_identity(tmp_path):
    executable = _python3_executable(tmp_path)
    command = "python3 -c 'print(\"integration-pass\")'"
    state = {
        "verified_receipt": {"verifier_evidence": [
            _verifier_evidence(
                executable,
                command,
                ["-c", 'print("integration-pass")'],
            )
        ]},
    }
    admitted = ControlledIntegrationManager._admitted_commands(state, {"verifier_commands": [command]})
    assert admitted == ((str(executable), ("-c", 'print("integration-pass")')),)


def test_staging_verifier_rejects_executable_sha_drift_before_run(tmp_path):
    command = "python3 -c 'print(1)'"
    evidence = _verifier_evidence(
        _python3_executable(tmp_path), command, ["-c", "print(1)"]
    )
    evidence["executable_sha256"] = "0" * 64
    state = {"verified_receipt": {"verifier_evidence": [evidence]}}
    with pytest.raises(RuntimeError, match="SHA drift"):
        ControlledIntegrationManager._admitted_commands(state, {"verifier_commands": [command]})


def test_staging_verifier_preserves_bounded_env_prefix(tmp_path):
    executable = _python3_executable(tmp_path)
    command = "PYTHONDONTWRITEBYTECODE=1 python3 -c 'print(1)'"
    state = {"verified_receipt": {"verifier_evidence": [
        _verifier_evidence(executable, command, ["-c", "print(1)"])
    ]}}

    manifest = ControlledIntegrationManager._admitted_manifest(
        state,
        {"verifier_commands": [command]},
    )

    assert manifest[0]["executable_identity"] == str(executable)
    assert manifest[0]["argv"] == ["-c", "print(1)"]
    assert manifest[0]["env"] == {"PYTHONDONTWRITEBYTECODE": "1"}


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda evidence: evidence.update(command="python3 -c 'print(2)'"), "command mismatch"),
        (lambda evidence: evidence.update(argv=["-c", "print(2)"]), "argv mismatch"),
        (lambda evidence: evidence.update(executable_identity="python3"), "identity is invalid"),
        (lambda evidence: evidence.update(status="TIMED_OUT"), "not successful"),
        (lambda evidence: evidence.update(exit_code=1), "not successful"),
        (lambda evidence: evidence.update(env=[]), "environment receipt mismatch"),
    ],
)
def test_staging_verifier_identity_tamper_fails_closed(tmp_path, tamper, message):
    command = "python3 -c 'print(1)'"
    evidence = _verifier_evidence(
        _python3_executable(tmp_path), command, ["-c", "print(1)"]
    )
    tamper(evidence)

    with pytest.raises(RuntimeError, match=message):
        ControlledIntegrationManager._admitted_manifest(
            {"verified_receipt": {"verifier_evidence": [evidence]}},
            {"verifier_commands": [command]},
        )


def test_staging_verifier_rejects_reordered_or_injected_commands(tmp_path):
    executable = _python3_executable(tmp_path)
    first = "python3 -c 'print(1)'"
    second = "python3 -c 'print(2)'"
    reversed_evidence = [
        _verifier_evidence(executable, second, ["-c", "print(2)"]),
        _verifier_evidence(executable, first, ["-c", "print(1)"]),
    ]
    with pytest.raises(RuntimeError, match="command mismatch"):
        ControlledIntegrationManager._admitted_manifest(
            {"verified_receipt": {"verifier_evidence": reversed_evidence}},
            {"verifier_commands": [first, second]},
        )
    with pytest.raises(RuntimeError, match="not admitted"):
        ControlledIntegrationManager._admitted_manifest(
            {"verified_receipt": {"verifier_evidence": [
                _verifier_evidence(executable, "python3 -m pytest; touch pwned", [])
            ]}},
            {"verifier_commands": ["python3 -m pytest; touch pwned"]},
        )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=repo, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _marker_program(tmp_path: Path, *, process_filter: bool = False) -> tuple[Path, Path]:
    marker = tmp_path / "PROGRAM_RAN"
    program = tmp_path / "marker_filter.py"
    script = "import pathlib, sys\npathlib.Path(sys.argv[1]).touch()\n"
    if process_filter:
        script += "sys.exit(1)\n"
    script += "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    program.write_text(script, encoding="utf-8")
    return marker, program


def _install_conditional_filter(repo: Path, tmp_path: Path, condition: str, pattern: str):
    marker, program = _marker_program(tmp_path)
    included_config = tmp_path / "conditional-filter.config"
    included_config.write_text(
        f'[filter "x"]\n\tsmudge = {sys.executable} {program} {marker}\n',
        encoding="utf-8",
    )
    (repo / ".git" / "info" / "attributes").write_text("* filter=x\n", encoding="utf-8")
    _git(repo, "config", f"includeIf.{condition}:{pattern}.path", str(included_config))
    return marker


def _authorized_verifier_state(tmp_path: Path):
    repo = tmp_path / "authorized-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    branch = "nexus/integration/test"
    _git(repo, "branch", branch, base)
    _git(repo, "checkout", "-b", "candidate")
    (repo / "candidate.txt").write_text("candidate\n")
    _git(repo, "add", "candidate.txt")
    _git(repo, "commit", "-m", "candidate")
    candidate = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")

    executable_dir = tmp_path / "admitted-bin"
    executable_dir.mkdir()
    executable = executable_dir / "python3"
    executable.symlink_to(Path(sys.executable))
    command = (
        "PYTHONDONTWRITEBYTECODE=1 python3 -c "
        "'from pathlib import Path; Path(\"verifier-ran\").write_text(\"ok\")'"
    )
    evidence = _verifier_evidence(
        executable,
        command,
        [
            "-c",
            'from pathlib import Path; Path("verifier-ran").write_text("ok")',
        ],
    )
    state = {
        "task_id": "integration-identity",
        "contract": {
            "task_id": "integration-identity",
            "controller_repo_root": str(repo),
            "verifier_commands": [command],
        },
        "promotion_packet": {"candidate_commit_sha": candidate},
        "integration_authorization": {
            "expected_canonical_head": base,
            "canonical_branch": branch,
            "canonical_root": str(repo),
            "cleanup_requested": False,
            "acceptance_receipt_hash": "9" * 64,
            "reviewer_id": "reviewer-1",
            "action_set": [
                "INTEGRATION_STAGING",
                "APPLY_VERIFIED_INTEGRATION",
            ],
        },
        "external_acceptance": _bound_acceptance("integration-identity", candidate),
        "verified_receipt": {"verifier_evidence": [evidence]},
        "lease": {"target_branch": "candidate"},
    }
    state["integration_verifier_manifest"] = list(
        ControlledIntegrationManager._admitted_manifest(state, state["contract"])
    )
    return repo, base, candidate, branch, executable, state


def test_authorized_integration_executes_admitted_identity_without_path_fallback(
    tmp_path: Path,
    monkeypatch,
):
    repo, base, _, branch, executable, state = _authorized_verifier_state(tmp_path)
    calls = []
    actual_runner = governed_integration.run_cli_worker

    def record(request):
        calls.append(request)
        return actual_runner(request)

    monkeypatch.setattr(governed_integration, "run_cli_worker", record)
    monkeypatch.setenv("PATH", "/usr/bin")
    receipt = ControlledIntegrationManager(
        integration_root=tmp_path / "integrations"
    ).integrate_authorized_task_state(
        state,
        integration_branch=branch,
        staging_root=tmp_path / "staging",
        apply=False,
    )

    assert receipt.staging_verified is True
    assert receipt.merge_performed is False
    assert _git(repo, "rev-parse", branch) == base
    assert len(calls) == 1
    assert calls[0].executable == str(executable)
    assert calls[0].env == {"PYTHONDONTWRITEBYTECODE": "1"}


def test_authorized_integration_rejects_identity_drift_before_staging(
    tmp_path: Path,
):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    state["verified_receipt"]["verifier_evidence"][0]["executable_sha256"] = "0" * 64

    with pytest.raises(RuntimeError, match="SHA drift"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not (tmp_path / "staging" / "integration-identity").exists()
    assert _git(repo, "rev-parse", branch) == base


def test_authorized_integration_rejects_persisted_manifest_drift_before_staging(
    tmp_path: Path,
):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    state["integration_verifier_manifest"][0]["argv"] = ["--version"]

    with pytest.raises(RuntimeError, match="manifest binding mismatch"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not (tmp_path / "staging" / "integration-identity").exists()
    assert _git(repo, "rev-parse", branch) == base


def test_authorized_integration_rejects_expired_authorization_before_staging(
    tmp_path: Path,
):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    state["integration_authorization"]["expires_at"] = "2000-01-01T00:00:00+00:00"

    with pytest.raises(RuntimeError, match="authorization expired"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    # Mutation Sentinel: prove neither staging worktree nor git branch mutation was reached
    assert not (tmp_path / "staging" / "integration-identity").exists()
    assert _git(repo, "rev-parse", branch) == base


def test_staging_verifier_failure_exposes_digests_not_raw_output(
    tmp_path: Path,
    monkeypatch,
):
    repo, base, _, branch, executable, state = _authorized_verifier_state(tmp_path)
    stdout = b"provider-secret-in-stdout"
    stderr = b"provider-secret-in-stderr"

    def fail(request):
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=str(executable),
            executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
            argv=request.argv,
            cwd=request.cwd,
            exit_code=7,
            stdout=stdout,
            stderr=stderr,
            wall_time_ms=1,
            process_group_id=1,
            env=bounded_environment_receipt(request.env),
        )

    monkeypatch.setattr(governed_integration, "run_cli_worker", fail)
    with pytest.raises(IntegrationExecutionError) as caught:
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    message = str(caught.value)
    assert stdout.decode() not in message
    assert stderr.decode() not in message
    assert hashlib.sha256(stdout).hexdigest() in message
    assert hashlib.sha256(stderr).hexdigest() in message
    assert caught.value.merge_performed is False
    assert _git(repo, "rev-parse", branch) == base


def _bound_acceptance(task_id, candidate):
    return {
        "schema": "nexus.external_acceptance_receipt.v1",
        "task_id": task_id,
        "attempt_id": "attempt-1",
        "candidate_commit": candidate,
        "receipt_hash": "9" * 64,
        "reviewer_id": "reviewer-1",
        "passed": True,
        "verifier_artifact": "artifact-1",
    }


def _bound_grant(task_id, action="CANDIDATE_APPROVE"):
    return {
        "schema": "nexus.approval.v2",
        "approval_id": "grant",
        "approved_by": "owner",
        "approval_scope": "ALLOW_ACTION_ONCE",
        "bound_task_id": task_id,
        "bound_action_type": action,
        "consumed_at": "2026-10-12T00:00:00+00:00",
    }


def _candidate_state(repo: Path, base: str, candidate: str, tree: str):
    executable = Path(sys.executable)
    command = f"{executable} -c 'print(\"integration-pass\")'"
    state = {
        "task_id": "integration-task",
        "status": "CANDIDATE_COMMITTED",
        "contract": {
            "task_id": "integration-task",
            "controller_repo_root": str(repo),
            "target_base_revision": base,
            "verifier_commands": [command],
        },
        "lease": {"target_branch": "nexus/task/integration-task"},
        "promotion_packet": {
            "promotion_status": "PENDING_HUMAN_APPROVAL",
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": tree,
            "candidate_state_hash": "a" * 64,
            "verified_receipt_hash": "b" * 64,
        },
        "promotion_status": "APPROVED",
        "approved_binding": {
            "candidate_commit_sha": candidate,
            "candidate_tree_sha": tree,
            "candidate_state_hash": "a" * 64,
            "verified_receipt_hash": "b" * 64,
        },
        "verified_receipt": {"verifier_evidence": [
            _verifier_evidence(
                executable,
                command,
                ["-c", 'print("integration-pass")'],
            )
        ]},
    }
    state["integration_verifier_manifest"] = list(
        ControlledIntegrationManager._admitted_manifest(state, state["contract"])
    )
    state["verified_receipt"]["verified"] = True
    state["approved_binding"]["approval_grant"] = _bound_grant("integration-task")
    state["external_acceptance"] = _bound_acceptance("integration-task", candidate)
    return _bind_verified_receipt(state)


def _bind_verified_receipt(state):
    receipt_hash = hashlib.sha256(
        json.dumps(
            state["verified_receipt"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    state["promotion_packet"]["verified_receipt_hash"] = receipt_hash
    state["approved_binding"]["verified_receipt_hash"] = receipt_hash
    return state


def test_controlled_integration_merges_only_to_nexus_integration(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")

    receipt = ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
        _candidate_state(repo, base, candidate, tree)
    )

    assert receipt.integration_branch == "nexus/integration"
    assert receipt.merge_performed is True
    assert receipt.push_performed is False
    assert _git(repo, "rev-parse", "nexus/integration") == receipt.integration_commit_sha
    assert _git(repo, "rev-parse", "main") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()


def test_controlled_integration_rejects_protected_branch(tmp_path):
    manager = ControlledIntegrationManager(integration_root=tmp_path / "integrations")

    with pytest.raises(ValueError, match="protected"):
        manager._validate_branch("main")


def test_controlled_integration_uses_durable_ref_for_detached_retry(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration/test", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", "--detach", str(target), base)
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    candidate_ref = f"refs/nexus-candidates/integration-task/{candidate}"
    _git(repo, "update-ref", candidate_ref, candidate)
    state = _candidate_state(repo, base, candidate, tree)
    state["lease"]["target_detached"] = True
    state["candidate_ref"] = candidate_ref

    receipt = ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
        state, integration_branch="nexus/integration/test"
    )

    assert receipt.source_branch == candidate_ref
    assert _git(repo, "rev-parse", "nexus/integration/test") == receipt.integration_commit_sha


def test_controlled_integration_requires_exact_approved_binding(tmp_path):
    manager = ControlledIntegrationManager(integration_root=tmp_path / "integrations")
    state = {"status": "CANDIDATE_COMMITTED", "promotion_status": "APPROVED"}

    with pytest.raises(RuntimeError, match="approved binding"):
        manager.integrate_task_state(state)


def test_controlled_integration_rolls_back_failed_verifier(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration/test", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    state = _candidate_state(repo, base, candidate, tree)
    executable = Path(sys.executable)
    command = f"{executable} -c 'raise SystemExit(1)'"
    state["contract"]["verifier_commands"] = [command]
    state["verified_receipt"]["verifier_evidence"] = [
        _verifier_evidence(executable, command, ["-c", "raise SystemExit(1)"])
    ]
    state["integration_verifier_manifest"] = list(
        ControlledIntegrationManager._admitted_manifest(state, state["contract"])
    )
    _bind_verified_receipt(state)

    with pytest.raises(RuntimeError, match="staging verifier failed"):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state, integration_branch="nexus/integration/test"
        )

    assert _git(repo, "rev-parse", "nexus/integration/test") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()


def _authorized_candidate_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    return repo, base, _candidate_state(repo, base, candidate, tree)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda state: state.pop("external_acceptance"), "external acceptance"),
        (lambda state: state["approved_binding"].pop("approval_grant"), "consumed approval grant"),
        (lambda state: state["verified_receipt"].update(verified=False), "verified candidate receipt"),
        (
            lambda state: state["verified_receipt"].update(extra="tampered"),
            "verified receipt hash",
        ),
    ],
)
def test_controlled_integration_requires_authority_at_sink(tmp_path, tamper, message):
    repo, base, state = _authorized_candidate_repo(tmp_path)
    tamper(state)

    with pytest.raises(RuntimeError, match=message):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state
        )

    assert _git(repo, "rev-parse", "nexus/integration") == base


def _assert_sink_rejects(tmp_path, mutate, message):
    repo, base, state = _authorized_candidate_repo(tmp_path)
    mutate(state)
    with pytest.raises(RuntimeError, match=message):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state)
    assert _git(repo, "rev-parse", "nexus/integration") == base


def test_sink_rejects_acceptance_for_another_task(tmp_path):
    def mutate(state):
        state["external_acceptance"]["task_id"] = "other-task"

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_sink_rejects_acceptance_for_another_candidate(tmp_path):
    def mutate(state):
        state["external_acceptance"]["candidate_commit"] = "0" * 40

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_sink_rejects_acceptance_without_receipt_hash(tmp_path):
    def mutate(state):
        state["external_acceptance"] = {"passed": True}

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_sink_rejects_identityless_grant_and_wrong_task_acceptance(tmp_path):
    def mutate(state):
        state["external_acceptance"] = {
            "passed": True,
            "task_id": "other-task",
            "candidate_commit": "0" * 40,
        }
        state["approved_binding"]["approval_grant"] = {"consumed_at": "x"}

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_sink_rejects_grant_without_approver(tmp_path):
    def mutate(state):
        state["approved_binding"]["approval_grant"].pop("approved_by")

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_rejects_shape_only_consumed_grant(tmp_path):
    def mutate(state):
        state["approved_binding"]["approval_grant"] = {"consumed_at": "x"}

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_rejects_grant_bound_to_another_task(tmp_path):
    def mutate(state):
        state["approved_binding"]["approval_grant"]["bound_task_id"] = "other-task"

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_rejects_grant_bound_to_another_action(tmp_path):
    def mutate(state):
        state["approved_binding"]["approval_grant"]["bound_action_type"] = "CANDIDATE_INTEGRATE"

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_integration_grant_must_bind_integrate_action(tmp_path):
    def mutate(state):
        state["integration_approval_grant"] = _bound_grant("integration-task", "CANDIDATE_APPROVE")

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_accepts_fully_bound_flow_with_integrate_grant(tmp_path):
    repo, base, state = _authorized_candidate_repo(tmp_path)
    state["integration_approval_grant"] = _bound_grant("integration-task", "CANDIDATE_INTEGRATE")
    receipt = ControlledIntegrationManager(
        integration_root=tmp_path / "integrations"
    ).integrate_task_state(state)
    assert receipt.verifier_passed
    assert _git(repo, "rev-parse", "nexus/integration") != base


def test_authorized_integration_rejects_acceptance_not_bound_to_candidate(tmp_path):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    state["external_acceptance"]["candidate_commit"] = "0" * 40
    with pytest.raises(RuntimeError, match="external acceptance is not bound"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state, integration_branch=branch, staging_root=tmp_path / "staging"
        )
    assert _git(repo, "rev-parse", branch) == base


def test_authorized_integration_rejects_acceptance_for_another_task(tmp_path):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    state["external_acceptance"]["task_id"] = "other-task"
    with pytest.raises(RuntimeError, match="external acceptance is not bound"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state, integration_branch=branch, staging_root=tmp_path / "staging"
        )
    assert _git(repo, "rev-parse", branch) == base


def test_sink_rejects_grant_without_attempt_when_state_has_attempt(tmp_path):
    def mutate(state):
        state["attempt_id"] = "attempt-9"
        state["external_acceptance"]["attempt_id"] = "attempt-9"

    _assert_sink_rejects(tmp_path, mutate, "approval grant is not bound")


def test_sink_accepts_grant_with_matching_attempt(tmp_path):
    repo, base, state = _authorized_candidate_repo(tmp_path)
    state["attempt_id"] = "attempt-9"
    state["external_acceptance"]["attempt_id"] = "attempt-9"
    state["approved_binding"]["approval_grant"]["bound_attempt_id"] = "attempt-9"
    receipt = ControlledIntegrationManager(
        integration_root=tmp_path / "integrations"
    ).integrate_task_state(state)
    assert receipt.verifier_passed


@pytest.mark.parametrize("drop", ["schema", "reviewer_id", "verifier_artifact"])
def test_sink_rejects_acceptance_failing_receipt_model(tmp_path, drop):
    def mutate(state):
        state["external_acceptance"].pop(drop)

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_sink_rejects_acceptance_with_malformed_receipt_hash(tmp_path):
    def mutate(state):
        state["external_acceptance"]["receipt_hash"] = "not-a-hash"

    _assert_sink_rejects(tmp_path, mutate, "external acceptance is not bound")


def test_competition_integration_requires_admitted_verifier(tmp_path):
    repo, base, state = _authorized_candidate_repo(tmp_path)
    state["contract"]["verifier_commands"] = []
    state["integration_verifier_manifest"] = []

    with pytest.raises(RuntimeError, match="at least one admitted verifier"):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state
        )

    assert _git(repo, "rev-parse", "nexus/integration") == base


def test_controlled_integration_refuses_a_verifier_that_writes_a_replacement_ref(tmp_path):
    """The compatibility path runs every git call sanitised and refuses a replacement ref
    left by a verifier, as the authorized path does (#3226)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration/test", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "change.txt").write_text("candidate\n")
    _git(target, "add", "change.txt")
    _git(target, "commit", "-m", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    state = _candidate_state(repo, base, candidate, tree)
    script = tmp_path / "replace_head.py"
    script.write_text(
        "import subprocess\n"
        "def g(*a, inp=None):\n"
        "    return subprocess.run(['git', *a], check=True, capture_output=True, text=True,"
        " input=inp).stdout.strip()\n"
        "head = g('rev-parse', 'HEAD')\n"
        "blob = g('hash-object', '-w', '--stdin', inp='other\\n')\n"
        "tree = g('mktree', inp='100644 blob ' + blob + '\\tREADME\\n')\n"
        "g('replace', head, g('commit-tree', tree, '-m', 'other', inp=''))\n",
        encoding="utf-8",
    )
    executable = Path(sys.executable)
    command = f"{executable} {script}"
    state["contract"]["verifier_commands"] = [command]
    state["verified_receipt"]["verifier_evidence"] = [
        _verifier_evidence(executable, command, [str(script)])
    ]
    state["integration_verifier_manifest"] = list(
        ControlledIntegrationManager._admitted_manifest(state, state["contract"])
    )
    _bind_verified_receipt(state)

    with pytest.raises(RuntimeError, match="carries replacement refs"):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state, integration_branch="nexus/integration/test"
        )

    assert _git(repo, "rev-parse", "nexus/integration/test") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()


def _legacy_driver_repo(tmp_path, monkeypatch):
    """Integration branch and candidate edit different lines of README, so the
    compatibility path runs a real content merge (#3383)."""
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for name in ("GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_ATTR_SOURCE"):
        monkeypatch.delenv(name, raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("a\nb\nc\nd\ne\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "branch", "nexus/integration/test", base)
    _git(repo, "branch", "nexus/task/integration-task", base)
    head_side = tmp_path / "head-side"
    _git(repo, "worktree", "add", str(head_side), "nexus/integration/test")
    (head_side / "README").write_text("a\nb\nc\nd\nHEAD\n")
    _git(head_side, "commit", "-am", "integration branch edits README")
    _git(repo, "worktree", "remove", str(head_side))
    target = tmp_path / "target"
    _git(repo, "worktree", "add", str(target), "nexus/task/integration-task")
    (target / "README").write_text("a\nCAND\nc\nd\ne\n")
    _git(target, "commit", "-am", "candidate")
    candidate = _git(target, "rev-parse", "HEAD")
    tree = _git(target, "rev-parse", "HEAD^{tree}")
    return repo, _candidate_state(repo, base, candidate, tree)


def _plant_legacy_driver(tmp_path, repo):
    marker = tmp_path / "DRIVER_RAN"
    _git(repo, "config", "merge.poc.driver", f"touch {marker}")
    (repo / ".git" / "info" / "attributes").write_text("* merge=poc\n")
    return marker


def test_controlled_integration_refuses_a_custom_merge_driver_without_running_it(
    tmp_path, monkeypatch
):
    """The compatibility path refuses a configured merge driver before merging: the
    driver never runs and the integration branch stays put (#3383)."""
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    integration_head = _git(repo, "rev-parse", "nexus/integration/test")
    marker = _plant_legacy_driver(tmp_path, repo)

    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch="nexus/integration/test")

    assert not marker.exists()
    assert _git(repo, "rev-parse", "nexus/integration/test") == integration_head
    assert not (tmp_path / "integrations" / "integration-task").exists()


def test_controlled_integration_driver_planted_after_the_check_never_runs(tmp_path, monkeypatch):
    """#3383 check-then-use race on the compatibility path: a driver written right
    after the first driver check passes never runs, and the branch stays put."""
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    integration_head = _git(repo, "rev-parse", "nexus/integration/test")
    real_check = ControlledIntegrationManager._refuse_custom_merge_drivers.__func__
    planted: list = []

    def racing_check(cls, cwd):
        real_check(cls, cwd)
        if not planted:
            planted.append(_plant_legacy_driver(tmp_path, repo))

    monkeypatch.setattr(
        ControlledIntegrationManager, "_refuse_custom_merge_drivers", classmethod(racing_check)
    )
    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch="nexus/integration/test")

    assert planted and not planted[0].exists()
    assert _git(repo, "rev-parse", "nexus/integration/test") == integration_head
    assert not (tmp_path / "integrations" / "integration-task").exists()


def test_controlled_integration_merge_never_reads_controller_driver_config(tmp_path, monkeypatch):
    """#3383: with the refusal removed, the compatibility path still merges outside the
    Controller's config: the planted driver never runs and the built-in merge lands."""
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    integration_head = _git(repo, "rev-parse", "nexus/integration/test")
    candidate = state["promotion_packet"]["candidate_commit_sha"]
    marker = _plant_legacy_driver(tmp_path, repo)
    monkeypatch.setattr(
        ControlledIntegrationManager,
        "_refuse_custom_merge_drivers",
        classmethod(lambda cls, cwd: None),
    )

    receipt = ControlledIntegrationManager(
        integration_root=tmp_path / "integrations"
    ).integrate_task_state(state, integration_branch="nexus/integration/test")

    assert not marker.exists()
    merged = receipt.integration_commit_sha
    assert _git(repo, "rev-parse", "nexus/integration/test") == merged
    assert _git(repo, "rev-list", "--parents", "-n", "1", merged).split()[1:] == [
        integration_head,
        candidate,
    ]
    assert _git(repo, "show", f"{merged}:README") == "a\nCAND\nc\nd\nHEAD"


def _plant_config_hook(repo, marker, event="post-merge", name="pm"):
    _git(repo, "config", f"hook.{name}.event", event)
    _git(repo, "config", f"hook.{name}.command", f"touch {marker}")


def test_controlled_integration_refuses_config_hook_before_compat_merge(tmp_path, monkeypatch):
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    integration_head = _git(repo, "rev-parse", "nexus/integration/test")
    marker = tmp_path / "CONFIG_HOOK_RAN"
    _plant_config_hook(repo, marker)

    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch="nexus/integration/test")

    assert not marker.exists()
    assert _git(repo, "rev-parse", "nexus/integration/test") == integration_head


def test_authorized_integration_refuses_config_hook_before_apply_merge(tmp_path):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    _git(repo, "checkout", branch)
    marker = tmp_path / "CONFIG_HOOK_RAN"
    _plant_config_hook(repo, marker)

    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == base


def test_authorized_integration_refuses_hook_planted_before_apply_merge(tmp_path, monkeypatch):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    _git(repo, "checkout", branch)
    marker = tmp_path / "CONFIG_HOOK_RAN"
    real_check = ControlledIntegrationManager._require_sole_controller_checkout.__func__

    def plant_after_checkout_check(cls, controller_root, checked_branch):
        real_check(cls, controller_root, checked_branch)
        _plant_config_hook(repo, marker)

    monkeypatch.setattr(
        ControlledIntegrationManager,
        "_require_sole_controller_checkout",
        classmethod(plant_after_checkout_check),
    )

    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == base


@pytest.mark.parametrize("event", ["post-merge", "post-checkout", "reference-transaction", "post-index-change"])
@pytest.mark.parametrize("path", ["compat", "authorized"])
def test_integration_refuses_config_hook_events_before_controller_git_calls(
    tmp_path, monkeypatch, event, path
):
    marker = tmp_path / "CONFIG_HOOK_RAN"
    if path == "compat":
        repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
        branch = "nexus/integration/test"

        def call():
            return ControlledIntegrationManager(
                integration_root=tmp_path / "integrations"
            ).integrate_task_state(state, integration_branch=branch)
    else:
        repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
        _git(repo, "checkout", branch)

        def call():
            return ControlledIntegrationManager(
                integration_root=tmp_path / "integrations"
            ).integrate_authorized_task_state(
                state,
                integration_branch=branch,
                staging_root=tmp_path / "staging",
                apply=True,
            )
    original_head = _git(repo, "rev-parse", branch)
    _plant_config_hook(repo, marker, event)

    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        call()

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == original_head


def test_sanitised_git_disables_config_hook_without_refuser(tmp_path):
    repo = tmp_path / "hook-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    _git(repo, "branch", "hook-test")
    marker = tmp_path / "CONFIG_HOOK_RAN"
    _plant_config_hook(repo, marker, "post-checkout")

    target = tmp_path / "linked"
    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager._git(["worktree", "add", str(target), "hook-test"], repo)

    assert not marker.exists()
    assert not target.exists()


def test_sanitised_git_allows_repo_without_config_hooks(tmp_path):
    repo = tmp_path / "plain-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    result = ControlledIntegrationManager._run_sanitised_git(["status", "--porcelain"], repo)
    assert result.returncode == 0


def test_authorized_integration_pins_fsmonitor_off_for_controller_git_calls(tmp_path):
    repo, base, _candidate, branch, _executable, state = _authorized_verifier_state(tmp_path)
    _git(repo, "checkout", branch)
    marker = tmp_path / "FSMONITOR_RAN"
    program = tmp_path / "marker_fsmonitor.py"
    program.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).touch()\nsys.stdout.write('token\\n\\0')\n",
        encoding="utf-8",
    )
    _git(repo, "config", "core.fsmonitor", f"{sys.executable} {program} {marker}")

    receipt = ControlledIntegrationManager(
        integration_root=tmp_path / "integrations"
    ).integrate_authorized_task_state(
        state,
        integration_branch=branch,
        staging_root=tmp_path / "staging",
        apply=True,
    )

    assert not marker.exists()
    assert receipt.merge_performed
    assert _git(repo, "rev-parse", branch) == receipt.integration_commit_sha
    assert _git(repo, "rev-parse", "HEAD") == receipt.integration_commit_sha
    assert _git(repo, "rev-parse", base) == base


@pytest.mark.parametrize(
    ("filter_key", "attribute_source"),
    [
        ("smudge", "info"),
        ("process", "info"),
        ("smudge", "committed"),
    ],
    ids=["smudge-info-attributes", "process-info-attributes", "smudge-committed-attributes"],
)
def test_controlled_integration_refuses_config_filters_before_any_git_side_effect(
    tmp_path, monkeypatch, filter_key, attribute_source
):
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    branch = "nexus/integration/test"
    integration_head = _git(repo, "rev-parse", branch)
    marker, program = _marker_program(tmp_path, process_filter=filter_key == "process")
    _git(
        repo,
        "config",
        f"filter.x.{filter_key}",
        f"{sys.executable} {program} {marker}",
    )
    if attribute_source == "info":
        (repo / ".git" / "info" / "attributes").write_text("* filter=x\n")
    else:
        target = tmp_path / "target"
        (target / ".gitattributes").write_text("* filter=x\n")
        _git(target, "add", ".gitattributes")
        _git(target, "commit", "-m", "candidate selects configured filter")
        candidate = _git(target, "rev-parse", "HEAD")
        tree = _git(target, "rev-parse", "HEAD^{tree}")
        base = _git(repo, "rev-parse", branch)
        state = _candidate_state(repo, base, candidate, tree)
    worktrees_before = _git(repo, "worktree", "list", "--porcelain")

    with pytest.raises(RuntimeError, match="CONFIG_FILTER_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch=branch)

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == integration_head
    assert _git(repo, "worktree", "list", "--porcelain") == worktrees_before
    assert not (tmp_path / "integrations" / "integration-task").exists()


@pytest.mark.parametrize(
    ("condition", "pattern"),
    [
        ("gitdir", "**/.git/worktrees/**"),
        ("onbranch", "nexus/integration/**"),
    ],
    ids=["gitdir-new-worktree", "onbranch-integration-branch"],
)
def test_compat_integration_refuses_worktree_only_conditional_filter_before_worktree_add(
    tmp_path, monkeypatch, condition, pattern
):
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    branch = "nexus/integration/test"
    branch_head = _git(repo, "rev-parse", branch)
    refs_before = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    worktrees_before = _git(repo, "worktree", "list", "--porcelain")
    marker = _install_conditional_filter(repo, tmp_path, condition, pattern)

    with pytest.raises(RuntimeError, match="CONFIG_INCLUDE_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch=branch)

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == branch_head
    assert _git(repo, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    assert _git(repo, "worktree", "list", "--porcelain") == worktrees_before
    assert not (tmp_path / "integrations" / "integration-task").exists()


def test_authorized_integration_refuses_worktree_only_conditional_filter_before_worktree_add(
    tmp_path,
):
    repo, _base, _candidate, branch, _executable, state = _authorized_verifier_state(tmp_path)
    branch_head = _git(repo, "rev-parse", branch)
    refs_before = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    worktrees_before = _git(repo, "worktree", "list", "--porcelain")
    marker = _install_conditional_filter(repo, tmp_path, "gitdir", "**/.git/worktrees/**")

    with pytest.raises(RuntimeError, match="CONFIG_INCLUDE_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == branch_head
    assert _git(repo, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    assert _git(repo, "worktree", "list", "--porcelain") == worktrees_before
    assert not (tmp_path / "staging" / state["task_id"]).exists()


def test_authorized_integration_refuses_visible_config_filter_before_worktree_add(tmp_path):
    repo, _base, _candidate, branch, _executable, state = _authorized_verifier_state(tmp_path)
    branch_head = _git(repo, "rev-parse", branch)
    refs_before = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    worktrees_before = _git(repo, "worktree", "list", "--porcelain")
    marker, program = _marker_program(tmp_path)
    (repo / ".git" / "info" / "attributes").write_text("* filter=x\n", encoding="utf-8")
    _git(repo, "config", "filter.x.smudge", f"{sys.executable} {program} {marker}")

    with pytest.raises(RuntimeError, match="CONFIG_FILTER_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state,
            integration_branch=branch,
            staging_root=tmp_path / "staging",
            apply=True,
        )

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == branch_head
    assert _git(repo, "for-each-ref", "--format=%(refname) %(objectname)") == refs_before
    assert _git(repo, "worktree", "list", "--porcelain") == worktrees_before
    assert not (tmp_path / "staging" / state["task_id"]).exists()


@pytest.mark.parametrize("hook_name", ["PM", "a=b"])
@pytest.mark.parametrize("path", ["authorized", "compat"])
def test_config_hook_subsection_names_refused_before_first_worktree_status(
    tmp_path, monkeypatch, hook_name, path
):
    marker = tmp_path / "CONFIG_HOOK_RAN"
    if path == "authorized":
        repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
        _git(repo, "checkout", branch)
        def call():
            ControlledIntegrationManager(
                integration_root=tmp_path / "integrations"
            ).integrate_authorized_task_state(
                state, integration_branch=branch, staging_root=tmp_path / "staging", apply=True
            )
    else:
        repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
        branch = "nexus/integration/test"
        base = _git(repo, "rev-parse", branch)
        def call():
            ControlledIntegrationManager(
                integration_root=tmp_path / "integrations"
            ).integrate_task_state(state, integration_branch=branch)
    _plant_config_hook(repo, marker, "post-index-change", hook_name)

    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        call()

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == base


def test_separate_controller_refuses_hook_before_update_ref(tmp_path, monkeypatch):
    repo, base, _, branch, _, state = _authorized_verifier_state(tmp_path)
    controller = tmp_path / "separate-controller"
    _git(repo, "worktree", "add", "--detach", str(controller), "main")
    state["contract"]["controller_repo_root"] = str(controller)
    state["integration_authorization"]["canonical_root"] = str(controller)
    marker = tmp_path / "CONFIG_HOOK_RAN"
    original_status = ControlledIntegrationManager._git_status.__func__

    def plant_after_ancestry(cls, args, cwd):
        result = original_status(cls, args, cwd)
        if args[:2] == ["merge-base", "--is-ancestor"]:
            _plant_config_hook(repo, marker, "reference-transaction", "PM")
        return result

    monkeypatch.setattr(
        ControlledIntegrationManager, "_git_status", classmethod(plant_after_ancestry)
    )
    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state, integration_branch=branch, staging_root=tmp_path / "staging", apply=True
        )
    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == base


@pytest.mark.parametrize("path", ["compat", "authorized_staging", "separate_update_ref"])
def test_explicit_hook_refusal_precedes_protected_git_mutation(tmp_path, monkeypatch, path):
    events = []
    original_refuse = ControlledIntegrationManager._refuse_custom_merge_drivers.__func__
    original_git = ControlledIntegrationManager._git.__func__
    original_status = ControlledIntegrationManager._git_status.__func__

    def record_refusal(cls, cwd):
        events.append(("refusal", None))
        return original_refuse(cls, cwd)

    def record_git(cls, args, cwd):
        if args[:2] == ["worktree", "add"] or args[:2] == ["update-ref", "--no-deref"]:
            events.append(("command", tuple(args)))
        return original_git(cls, args, cwd)

    def record_status(cls, args, cwd):
        result = original_status(cls, args, cwd)
        if args[:2] == ["merge-base", "--is-ancestor"]:
            events.append(("ancestry", None))
        return result

    monkeypatch.setattr(
        ControlledIntegrationManager, "_refuse_custom_merge_drivers", classmethod(record_refusal)
    )
    monkeypatch.setattr(ControlledIntegrationManager, "_git", classmethod(record_git))
    monkeypatch.setattr(ControlledIntegrationManager, "_git_status", classmethod(record_status))

    if path == "compat":
        repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch="nexus/integration/test")
        command_name = "worktree add"
    else:
        repo, _, _, branch, _, state = _authorized_verifier_state(tmp_path)
        if path == "separate_update_ref":
            controller = tmp_path / "separate-controller"
            _git(repo, "worktree", "add", "--detach", str(controller), "main")
            state["contract"]["controller_repo_root"] = str(controller)
            state["integration_authorization"]["canonical_root"] = str(controller)
            command_name = "update-ref --no-deref"
        else:
            _git(repo, "checkout", branch)
            command_name = "worktree add --detach"
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_authorized_task_state(
            state, integration_branch=branch, staging_root=tmp_path / "staging", apply=True
        )

    command_event = next(
        index
        for index, event in enumerate(events)
        if event[0] == "command" and " ".join(event[1]).startswith(command_name)
    )
    prior_refusals = [index for index, event in enumerate(events[:command_event]) if event[0] == "refusal"]
    assert prior_refusals
    if path == "separate_update_ref":
        ancestry_event = max(index for index, event in enumerate(events) if event[0] == "ancestry")
        assert prior_refusals[-1] > ancestry_event


def test_compat_rechecks_hook_planted_after_merge_commit(tmp_path, monkeypatch):
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    branch = "nexus/integration/test"
    original_head = _git(repo, "rev-parse", branch)
    marker = tmp_path / "CONFIG_HOOK_RAN"
    real_merge = ControlledIntegrationManager._controller_merge_commit.__func__

    def plant_after_merge(cls, head, candidate, controller_root):
        merged = real_merge(cls, head, candidate, controller_root)
        _plant_config_hook(repo, marker, "post-checkout")
        return merged

    monkeypatch.setattr(
        ControlledIntegrationManager, "_controller_merge_commit", classmethod(plant_after_merge)
    )
    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch=branch)

    assert not marker.exists()
    assert _git(repo, "rev-parse", branch) == original_head


def test_compat_refusal_survives_dirty_worktree_cleanup_error(tmp_path, monkeypatch):
    repo, state = _legacy_driver_repo(tmp_path, monkeypatch)
    marker = tmp_path / "CONFIG_HOOK_RAN"
    real_merge = ControlledIntegrationManager._controller_merge_commit.__func__

    def dirty_and_plant(cls, head, candidate, controller_root):
        merged = real_merge(cls, head, candidate, controller_root)
        integration_path = tmp_path / "integrations" / "integration-task"
        (integration_path / "untracked-dirty").write_text("dirty\n")
        _plant_config_hook(repo, marker, "post-checkout")
        return merged

    monkeypatch.setattr(
        ControlledIntegrationManager, "_controller_merge_commit", classmethod(dirty_and_plant)
    )
    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager(
            integration_root=tmp_path / "integrations"
        ).integrate_task_state(state, integration_branch="nexus/integration/test")

    assert not marker.exists()


def test_sanitised_git_fails_closed_when_config_cannot_be_read(tmp_path, monkeypatch):
    """An unreadable repository config refuses every Controller git call (#3408)."""
    repo, _state = _legacy_driver_repo(tmp_path, monkeypatch)
    with (repo / ".git" / "config").open("a") as config:
        config.write("[broken\n")
    with pytest.raises(RuntimeError, match="git config could not be read"):
        ControlledIntegrationManager._git(["status", "--porcelain"], repo)


def test_sanitised_git_refuses_a_hook_key_without_a_value(tmp_path, monkeypatch):
    """A valueless ``hook.<name>.event`` key is listed without a newline and still refused."""
    repo, _state = _legacy_driver_repo(tmp_path, monkeypatch)
    with (repo / ".git" / "config").open("a") as config:
        config.write('[hook "PM"]\n\tevent\n')
    with pytest.raises(RuntimeError, match="CONFIG_HOOK_REFUSED"):
        ControlledIntegrationManager._git(["status", "--porcelain"], repo)
