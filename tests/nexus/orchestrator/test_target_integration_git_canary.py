import dataclasses
import hashlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nexus.contracts.target_integration_lifecycle import (
    CleanupDecision,
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.executors.cli_worker import bounded_environment_receipt
from nexus.orchestrator import governed_integration as governed_integration_module
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
)
from nexus.orchestrator.target_integration_lifecycle import (
    TargetIntegrationLifecycle,
    _render_command,
    post_apply_commands_hash,
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
    post_apply_commands=(), authorized_post_apply_hash=None,
):
    """Drive the live Git sink with an authorized task state (#2584 Phase-2 batch A).

    The compatibility adapter ``TargetIntegrationLifecycle.transactional_integration``
    that these canaries used to call had no production caller and was removed; the
    state below is the one it built, handed to the same sink the live
    ``SelfHostedTaskService.integrate_approved`` uses.  The authorization is bound
    to ``post_apply_commands`` unless ``authorized_post_apply_hash`` names another
    value (#3185).
    """
    auth = dataclasses.replace(
        auth,
        post_apply_commands_hash=(
            post_apply_commands_hash(post_apply_commands)
            if authorized_post_apply_hash is None
            else authorized_post_apply_hash
        ),
    )
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


# The applied commit is the staging merge result, recorded before any admitted
# verifier runs; the ref-update path only moves the branch forward (#3174).
_COMMIT_DURING_VERIFICATION = (
    "import subprocess; subprocess.run(['git', 'commit', '-q', '--allow-empty', "
    "'-m', 'made during verification'], check=True)"
)
_EDIT_DURING_VERIFICATION = "open('value.txt', 'a').write('changed during verification')"


def _shape_repo(tmp_path: Path, shape: str) -> tuple[Path, str, str]:
    """``ff-only``: Controller on the integration branch; ``ref-update``: on another branch."""
    root, base, candidate = make_repo(tmp_path)
    if shape == "ref-update":
        git(root, "checkout", "main")
    return root, base, candidate


def _integration_head(root: Path) -> str:
    return git(root, "rev-parse", "refs/heads/nexus/integration/canary")


@pytest.mark.parametrize("shape", ["ff-only", "ref-update"])
def test_a_staging_step_that_moves_head_is_refused_without_changing_the_branch(
    tmp_path: Path, shape: str
):
    root, base, candidate = _shape_repo(tmp_path, shape)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    argv, state = _spaced_verifier_state(tmp_path / "ev", _COMMIT_DURING_VERIFICATION)
    with pytest.raises(RuntimeError, match="staging HEAD moved during verification") as refused:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            verifier_commands=(argv,),
            lifecycle_state=state,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert refused.value.merge_performed is False
    assert _integration_head(root) == base
    assert not (tmp_path / "stage" / "task-1").exists()


@pytest.mark.parametrize("shape", ["ff-only", "ref-update"])
def test_a_staging_step_that_leaves_the_tree_dirty_is_refused(tmp_path: Path, shape: str):
    root, base, candidate = _shape_repo(tmp_path, shape)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    argv, state = _spaced_verifier_state(tmp_path / "ev", _EDIT_DURING_VERIFICATION)
    with pytest.raises(
        RuntimeError, match="staging worktree is dirty after verification"
    ) as refused:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            verifier_commands=(argv,),
            lifecycle_state=state,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert refused.value.merge_performed is False
    assert _integration_head(root) == base


@pytest.mark.parametrize("shape", ["ff-only", "ref-update"])
def test_a_clean_staging_run_applies_the_recorded_merge_result(tmp_path: Path, shape: str):
    root, base, candidate = _shape_repo(tmp_path, shape)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    argv, state = _spaced_verifier_state(tmp_path / "ev", "assert 1 + 1 == 2")
    applied = integrate(
        staging_root=str(tmp_path / "stage"),
        apply=True,
        verifier_commands=(argv,),
        lifecycle_state=state,
        acceptance_receipt=receipt,
        auth=auth,
    )
    head = _integration_head(root)
    assert applied.merge_performed is True
    assert applied.staging_commit_sha == applied.integration_commit_sha == head
    assert git(root, "rev-list", "--parents", "-n", "1", head).split()[1:] == [base, candidate]


