from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import mutation_domains_conflict
from nexus.orchestrator.worktree_manager import WorktreeManager


def _task(*, task_id: str, allowed_files, status="CANDIDATE_CAPTURED", **extra):
    return {
        "task_id": task_id,
        "attempt_id": f"attempt-{task_id}",
        "lease_id": f"lease-{task_id}",
        "controller_revision": "a" * 40,
        "controller_worktree": "/repo",
        "expected_attempt_id": f"attempt-{task_id}",
        "expected_lease_id": f"lease-{task_id}",
        "expected_controller_revision": "a" * 40,
        "expected_controller_worktree": "/repo",
        "status": status,
        "contract": {
            "task_id": task_id,
            "controller_repo_root": "/repo",
            "controller_revision": "a" * 40,
            "allowed_files": list(allowed_files),
            "mutation_mode": "ISOLATED_TARGET",
        },
        **extra,
    }


def test_merge_waiting_disjoint_task_reaches_distinct_admission_domain():
    a = _task(task_id="a", allowed_files=["scope/a.txt"])
    b = _task(task_id="b", allowed_files=["scope/b.txt"], status="SUBMITTED")

    assert mutation_domains_conflict(a, b) is False


@pytest.mark.parametrize(
    "left,right",
    [
        (["scope/a.txt"], ["scope/a.txt"]),
        (["scope"], ["scope/a.txt"]),
        (["scope/a.txt"], ["scope"]),
    ],
)
def test_exact_and_parent_child_overlap_blocks_before_provider(left, right):
    assert mutation_domains_conflict(
        _task(task_id="a", allowed_files=left),
        _task(task_id="b", allowed_files=right, status="SUBMITTED"),
    ) is True


@pytest.mark.parametrize(
    "left,right",
    [
        (["../escape.txt"], ["scope/b.txt"]),
        (["scope//a.txt"], ["scope/a.txt"]),
        (["/repo/scope/a.txt"], ["scope/b.txt"]),
        (["scope/a.txt", "scope"], ["scope/b.txt"]),
    ],
)
def test_malformed_or_ambiguous_domains_fail_closed(left, right):
    with pytest.raises(ValueError):
        mutation_domains_conflict(
            _task(task_id="a", allowed_files=left),
            _task(task_id="b", allowed_files=right, status="SUBMITTED"),
        )


@pytest.mark.parametrize(
    "tamper",
    [
        {"attempt_id": "other"},
        {"lease_id": "other"},
        {"controller_revision": "b" * 40},
        {"controller_worktree": "/other"},
        {"competition_id": "forged"},
    ],
)
def test_stale_or_forged_identity_fails_closed(tamper):
    a = _task(task_id="a", allowed_files=["scope/a.txt"], **tamper)
    b = _task(task_id="b", allowed_files=["scope/b.txt"], status="SUBMITTED")
    with pytest.raises(ValueError):
        mutation_domains_conflict(a, b)


def test_direct_canonical_overlap_remains_blocked():
    a = _task(task_id="a", allowed_files=["scope/a.txt"])
    b = _task(
        task_id="b",
        allowed_files=["scope/a.txt"],
        status="SUBMITTED",
        contract={
            "task_id": "b",
            "controller_repo_root": "/repo",
            "controller_revision": "a" * 40,
            "allowed_files": ["scope/a.txt"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    assert mutation_domains_conflict(a, b) is True


def test_worktree_manager_uses_same_disjoint_predicate_before_target_creation(tmp_path):
    manager = WorktreeManager(root_dir=tmp_path / "targets", create_root=True)
    contract = SimpleNamespace(
        task_id="b",
        controller_repo_root=str(tmp_path / "repo"),
        target_repo_root=str(tmp_path / "targets" / "b"),
        target_worktree_root=str(tmp_path / "targets"),
        target_base_revision="a" * 40,
        controller_revision="a" * 40,
        allowed_files=("scope/b.txt",),
        mutation_mode="ISOLATED_TARGET",
    )
    states = {"a": _task(task_id="a", allowed_files=["scope/a.txt"])}
    states["a"]["controller_worktree"] = contract.controller_repo_root
    states["a"]["contract"]["controller_repo_root"] = contract.controller_repo_root
    states["a"]["expected_controller_worktree"] = contract.controller_repo_root
    manager._active_target_worktrees = lambda *args, **kwargs: [
        {"worktree": str(tmp_path / "targets" / "a"), "branch": "refs/heads/nexus/task/a"}
    ]
    assert manager.target_conflict(contract, task_states=states) is False
    states["a"]["contract"]["allowed_files"] = ["scope"]
    assert manager.target_conflict(contract, task_states=states) is True
