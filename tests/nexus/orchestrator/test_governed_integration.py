import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.executors.cli_worker import (
    CliWorkerResult,
    CliWorkerStatus,
    bounded_environment_receipt,
)
import nexus.orchestrator.governed_integration as governed_integration
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
            "action_set": [
                "INTEGRATION_STAGING",
                "APPLY_VERIFIED_INTEGRATION",
            ],
        },
        "external_acceptance": {"passed": True},
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

    with pytest.raises(RuntimeError, match="staging verifier failed"):
        ControlledIntegrationManager(integration_root=tmp_path / "integrations").integrate_task_state(
            state, integration_branch="nexus/integration/test"
        )

    assert _git(repo, "rev-parse", "nexus/integration/test") == base
    assert not (tmp_path / "integrations" / "integration-task").exists()