def test_the_ref_update_apply_only_moves_the_branch_forward(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _base, candidate = make_repo(tmp_path)
    (root / "earlier.txt").write_text("earlier integrated work\n")
    git(root, "add", "earlier.txt")
    git(root, "commit", "-m", "earlier")
    head = _integration_head(root)
    git(root, "checkout", "main")
    receipt = acceptance(candidate)
    auth = authorization(root, head, candidate, receipt)
    real_git = ControlledIntegrationManager._git.__func__

    # Fault injection: the staging step yields a commit that is not a
    # descendant of the head, while the merge-shape probe still agrees.
    def git_without_descendant(cls, args, cwd):
        # The Controller computes the staging commit with commit-tree (#3186).
        if list(args[:1]) == ["commit-tree"]:
            return candidate
        if list(args[:2]) == ["rev-list", "--parents"]:
            return f"{args[-1]} {head} {candidate}"
        return real_git(cls, args, cwd)

    monkeypatch.setattr(ControlledIntegrationManager, "_git", classmethod(git_without_descendant))
    with pytest.raises(RuntimeError, match="does not descend from the head") as refused:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert refused.value.merge_performed is False
    assert _integration_head(root) == head


def test_an_unexpected_cleanup_error_after_apply_is_reported_as_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    real_git = ControlledIntegrationManager._git.__func__

    def git_with_cleanup_error(cls, args, cwd):
        if list(args[:2]) == ["worktree", "remove"]:
            raise OSError("cleanup unavailable")
        return real_git(cls, args, cwd)

    monkeypatch.setattr(ControlledIntegrationManager, "_git", classmethod(git_with_cleanup_error))
    with pytest.raises(IntegrationExecutionError) as reported:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert reported.value.merge_performed is True
    assert reported.value.stage == "POST_APPLY_CLEANUP"
    assert reported.value.integration_result_sha == _integration_head(root) != base


def test_a_candidate_already_on_the_branch_is_refused_as_producing_no_merge_result(tmp_path: Path):
    root, _base, candidate = make_repo(tmp_path)
    git(root, "merge", "--ff-only", candidate)
    receipt = acceptance(candidate)
    auth = authorization(root, candidate, candidate, receipt)
    with pytest.raises(RuntimeError, match="not the expected head merged with the candidate"):
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert _integration_head(root) == candidate


# A verifier that writes a replacement ref for the staging commit: every sha the
# integration records stays the same while a git call that honours replacement reads
# another tree under it (#3226).  With ``reset`` the staging tree is loaded from the
# replacement as well.
_REPLACE_DURING_VERIFICATION = (
    "import subprocess; "
    "g = lambda *a, inp=None: subprocess.run(['git', *a], check=True, capture_output=True, "
    "text=True, input=inp).stdout.strip(); "
    "head = g('rev-parse', 'HEAD'); "
    "parents = g('rev-list', '--parents', '-n', '1', head).split()[1:]; "
    "blob = g('hash-object', '-w', '--stdin', inp='other content\\n'); "
    "tree = g('mktree', inp='100644 blob ' + blob + '\\tvalue.txt\\n'); "
    "other = g('commit-tree', tree, '-p', parents[0], '-p', parents[1], '-m', 'other', inp=''); "
    "g('replace', head, other)"
)
_REPLACE_AND_RESET_DURING_VERIFICATION = (
    _REPLACE_DURING_VERIFICATION + "; g('reset', '--hard', 'HEAD')"
)


@pytest.mark.parametrize("shape", ["ff-only", "ref-update"])
@pytest.mark.parametrize(
    "expression",
    [_REPLACE_DURING_VERIFICATION, _REPLACE_AND_RESET_DURING_VERIFICATION],
    ids=["replace", "replace-and-reset"],
)
def test_a_staging_step_that_writes_a_replacement_ref_is_refused_without_changing_the_branch(
    tmp_path: Path, shape: str, expression: str
):
    root, base, candidate = _shape_repo(tmp_path, shape)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    argv, state = _spaced_verifier_state(tmp_path / "ev", expression)
    with pytest.raises(RuntimeError, match="carries replacement refs") as refused:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            verifier_commands=(argv,),
            lifecycle_state=state,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert refused.value.merge_performed is False
    assert _integration_head(root) == base
    assert git(root, "show", f"{base}:value.txt") == "base"
    assert not (tmp_path / "stage" / "task-1").exists()


def test_controller_git_calls_read_objects_as_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The Controller's git environment ignores replacement refs, so a sha names one tree."""
    root, base, _candidate = make_repo(tmp_path)
    seen: dict[str, Any] = {}
    real_run = subprocess.run

    def recording_run(cmd, **kwargs):
        seen["env"] = kwargs["env"]
        return real_run(cmd, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(governed_integration_module.subprocess, "run", recording_run)
        assert ControlledIntegrationManager._git(["rev-parse", "HEAD"], root)
    assert seen["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
    # Behaviour, not just the variable: a replacement for the base commit is not followed.
    git(root, "checkout", "-q", "--detach", base)
    (root / "value.txt").write_text("other\n")
    git(root, "commit", "-aqm", "other")
    git(root, "replace", base, git(root, "rev-parse", "HEAD"))
    assert git(root, "show", f"{base}:value.txt") == "other"
    assert ControlledIntegrationManager._git(["show", f"{base}:value.txt"], root) == "base"


# A post-apply command that writes a replacement ref for the applied commit (#3226).
_REPLACE_AFTER_APPLY = (
    "import subprocess; "
    "g = lambda *a, inp=None: subprocess.run(['git', *a], check=True, capture_output=True, "
    "text=True, input=inp).stdout.strip(); "
    "head = g('rev-parse', 'HEAD'); "
    "blob = g('hash-object', '-w', '--stdin', inp='other content\\n'); "
    "tree = g('mktree', inp='100644 blob ' + blob + '\\tvalue.txt\\n'); "
    "other = g('commit-tree', tree, '-m', 'other', inp=''); "
    "g('replace', head, other)"
)


def test_a_post_apply_command_that_writes_a_replacement_ref_is_refused(tmp_path: Path):
    """The post-apply worktree shares the Controller's ref store: a replacement ref written
    there is caught before the receipt, not only one written during staging."""
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    with pytest.raises(RuntimeError, match="carries replacement refs after post-apply"):
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            post_apply_commands=((sys.executable, "-c", _REPLACE_AFTER_APPLY),),
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert git(root, "for-each-ref", "refs/replace/")  # what the command left behind


def test_a_branch_moved_during_cleanup_is_reported_instead_of_receipted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """#3228 V1: the last read of the branch is compared to the applied commit, so a move in
    the cleanup window (a straggler of a post-apply command, a concurrent writer) is a
    classified failure, not a receipt naming an unverified commit."""
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    auth = authorization(root, base, candidate, receipt)
    real_git = ControlledIntegrationManager._git.__func__
    moved: dict[str, str] = {}

    def git_moving_the_branch_during_cleanup(cls, args, cwd):
        result = real_git(cls, args, cwd)
        if list(args[:2]) == ["worktree", "remove"] and not moved:
            git(root, "commit", "--allow-empty", "-m", "moved after apply")
            moved["head"] = _integration_head(root)
        return result

    monkeypatch.setattr(
        ControlledIntegrationManager, "_git", classmethod(git_moving_the_branch_during_cleanup)
    )
    with pytest.raises(IntegrationExecutionError, match="moved after apply") as reported:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert reported.value.merge_performed is True
    assert reported.value.stage == "POST_APPLY_VERIFICATION"
    assert reported.value.branch_head_after == moved["head"]
    assert reported.value.staging_commit_sha not in (None, moved["head"])


def test_the_controller_computes_the_staging_commit_before_any_staging_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """#3186: the sha the receipt binds is a merge the Controller builds from objects
    (head and candidate as parents, the same tree a ``merge`` gives) before the staging
    worktree exists, and no merge runs inside the staging worktree."""
    root, base, candidate = make_repo(tmp_path)
    (root / "other.txt").write_text("head side\n")
    git(root, "add", "other.txt")
    git(root, "commit", "-m", "head side change")
    head = git(root, "rev-parse", "HEAD")
    receipt = acceptance(candidate)
    auth = authorization(root, head, candidate, receipt)
    real_run = ControlledIntegrationManager._run_sanitised_git
    calls: list[tuple[list[str], Path]] = []

    def recording_run(args, cwd):
        calls.append((list(args), Path(cwd)))
        return real_run(args, cwd)

    monkeypatch.setattr(
        ControlledIntegrationManager, "_run_sanitised_git", staticmethod(recording_run)
    )
    stage = tmp_path / "stage"
    staged = integrate(staging_root=str(stage), acceptance_receipt=receipt, auth=auth)

    sha = staged.staging_commit_sha
    assert git(root, "rev-list", "--parents", "-n", "1", sha).split()[1:] == [head, candidate]
    reference = tmp_path / "reference"
    git(root, "worktree", "add", "--detach", str(reference), head)
    git(reference, "merge", "--no-ff", "--no-edit", candidate)
    assert git(root, "rev-parse", f"{sha}^{{tree}}") == git(reference, "rev-parse", "HEAD^{tree}")
    commit_tree = next(i for i, (args, _) in enumerate(calls) if args[0] == "commit-tree")
    in_stage = [
        i for i, (_, cwd) in enumerate(calls) if cwd.resolve().is_relative_to(stage.resolve())
    ]
    assert in_stage and commit_tree < min(in_stage)
    assert calls[commit_tree][1].resolve() == root.resolve()
    assert not any(args[0] == "merge" for args, cwd in calls if cwd.resolve() != root.resolve())


def test_a_candidate_already_in_the_head_is_refused_without_a_merge_commit(tmp_path: Path):
    """#3186: ``commit-tree`` would record an empty merge where ``merge --no-ff`` made none."""
    root, _base, candidate = make_repo(tmp_path)
    git(root, "merge", "--no-ff", "--no-edit", candidate)
    git(root, "commit", "--allow-empty", "-m", "later work")
    head = git(root, "rev-parse", "HEAD")
    receipt = acceptance(candidate)
    auth = authorization(root, head, candidate, receipt)
    objects_before = git(root, "count-objects", "-v")
    with pytest.raises(RuntimeError, match="not the expected head merged with the candidate"):
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert _integration_head(root) == head
    assert git(root, "count-objects", "-v") == objects_before


def test_merge_attributes_come_from_the_head_not_the_controller_checkout(tmp_path: Path):
    """#3186: a detached Controller can lag the integration branch, so its
    ``.gitattributes`` must not decide how the candidate merges.  The head dropped
    ``merge=union``; both sides edit the same line, so the merge must conflict (as a
    ``merge --no-ff`` at the head does) instead of union-merging under stale attributes."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.invalid")
    (root / "f.txt").write_text("a\nb\nc\n")
    (root / ".gitattributes").write_text("f.txt merge=union\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")
    controller = tmp_path / "controller"
    git(root, "worktree", "add", "-q", "--detach", str(controller), base)
    git(root, "rm", "-q", ".gitattributes")
    git(root, "commit", "-qm", "drop union")
    git(root, "checkout", "-q", "-b", "cand")
    (root / "f.txt").write_text("a\nCAND\nc\n")
    git(root, "commit", "-qam", "cand")
    candidate = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    (root / "f.txt").write_text("a\nHEAD\nc\n")
    git(root, "commit", "-qam", "head")
    head = git(root, "rev-parse", "HEAD")
    assert (controller / ".gitattributes").exists()
    with pytest.raises(RuntimeError, match="does not merge cleanly"):
        ControlledIntegrationManager._controller_merge_commit(head, candidate, controller)


# --- #3383: external merge drivers never run during governed integration ------------

_CUSTOM_DRIVER_SOURCES = (
    "repo-config",
    "worktree-config",
    "included-config",
    "merge-default",
    "head-committed-attributes",
    "info-attributes",
    "repo-core-attributes-file",
    "env-git-config-count",
    "env-git-config-parameters",
    "env-git-config-hides-repo-config",
)


@pytest.fixture
def isolated_git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No real user or system Git config, and no inherited Git config environment."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for name in ("GIT_CONFIG", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_ATTR_SOURCE"):
        monkeypatch.delenv(name, raising=False)


def _driver_repo(tmp_path: Path, attributes: str | None) -> tuple[Path, str, str]:
    """Head and candidate both edit ``f.txt`` (different lines), so a content merge runs."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "t")
    git(root, "config", "user.email", "t@example.invalid")
    (root / "f.txt").write_text("a\nb\nc\nd\ne\n")
    if attributes is not None:
        (root / ".gitattributes").write_text(attributes)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "checkout", "-q", "-b", "cand")
    (root / "f.txt").write_text("a\nCAND\nc\nd\ne\n")
    git(root, "commit", "-qam", "cand")
    candidate = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    (root / "f.txt").write_text("a\nb\nc\nd\nHEAD\n")
    git(root, "commit", "-qam", "head")
    return root, git(root, "rev-parse", "HEAD"), candidate


def _plant_driver(tmp_path: Path, root: Path, source: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a ``poc`` merge driver through ``source``; it creates the returned marker."""
    marker = tmp_path / "DRIVER_RAN"
    command = f"touch {shlex.quote(str(marker))}"
    selector = tmp_path / "selector.attributes"
    selector.write_text("* merge=poc\n")
    if source == "repo-config":
        git(root, "config", "merge.poc.driver", command)
        shutil.copy(selector, root / ".git" / "info" / "attributes")
    elif source == "worktree-config":
        git(root, "config", "extensions.worktreeConfig", "true")
        git(root, "config", "--worktree", "merge.poc.driver", command)
        shutil.copy(selector, root / ".git" / "info" / "attributes")
    elif source == "included-config":
        included = tmp_path / "included.cfg"
        git(root, "config", "--file", str(included), "merge.poc.driver", command)
        git(root, "config", "include.path", str(included))
        shutil.copy(selector, root / ".git" / "info" / "attributes")
    elif source == "merge-default":
        git(root, "config", "merge.poc.driver", command)
        git(root, "config", "merge.default", "poc")
    elif source == "head-committed-attributes":
        git(root, "config", "merge.poc.driver", command)
    elif source == "info-attributes":
        git(root, "config", "merge.poc.driver", command)
        shutil.copy(selector, root / ".git" / "info" / "attributes")
    elif source == "repo-core-attributes-file":
        git(root, "config", "merge.poc.driver", command)
        git(root, "config", "core.attributesFile", str(selector))
    elif source == "env-git-config-count":
        shutil.copy(selector, root / ".git" / "info" / "attributes")
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "merge.poc.driver")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", command)
    elif source == "env-git-config-parameters":
        assert "'" not in command
        shutil.copy(selector, root / ".git" / "info" / "attributes")
        monkeypatch.setenv("GIT_CONFIG_PARAMETERS", f"'merge.poc.driver'='{command}'")
    elif source == "env-git-config-hides-repo-config":
        git(root, "config", "merge.poc.driver", command)
        shutil.copy(selector, root / ".git" / "info" / "attributes")
        empty = tmp_path / "empty.cfg"
        empty.write_text("")
        monkeypatch.setenv("GIT_CONFIG", str(empty))
    else:  # pragma: no cover - parametrisation guard
        raise AssertionError(source)
    return marker


def _raw_merge_tree(root: Path, head: str, candidate: str) -> None:
    """The pre-#3383 staging merge argv under the same sanitised environment."""
    environment = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", f"--attr-source={head}", "merge-tree",
         "--write-tree", "--no-messages", head, candidate],
        cwd=root, env=environment, capture_output=True, text=True, check=False,
    )  # fmt: skip


@pytest.mark.parametrize("source", _CUSTOM_DRIVER_SOURCES)
def test_a_custom_merge_driver_from_any_config_source_is_refused_and_never_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git_env: None, source: str
):
    """#3383: the positive control proves the planted driver is live for the exact
    staging merge argv; the Controller then refuses before any merge runs."""
    attributes = "* merge=poc\n" if source == "head-committed-attributes" else None
    root, head, candidate = _driver_repo(tmp_path, attributes)
    marker = _plant_driver(tmp_path, root, source, monkeypatch)

    _raw_merge_tree(root, head, candidate)
    assert marker.exists(), "positive control: the planted driver must run without the guard"
    marker.unlink()

    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED"):
        ControlledIntegrationManager._controller_merge_commit(head, candidate, root)
    assert not marker.exists()


