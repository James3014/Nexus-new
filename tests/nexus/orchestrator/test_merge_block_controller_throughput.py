from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import (
    SelfHostedTaskService,
    mutation_domains_conflict,
)
from nexus.orchestrator.task_contract import MutationMode, SelfHostedTaskContract
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
    assert (
        mutation_domains_conflict(
            _task(task_id="a", allowed_files=left),
            _task(task_id="b", allowed_files=right, status="SUBMITTED"),
        )
        is True
    )


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


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _real_contract(
    controller: Path, target_root: Path, task_id: str, allowed
) -> SelfHostedTaskContract:
    base = _git(controller, "rev-parse", "HEAD")
    return SelfHostedTaskContract(
        task_id=task_id,
        objective="real throughput admission",
        controller_revision=base,
        target_base_revision=base,
        controller_repo_root=str(controller),
        target_repo_root=str(target_root / task_id),
        target_worktree_root=str(target_root),
        allowed_files=list(allowed),
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
        preferred_provider=None,
        fallback_provider=None,
        maximum_provider_calls=0,
        maximum_replans=0,
        mutation_mode=MutationMode.WORKING_TREE_ONLY,
        human_approval_required=True,
    )


def _real_repo(tmp_path: Path):
    controller = tmp_path / "controller"
    target_root = tmp_path / "targets"
    controller.mkdir()
    target_root.mkdir()
    _git(controller, "init", "-b", "main")
    _git(controller, "config", "user.email", "test@example.test")
    _git(controller, "config", "user.name", "Test")
    (controller / "base.txt").write_text("base\n", encoding="utf-8")
    _git(controller, "add", "base.txt")
    _git(controller, "commit", "-m", "base")
    return controller, target_root


def test_real_create_lease_allows_disjoint_and_blocks_exact_parent(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    lease_a = manager.create_lease(a)
    state_a = {
        "a": {
            "task_id": "a",
            "status": "CANDIDATE_CAPTURED",
            "attempt_id": "a-attempt",
            "lease_id": lease_a.lease_id,
            "controller_revision": a.controller_revision,
            "controller_worktree": a.controller_repo_root,
            "contract": a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
            "expected_attempt_id": "a-attempt",
        }
    }
    state_a["a"]["attempt_id"] = "stale-attempt"
    with pytest.raises(ValueError, match="stale"):
        manager.target_conflict(b, task_states=state_a)
    state_a["a"]["attempt_id"] = "a-attempt"
    lease_b = manager.create_lease(b, task_states=state_a)
    assert Path(lease_a.target_worktree) != Path(lease_b.target_worktree)
    b_branch = f"refs/heads/{lease_b.target_branch}"
    b_ref_before = _git(controller, "rev-parse", b_branch)
    b_head_before = _git(Path(lease_b.target_worktree), "rev-parse", "HEAD")
    b_lease_bytes = json.dumps(lease_b.__dict__, sort_keys=True).encode()
    b_lease_hash = hashlib.sha256(b_lease_bytes).hexdigest()
    evidence = tmp_path / "b-evidence.json"
    evidence.write_bytes(b_lease_bytes)
    evidence_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert manager.cleanup_terminal_target(a, lease_a).decision == "REMOVED"
    assert Path(lease_b.target_worktree).exists()
    assert _git(controller, "rev-parse", b_branch) == b_ref_before
    assert _git(Path(lease_b.target_worktree), "rev-parse", "HEAD") == b_head_before
    assert (
        hashlib.sha256(json.dumps(lease_b.__dict__, sort_keys=True).encode()).hexdigest()
        == b_lease_hash
    )
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == evidence_hash
    overlapping = _real_contract(controller, target_root, "overlap", ["scope"])
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            overlapping,
            task_states={
                **state_a,
                "b": {
                    "task_id": "b",
                    "status": "CANDIDATE_CAPTURED",
                    "attempt_id": "b-attempt",
                    "lease_id": lease_b.lease_id,
                    "controller_revision": b.controller_revision,
                    "controller_worktree": b.controller_repo_root,
                    "contract": b.model_dump(mode="json"),
                    "lease": lease_b.__dict__,
                },
            },
        )


