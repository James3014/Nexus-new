import hashlib
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.executors.cli_worker import bounded_environment_receipt
from nexus.orchestrator.governed_integration import ControlledIntegrationManager
from nexus.orchestrator.target_integration_lifecycle import (
    TargetIntegrationLifecycle,
    _render_command,
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def status_hash(root: Path) -> str:
    return hashlib.sha256(git(root, "status", "--porcelain=v1", "--untracked-files=all").encode()).hexdigest()


def make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "canary")
    git(root, "config", "user.email", "canary@example.invalid")
    (root / "value.txt").write_text("base\n")
    git(root, "add", "value.txt")
    git(root, "commit", "-m", "base")
    base = git(root, "rev-parse", "HEAD")
    git(root, "branch", "candidate")
    git(root, "checkout", "candidate")
    (root / "value.txt").write_text("candidate\n")
    git(root, "commit", "-am", "candidate")
    candidate = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "main")
    git(root, "checkout", "-b", "nexus/integration/canary")
    return root, base, candidate


def acceptance(candidate: str) -> ExternalAcceptanceReceipt:
    return ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1", task_id="task-1",
        attempt_id="attempt-1", candidate_commit=candidate, receipt_hash="b" * 64,
        reviewer_id="reviewer-1", passed=True, verifier_artifact="artifact-1",
    )


def authorization(root: Path, base: str, candidate: str, receipt: ExternalAcceptanceReceipt) -> IntegrationAuthorizationEnvelope:
    return IntegrationAuthorizationEnvelope(
        schema="nexus.integration_authorization.v1", task_id="task-1",
        campaign_id="campaign", attempt_id="attempt-1", task_card_hash="c" * 64,
        candidate_commit=candidate, candidate_tree_sha=git(root, "rev-parse", f"{candidate}^{{tree}}"),
        candidate_state_hash="d" * 64, candidate_receipt_hash="e" * 64,
        acceptance_receipt_hash=receipt.receipt_hash, reviewer_id=receipt.reviewer_id,
        verifier_artifact_hash="f" * 64, canonical_root=str(root.resolve()),
        canonical_branch="nexus/integration/canary", expected_canonical_head=base,
        canonical_dirty_baseline=status_hash(root), integration_plan_hash="1" * 64,
        strategy="EPHEMERAL_WORKTREE_MERGE_THEN_APPLY", verification_commands_hash="2" * 64,
        post_apply_commands_hash="3" * 64, cleanup_target_id="target-1",
        cleanup_target_path=str(root / "target"), durable_ref="refs/nexus-candidate/task-1",
        rollback="retain target", cleanup_requested=True,
        action_set=("ACCEPT_DISPOSITION", "INTEGRATION_STAGING", "APPLY_VERIFIED_INTEGRATION", "POST_INTEGRATION_VERIFY", "CLEANUP_OWNED_TARGET"),
        issued_at="2026-08-02T00:00:00+00:00",
    )


def integrate(
    *, acceptance_receipt: ExternalAcceptanceReceipt, auth: IntegrationAuthorizationEnvelope,
    staging_root: str, apply: bool = False, verifier_commands=(), lifecycle_state=None,
    post_apply_commands=(),
):
    """Drive the live Git sink with an authorized task state (#2584 Phase-2 batch A).

    The compatibility adapter ``TargetIntegrationLifecycle.transactional_integration``
    that these canaries used to call had no production caller and was removed; the
    state below is the one it built, handed to the same sink the live
    ``SelfHostedTaskService.integrate_approved`` uses.
    """
    authorization_state = auth.to_dict()
    authorization_state["authorization_hash"] = auth.authorization_hash
    state = dict(lifecycle_state or {})
    state.update({
        "task_id": auth.task_id,
        "external_acceptance": acceptance_receipt.to_dict(),
        "integration_authorization": authorization_state,
        "post_apply_commands": [list(command) for command in post_apply_commands],
        "verifier_argv_commands": [list(command) for command in verifier_commands],
        "promotion_packet": {
            **dict(state.get("promotion_packet") or {}),
            "candidate_commit_sha": auth.candidate_commit,
        },
        "contract": {
            **dict(state.get("contract") or {}),
            "controller_repo_root": auth.canonical_root,
            "verifier_commands": [_render_command(command) for command in verifier_commands],
        },
    })
    return ControlledIntegrationManager(
        integration_root=auth.canonical_root
    ).integrate_authorized_task_state(
        state, integration_branch=auth.canonical_branch, staging_root=staging_root,
        apply=apply, post_apply_commands=post_apply_commands,
    )