def test_without_the_guard_the_planted_driver_runs_in_the_staging_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git_env: None
):
    """#3383 reverse check: with the refusal removed, the real staging merge executes the
    driver, so the refusal test above fails for the reason it guards against."""
    root, head, candidate = _driver_repo(tmp_path, None)
    marker = _plant_driver(tmp_path, root, "repo-config", monkeypatch)
    monkeypatch.setattr(
        ControlledIntegrationManager,
        "_refuse_custom_merge_drivers",
        classmethod(lambda cls, cwd: None),
    )
    ControlledIntegrationManager._controller_merge_commit(head, candidate, root)
    assert marker.exists()


@pytest.mark.parametrize(
    ("attributes", "config", "merges"),
    [
        (None, (), True),
        ("f.txt merge=text\n", (), True),
        ("f.txt merge=union\n", (), True),
        (None, (("merge.default", "union"), ("merge.renames", "true")), True),
        ("f.txt merge=binary\n", (), False),
        ("f.txt -merge\n", (), False),
    ],
    ids=["unspecified", "text", "union", "builtin-default-and-merge-keys", "binary", "unset"],
)
def test_builtin_merge_drivers_and_merge_settings_keep_their_behaviour(
    tmp_path: Path, isolated_git_env: None, attributes, config, merges
):
    """#3383: only ``merge.<name>.*`` driver definitions are refused; Git's built-in
    drivers and two-level ``merge.*`` settings merge (or conflict) exactly as
    ``git merge --no-ff`` at the head does."""
    root, head, candidate = _driver_repo(tmp_path, attributes)
    for key, value in config:
        git(root, "config", key, value)
    reference = tmp_path / "reference"
    git(root, "worktree", "add", "-q", "--detach", str(reference), head)
    reference_ok = (
        subprocess.run(
            ["git", "merge", "--no-ff", "--no-edit", candidate], cwd=reference, capture_output=True
        ).returncode
        == 0
    )
    assert reference_ok is merges
    if merges:
        sha = ControlledIntegrationManager._controller_merge_commit(head, candidate, root)
        assert git(root, "rev-parse", f"{sha}^{{tree}}") == git(
            reference, "rev-parse", "HEAD^{tree}"
        )
    else:
        with pytest.raises(RuntimeError, match="does not merge cleanly"):
            ControlledIntegrationManager._controller_merge_commit(head, candidate, root)


