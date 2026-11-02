"""Post-apply commands are bound to the integration authorization (#3185).

The commands that run after apply must be the ones the authorization hashed, in
one canonical argv form, and the integration branch must still be the applied
commit once they have run.
"""

import dataclasses
import hashlib
import json
import shlex
import sys
from pathlib import Path

import pytest

from nexus.contracts.target_integration_lifecycle import (
    ExternalAcceptanceReceipt,
    IntegrationAuthorizationEnvelope,
)
from nexus.orchestrator.governed_integration import (
    ControlledIntegrationManager,
    IntegrationExecutionError,
)
from nexus.orchestrator.target_integration_lifecycle import TargetIntegrationLifecycle
from tests.nexus.orchestrator.test_target_integration_git_canary import (
    _integration_head,
    _shape_repo,
    acceptance,
    authorization,
    git,
    make_repo,
)

_BRANCH_REF = "refs/heads/nexus/integration/canary"
_NO_COMMANDS_HASH = hashlib.sha256(b"[]").hexdigest()


def _argv_hash(commands) -> str:
    """The canonical form, computed independently: JSON list of argv lists."""
    payload = json.dumps(
        [list(argv) for argv in commands], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_marker(marker: Path) -> tuple[str, ...]:
    return (sys.executable, "-c", f"open({str(marker)!r}, 'w').write('ran')")


def _run(
    tmp_path: Path,
    *,
    receipt: ExternalAcceptanceReceipt,
    auth: IntegrationAuthorizationEnvelope,
    authorized_hash: str,
    post_apply_commands,
):
    """Hand the live sink an authorized state whose post-apply hash is ``authorized_hash``."""
    auth = dataclasses.replace(auth, post_apply_commands_hash=authorized_hash)
    authorization_state = auth.to_dict()
    authorization_state["authorization_hash"] = auth.authorization_hash
    state = {
        "task_id": auth.task_id,
        "external_acceptance": receipt.to_dict(),
        "integration_authorization": authorization_state,
        "post_apply_commands": [list(command) for command in post_apply_commands],
        "verifier_argv_commands": [],
        "promotion_packet": {"candidate_commit_sha": auth.candidate_commit},
        "contract": {"controller_repo_root": auth.canonical_root, "verifier_commands": []},
    }
    return ControlledIntegrationManager(
        integration_root=auth.canonical_root
    ).integrate_authorized_task_state(
        state,
        integration_branch=auth.canonical_branch,
        staging_root=str(tmp_path / "stage"),
        apply=True,
        post_apply_commands=post_apply_commands,
    )


def _assert_refused_before_anything_ran(refused, tmp_path: Path, root: Path, base: str) -> None:
    assert not isinstance(refused.value, IntegrationExecutionError)
    assert _integration_head(root) == base
    assert not (tmp_path / "stage" / "task-1").exists()
    assert not (tmp_path / "marker").exists()


def test_post_apply_commands_that_differ_from_the_authorization_are_refused_before_anything_runs(
    tmp_path: Path,
):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    authorized = ((sys.executable, "-c", "pass"),)
    with pytest.raises(RuntimeError, match="post-apply commands do not match") as refused:
        _run(
            tmp_path,
            receipt=receipt,
            auth=authorization(root, base, candidate, receipt),
            authorized_hash=_argv_hash(authorized),
            post_apply_commands=(_write_marker(tmp_path / "marker"),),
        )
    _assert_refused_before_anything_ran(refused, tmp_path, root, base)


def test_post_apply_commands_under_an_authorization_without_their_hash_are_refused(
    tmp_path: Path,
):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    with pytest.raises(RuntimeError, match="post-apply commands do not match") as refused:
        _run(
            tmp_path,
            receipt=receipt,
            auth=authorization(root, base, candidate, receipt),
            authorized_hash="",
            post_apply_commands=(_write_marker(tmp_path / "marker"),),
        )
    _assert_refused_before_anything_ran(refused, tmp_path, root, base)


def test_an_authorization_issued_over_command_strings_is_refused_for_argv_commands(
    tmp_path: Path,
):
    # Authorizations issued before #3185 hashed a list of command strings.
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    command = _write_marker(tmp_path / "marker")
    legacy_hash = hashlib.sha256(
        json.dumps([shlex.join(command)], separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(RuntimeError, match="post-apply commands do not match") as refused:
        _run(
            tmp_path,
            receipt=receipt,
            auth=authorization(root, base, candidate, receipt),
            authorized_hash=legacy_hash,
            post_apply_commands=(command,),
        )
    _assert_refused_before_anything_ran(refused, tmp_path, root, base)


def test_authorized_post_apply_commands_that_are_not_supplied_are_refused(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    with pytest.raises(RuntimeError, match="post-apply commands do not match") as refused:
        _run(
            tmp_path,
            receipt=receipt,
            auth=authorization(root, base, candidate, receipt),
            authorized_hash=_argv_hash(((sys.executable, "-c", "pass"),)),
            post_apply_commands=(),
        )
    _assert_refused_before_anything_ran(refused, tmp_path, root, base)


def test_no_post_apply_commands_under_an_authorization_for_none_still_apply(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    applied = _run(
        tmp_path,
        receipt=receipt,
        auth=authorization(root, base, candidate, receipt),
        authorized_hash=_NO_COMMANDS_HASH,
        post_apply_commands=(),
    )
    assert applied.merge_performed is True
    assert applied.integration_commit_sha == _integration_head(root) != base


def _issue(post_apply_commands) -> IntegrationAuthorizationEnvelope:
    sha, digest = "a" * 40, "b" * 64
    receipt = ExternalAcceptanceReceipt(
        schema="nexus.external_acceptance_receipt.v1",
        task_id="task-1",
        attempt_id="attempt-1",
        candidate_commit=sha,
        receipt_hash=digest,
        reviewer_id="reviewer",
        passed=True,
        verifier_artifact="artifact",
    )
    preview = TargetIntegrationLifecycle.build_preview(
        task_id="task-1",
        target_id="target-1",
        candidate_commit=sha,
        acceptance=receipt,
        canonical_branch="nexus/integration/canary",
        expected_canonical_head=sha,
        verification_commands=(),
        cleanup_target_id="target-1",
        rollback="retain target",
    )
    return TargetIntegrationLifecycle.authorize(
        task_id="task-1",
        campaign_id="campaign",
        task_card_hash=digest,
        candidate_commit=sha,
        candidate_receipt_hash=digest,
        acceptance_receipt_hash=digest,
        canonical_root="/tmp/repo",
        canonical_branch="nexus/integration/canary",
        expected_canonical_head=sha,
        canonical_dirty_baseline=digest,
        preview=preview,
        cleanup_target_id="target-1",
        cleanup_target_path="/tmp/target-1",
        durable_ref="refs/nexus-candidate/task-1",
        rollback="retain target",
        issued_at="2026-08-02T00:00:00+00:00",
        post_apply_commands=post_apply_commands,
    )


@pytest.mark.parametrize("commands", [["pytest -q"], "pytest -q", [[]], [["pytest", 1]]])
def test_the_issuer_refuses_post_apply_commands_that_are_not_argv_lists(commands):
    with pytest.raises(ValueError, match="post-apply command"):
        _issue(commands)


def test_the_issued_hash_lets_exactly_those_argv_commands_run(tmp_path: Path):
    root, base, candidate = make_repo(tmp_path)
    receipt = acceptance(candidate)
    commands = (_write_marker(tmp_path / "marker"),)
    issued = _issue([list(command) for command in commands])
    assert issued.post_apply_commands_hash == _argv_hash(commands)
    assert _issue(()).post_apply_commands_hash == _NO_COMMANDS_HASH
    applied = _run(
        tmp_path,
        receipt=receipt,
        auth=authorization(root, base, candidate, receipt),
        authorized_hash=issued.post_apply_commands_hash,
        post_apply_commands=commands,
    )
    assert applied.post_apply_verified is True
    assert (tmp_path / "marker").read_text() == "ran"


_MOVE_BRANCH_AFTER_APPLY = (
    "import subprocess as s; "
    "s.run(['git', '-c', 'user.name=post-apply', '-c', 'user.email=post-apply@example.invalid', "
    "'commit', '-q', '--allow-empty', '-m', 'made after apply'], check=True); "
    f"s.run(['git', 'update-ref', '{_BRANCH_REF}', 'HEAD'], check=True)"
)


@pytest.mark.parametrize("shape", ["ff-only", "ref-update"])
def test_a_post_apply_step_that_moves_the_branch_is_reported_as_applied_not_verified(
    tmp_path: Path, shape: str
):
    root, base, candidate = _shape_repo(tmp_path, shape)
    receipt = acceptance(candidate)
    commands = ((sys.executable, "-c", _MOVE_BRANCH_AFTER_APPLY),)
    with pytest.raises(IntegrationExecutionError) as reported:
        _run(
            tmp_path,
            receipt=receipt,
            auth=authorization(root, base, candidate, receipt),
            authorized_hash=_argv_hash(commands),
            post_apply_commands=commands,
        )
    error = reported.value
    moved = _integration_head(root)
    assert "moved during post-apply verification" in error.failure_reason
    assert error.stage == "POST_APPLY_VERIFICATION"
    assert error.merge_performed is True
    assert error.post_apply_verified is False
    assert error.branch_head_before == base
    assert error.branch_head_after == moved != error.staging_commit_sha
    assert git(root, "rev-list", "--parents", "-n", "1", moved).split()[1:] == [
        error.staging_commit_sha
    ]