def test_real_create_lease_rejects_bad_revision_and_ambiguous_scope(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    bad = _real_contract(controller, target_root, "bad", ["scope/a.txt"])
    with pytest.raises(RuntimeError, match="lowercase 40-hex"):
        manager.create_lease(
            bad.model_copy(update={"controller_revision": bad.controller_revision.upper()})
        )
    malformed = _real_contract(controller, target_root, "malformed", ["scope/a.txt"]).model_copy(
        update={"allowed_files": ["scope//a.txt"]}
    )
    with pytest.raises(ValueError, match="MUTATION_DOMAIN_INVALID"):
        manager.create_lease(malformed)


def test_create_lease_uses_shared_common_git_dir_for_linked_worktree(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    linked = tmp_path / "linked"
    _git(controller, "worktree", "add", "--detach", str(linked), "HEAD")
    assert (linked / ".git").is_file()
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract = _real_contract(linked, target_root, "linked", ["scope/linked.txt"])
    lease = manager.create_lease(contract)
    assert Path(lease.target_worktree).exists()
    assert (controller / ".git" / "nexus-target-admission.lock").exists()


@pytest.mark.parametrize("first,second", [("a", "b"), ("b", "a")])
def test_create_lease_reservation_lock_has_controlled_order(tmp_path, first, second):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contracts = [
        _real_contract(controller, target_root, str(i), ["scope/a.txt"]) for i in ("a", "b")
    ]
    states = {
        contract.task_id: {
            "task_id": contract.task_id,
            "status": "SUBMITTED",
            "attempt_id": f"{contract.task_id}-attempt",
            "controller_revision": contract.controller_revision,
            "controller_worktree": contract.controller_repo_root,
            "contract": contract.model_dump(mode="json"),
        }
        for contract in contracts
    }

    original = manager._create_lease_locked
    entered = threading.Event()
    release = threading.Event()

    def controlled(contract, *, task_states=None):
        if contract.task_id == first:
            entered.set()
            assert release.wait(timeout=5)
        return original(contract, task_states=task_states)

    manager._create_lease_locked = controlled

    def acquire(contract):
        try:
            return ("ok", manager.create_lease(contract, task_states=states).task_id)
        except RuntimeError as exc:
            return ("blocked", str(exc))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            acquire, next(item for item in contracts if item.task_id == first)
        )
        assert entered.wait(timeout=5)
        second_future = pool.submit(
            acquire, next(item for item in contracts if item.task_id == second)
        )
        time.sleep(0.05)
        assert not second_future.done()
        release.set()
        first_result = first_future.result(timeout=5)
        second_result = second_future.result(timeout=5)
    assert first_result == ("ok", first)
    assert second_result[0] == "blocked"


def test_public_service_admission_allows_disjoint_and_blocks_overlap(tmp_path):
    calls = []

    def runner(contract, request, update):
        calls.append((contract.task_id, contract.target_repo_root))
        return {"promotion_status": "PENDING_HUMAN_APPROVAL"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    base = _task(task_id="a", allowed_files=["scope/a.txt"])
    base["controller_worktree"] = str(tmp_path / "controller")
    base["expected_controller_worktree"] = str(tmp_path / "controller")
    service._write_state(
        "a",
        {
            **base,
            "request": {"task_id": "a", "allowed_files": ["scope/a.txt"]},
            "contract": {
                "controller_repo_root": str(tmp_path / "controller"),
                "controller_revision": "a" * 40,
                "allowed_files": ["scope/a.txt"],
                "target_repo_root": str(tmp_path / "targets" / "a"),
            },
        },
    )
    request_b = {
        "task_id": "b",
        "what": "disjoint",
        "why": "throughput",
        "controller_revision": "a" * 40,
        "target_base_revision": "b" * 40,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "b"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["scope/b.txt"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "execution_lane": "ISOLATED_TARGET",
        "worker": "codex",
        "allow_unbound_test_identity": True,
        "task_card_path": str(tmp_path / "missing-card-b.txt"),
        "idempotency_key": "b-idempotent",
    }
    service.submit_task(request_b)
    for _ in range(100):
        if calls:
            break
        time.sleep(0.01)
    assert calls == [("b", str(tmp_path / "targets" / "b"))]
    request_overlap = {
        **request_b,
        "task_id": "c",
        "target_repo_root": str(tmp_path / "targets" / "c"),
        "allowed_files": ["scope"],
    }
    with pytest.raises(RuntimeError, match="overlapping Target"):
        service.submit_task(request_overlap)
    assert calls == [("b", str(tmp_path / "targets" / "b"))]
    assert service.submit_task(request_b).get("duplicate") is True
    assert calls == [("b", str(tmp_path / "targets" / "b"))]