def test_a_driver_planted_while_the_staging_merge_runs_yields_no_staging_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git_env: None
):
    """#3383 config race: a driver written after the pre-merge check is caught by the
    post-merge check, before ``commit-tree`` records any staging commit."""
    root, head, candidate = _driver_repo(tmp_path, None)
    real_run = ControlledIntegrationManager._run_sanitised_git
    calls: list[str] = []

    def racing_run(args, cwd):
        result = real_run(args, cwd)
        calls.append(args[1] if args[0].startswith("--attr-source=") else args[0])
        if "merge-tree" in args:
            git(root, "config", "merge.poc.driver", "true")
        return result

    monkeypatch.setattr(
        ControlledIntegrationManager, "_run_sanitised_git", staticmethod(racing_run)
    )
    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED"):
        ControlledIntegrationManager._controller_merge_commit(head, candidate, root)
    assert "merge-tree" in calls
    assert "commit-tree" not in calls


def test_an_unreadable_config_is_refused_before_the_merge(tmp_path: Path, isolated_git_env: None):
    root, head, candidate = _driver_repo(tmp_path, None)
    with (root / ".git" / "config").open("a") as config:
        config.write("[broken\n")
    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED"):
        ControlledIntegrationManager._controller_merge_commit(head, candidate, root)


def test_a_custom_merge_driver_fails_the_authorized_integration_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_git_env: None
):
    """#3383 end to end: a driver in the Controller's repository config is refused
    with no staging commit, the integration branch unmoved and the driver never run."""
    root, base, candidate = make_repo(tmp_path)
    (root / "value.txt").write_text("base\n\n\n\nhead\n")
    git(root, "commit", "-qam", "head edits the same file")
    head = git(root, "rev-parse", "HEAD")
    marker = _plant_driver(tmp_path, root, "info-attributes", monkeypatch)
    receipt = acceptance(candidate)
    auth = authorization(root, head, candidate, receipt)
    with pytest.raises(RuntimeError, match="CUSTOM_MERGE_DRIVER_REFUSED") as refused:
        integrate(
            staging_root=str(tmp_path / "stage"),
            apply=True,
            acceptance_receipt=receipt,
            auth=auth,
        )
    assert not marker.exists()
    assert _integration_head(root) == head
    error = refused.value
    if isinstance(error, IntegrationExecutionError):
        assert error.merge_performed is False
        assert error.staging_commit_sha in (None, "")