def _verifier_lifecycle_state(tmp_path: Path, exit_code: int) -> tuple[tuple[str, ...], dict]:
    """Sealed verifier evidence + admitted manifest, as the Candidate receipt would carry (a9a8a531e)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_path.resolve()
    executable = tmp_path / "python3"
    executable.symlink_to(Path(sys.executable))
    argv = ["-c", f"exit({exit_code})"]
    command = " ".join(["python3", *argv])
    state = {"verified_receipt": {"verifier_evidence": [{
        "command": command, "status": "COMPLETED", "exit_code": 0,
        "executable_identity": str(executable), "argv": argv,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "env": bounded_environment_receipt({"PYTHONDONTWRITEBYTECODE": "1"}),
        "timed_out": False, "process_group_killed": False,
    }]}}
    manifest = ControlledIntegrationManager._admitted_manifest(state, {"verifier_commands": [command]})
    state["integration_verifier_manifest"] = [dict(item) for item in manifest]
    return ("python3", *argv), state


def test_real_git_staging_failure_and_success_do_not_fake_ancestry(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    failing_argv, failing_state = _verifier_lifecycle_state(tmp_path / "fail-ev", 1)
    with pytest.raises(RuntimeError, match="staging verifier failed"):
        integrate(
            staging_root=str(tmp_path / "failed-stage"),
            verifier_commands=(failing_argv,), lifecycle_state=failing_state,
            acceptance_receipt=receipt, auth=auth,
        )
    assert git(root, "rev-parse", "HEAD") == base
    assert not (tmp_path / "failed-stage" / "task-1").exists()

    good_argv, good_state = _verifier_lifecycle_state(tmp_path / "good-ev", 0)
    staged = integrate(
        staging_root=str(tmp_path / "good-stage"),
        verifier_commands=(good_argv,), lifecycle_state=good_state,
        acceptance_receipt=receipt, auth=auth,
    )
    assert staged.staging_commit_sha
    assert staged.merge_performed is False
    assert git(root, "rev-parse", "HEAD") == base


def test_real_git_canary_detects_canonical_drift_and_applies_verified_result(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    (root / "unrelated.txt").write_text("dirty\n")
    with pytest.raises(RuntimeError, match="canonical.*clean"):
        integrate(
            staging_root=str(tmp_path / "drift-stage"), apply=True,
            acceptance_receipt=receipt, auth=auth,
        )
    (root / "unrelated.txt").unlink()
    applied = integrate(
        staging_root=str(tmp_path / "apply-stage"), apply=True,
        acceptance_receipt=receipt, auth=auth,
    )
    assert applied.merge_performed is True
    assert git(root, "rev-parse", "HEAD") == applied.integration_commit_sha
    assert git(root, "merge-base", "--is-ancestor", candidate, git(root, "rev-parse", "HEAD")) == ""


def test_real_git_conflict_and_forged_cleanup_are_fail_closed(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    (root / "value.txt").write_text("canonical-conflict\n")
    git(root, "commit", "-am", "canonical conflicting change")
    drifted_head = git(root, "rev-parse", "HEAD")
    receipt = acceptance(candidate)
    auth = authorization(root, drifted_head, candidate, receipt)
    with pytest.raises(RuntimeError, match="git merge"):
        integrate(
            staging_root=str(tmp_path / "conflict-stage"), apply=True,
            acceptance_receipt=receipt, auth=auth,
        )
    assert git(root, "rev-parse", "HEAD") == drifted_head

    target = tmp_path / "owned-target"
    git(root, "worktree", "add", "--detach", str(target), drifted_head)
    forged = CleanupDecision(
        schema="nexus.target_cleanup_decision.v1", decision="ELIGIBLE",
        task_id="task-1", target_id="target-1",
    )
    result = TargetIntegrationLifecycle.cleanup_target(
        decision=forged, target_path=target, canonical_root=root, apply=True,
    )
    assert result["performed"] is False
    assert target.exists()


def _spaced_verifier_state(tmp_path: Path, expression: str) -> tuple[tuple[str, ...], dict]:
    """Sealed evidence for a verifier whose one argument contains spaces (#2307)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_path.resolve()
    executable = tmp_path / "python3"
    executable.symlink_to(Path(sys.executable))
    argv = ["-c", expression]
    command = shlex.join(["python3", *argv])
    state = {"verified_receipt": {"verifier_evidence": [{
        "command": command, "status": "COMPLETED", "exit_code": 0,
        "executable_identity": str(executable), "argv": argv,
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "env": bounded_environment_receipt({"PYTHONDONTWRITEBYTECODE": "1"}),
        "timed_out": False, "process_group_killed": False,
    }]}}
    manifest = ControlledIntegrationManager._admitted_manifest(state, {"verifier_commands": [command]})
    state["integration_verifier_manifest"] = [dict(item) for item in manifest]
    return ("python3", *argv), state


def test_verifier_argument_with_spaces_is_approved_when_it_matches_and_refused_otherwise(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    argv, state = _spaced_verifier_state(tmp_path / "match-ev", "assert 1 + 1 == 2")
    staged = integrate(
        staging_root=str(tmp_path / "match-stage"),
        verifier_commands=(argv,), lifecycle_state=state,
        acceptance_receipt=receipt, auth=auth,
    )
    assert staged.staging_commit_sha and staged.merge_performed is False
    # The approved argv is not the one the sealed evidence recorded: refuse.
    other_argv, _ = _spaced_verifier_state(tmp_path / "other-ev", "assert 1 + 1 == 3")
    with pytest.raises(RuntimeError, match="staging verifier (command|argv) mismatch"):
        integrate(
            staging_root=str(tmp_path / "mismatch-stage"),
            verifier_commands=(other_argv,), lifecycle_state=state,
            acceptance_receipt=receipt, auth=auth,
        )
    assert git(root, "rev-parse", "HEAD") == base


@pytest.mark.parametrize(
    "token",
    ["a#b", "#x", "&x", ";x", "a|b", "<in", "x>y", "", "a b", "it's", "\\", "$HOME", "*", "exit(1)", "a\"b"],
)
def test_rendered_verifier_command_round_trips_through_the_downstream_lexer(token: str):
    argv = ("-c", token)  # the token after -c is exempt from the char denylist
    _executable, parsed, _env = ControlledIntegrationManager._command_intent(
        _render_command(("python3", *argv))
    )
    assert parsed == argv
