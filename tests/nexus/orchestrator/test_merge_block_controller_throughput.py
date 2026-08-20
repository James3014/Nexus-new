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
from nexus.orchestrator.worktree_manager import (
    WorktreeManager,
    _contract_digest,
    _domain_fingerprint,
    _source_identity,
)


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
    # A caller snapshot cannot substitute for durable ownership.
    assert manager.target_conflict(contract, task_states=states) is True
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
    lease_a = manager.create_lease(a, attempt_id="a-attempt")
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
    assert manager.target_conflict(b, task_states=state_a) is True
    state_a["a"]["attempt_id"] = "a-attempt"
    lease_b = manager.create_lease(b, task_states=state_a, attempt_id="b-attempt")
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


def test_concurrent_disjoint_create_lease_refreshes_ownership_under_lock(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contracts = [
        _real_contract(controller, target_root, task_id, [f"scope/{task_id}.txt"])
        for task_id in ("a", "b")
    ]
    states = {}
    for c in contracts:
        c_hash = _contract_digest(c)
        src_id = _source_identity(
            str(controller.resolve()),
            c.controller_revision,
            c_hash,
            execution_authority="WORKER_REGISTRY",
        )
        states[c.task_id] = {
            "task_id": c.task_id,
            "status": "SUBMITTED",
            "attempt_id": f"attempt-{c.task_id}",
            "contract_hash": c_hash,
            "source_identity": src_id,
            "controller_revision": c.controller_revision,
            "controller_worktree": str(controller.resolve()),
            "contract": c.model_dump(mode="json"),
        }
    barrier = threading.Barrier(2)

    def acquire(contract):
        barrier.wait(timeout=5)
        return manager.create_lease(
            contract,
            task_states=states,
            attempt_id=f"attempt-{contract.task_id}",
        ).task_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(acquire, contracts))
    assert results == ["a", "b"]
    assert all((target_root / task_id).is_dir() for task_id in ("a", "b"))


def test_missing_authoritative_ownership_keeps_live_target_fail_closed(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease = manager.create_lease(contract, task_states={})
    valid_state = {
        "a": {
            "task_id": "a",
            "status": "CANDIDATE_CAPTURED",
            "attempt_id": lease.lease_id,
            "lease_id": lease.lease_id,
            "controller_revision": contract.controller_revision,
            "controller_worktree": str(controller),
            "contract": contract.model_dump(mode="json"),
            "lease": lease.__dict__,
        }
    }
    ownership = manager._ownership_record_path(controller, contract.task_id)
    ownership.unlink()
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            _real_contract(controller, target_root, "b", ["scope/b.txt"]),
            task_states=valid_state,
        )
    assert Path(lease.target_worktree).exists()


def test_tampered_durable_scope_cannot_be_overridden_by_valid_snapshot(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a, task_states={})
    ownership = manager._ownership_record_path(controller, contract_a.task_id)
    record = json.loads(ownership.read_text(encoding="utf-8"))
    record["contract"]["allowed_files"] = ["scope"]
    ownership.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    valid_snapshot = {
        "a": {
            "task_id": "a",
            "status": "CANDIDATE_CAPTURED",
            "attempt_id": lease_a.lease_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
        }
    }
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            _real_contract(controller, target_root, "b", ["scope/b.txt"]),
            task_states=valid_snapshot,
        )


def test_forged_terminal_snapshot_cannot_hide_clean_live_target(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a, task_states={})
    forged_terminal = {
        "a": {
            "task_id": "a",
            "status": "FINAL_BLOCK",
            "attempt_id": lease_a.lease_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
        }
    }
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            _real_contract(controller, target_root, "b", ["scope/a.txt"]),
            task_states=forged_terminal,
        )


def test_forged_terminal_snapshot_cannot_hide_dirty_live_target(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a, task_states={})
    target = Path(lease_a.target_worktree)
    (target / "scope").mkdir()
    (target / "scope" / "a.txt").write_text("uncommitted\n", encoding="utf-8")
    forged_terminal = {
        "a": {
            "task_id": "a",
            "status": "RETAINED_FOR_REVIEW",
            "attempt_id": lease_a.lease_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
        }
    }
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            _real_contract(controller, target_root, "b", ["scope/a.txt"]),
            task_states=forged_terminal,
        )


def test_public_service_admission_allows_disjoint_and_blocks_overlap(tmp_path, monkeypatch):
    calls = []
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))

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


def test_final_block_and_retained_review_targets_remain_reserved_in_worktree_manager(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a, task_states={})

    # Status FINAL_BLOCK or RETAINED_FOR_REVIEW is descriptive only; physical Target remains reserved
    final_block_state = {
        "a": {
            "task_id": "a",
            "status": "FINAL_BLOCK",
            "attempt_id": lease_a.lease_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
        }
    }
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(
            _real_contract(controller, target_root, "b", ["scope/a.txt"]),
            task_states=final_block_state,
        )

    # Perform verified cleanup of a
    cleanup_receipt = manager.cleanup_terminal_target(contract_a, lease_a)
    assert cleanup_receipt.decision == "REMOVED"
    assert cleanup_receipt.performed is True

    # Now b can be admitted cleanly
    lease_b = manager.create_lease(
        _real_contract(controller, target_root, "b", ["scope/a.txt"]),
        task_states={"a": {**final_block_state["a"], "cleanup_decision": "REMOVED"}},
    )
    assert lease_b.task_id == "b"
    assert Path(lease_b.target_worktree).exists()


def test_symlink_ownership_record_fails_closed_in_target_conflict(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    manager.create_lease(contract_a, task_states={})

    ownership = manager._ownership_record_path(controller, contract_a.task_id)
    outside = controller / "base.txt"
    ownership.unlink()
    ownership.symlink_to(outside)

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    # Symlink ownership record fails closed -> target_conflict is True
    assert manager.target_conflict(contract_b) is True


def test_malformed_json_ownership_record_fails_closed_in_target_conflict(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    manager.create_lease(contract_a, task_states={})

    ownership = manager._ownership_record_path(controller, contract_a.task_id)
    ownership.write_text("{malformed:json", encoding="utf-8")

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    assert manager.target_conflict(contract_b) is True


def test_swap_race_tampered_task_id_fails_closed_in_target_conflict(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    manager.create_lease(contract_a, task_states={})

    ownership = manager._ownership_record_path(controller, contract_a.task_id)
    record = json.loads(ownership.read_text(encoding="utf-8"))
    record["task_id"] = "forged-task-id"
    record["integrity_sha256"] = manager._ownership_digest(record)
    ownership.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    assert manager.target_conflict(contract_b) is True


def test_cleanup_and_admission_share_same_reservation_lock(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a, task_states={})

    lock_acquired = threading.Event()
    release_lock = threading.Event()
    cleanup_done = threading.Event()

    def hold_lock():
        with manager._reservation_lock(controller):
            lock_acquired.set()
            assert release_lock.wait(timeout=5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert lock_acquired.wait(timeout=5)

    def do_cleanup():
        receipt = manager.cleanup_terminal_target(contract_a, lease_a)
        assert receipt.decision == "REMOVED"
        cleanup_done.set()

    cleaner = threading.Thread(target=do_cleanup)
    cleaner.start()

    # Cleanup must be blocked while lock is held
    time.sleep(0.05)
    assert not cleanup_done.is_set()

    # Release lock -> cleanup completes
    release_lock.set()
    holder.join(timeout=5)
    cleaner.join(timeout=5)
    assert cleanup_done.is_set()


def test_direct_service_admission_blocks_when_retained_target_exists(tmp_path, monkeypatch):
    calls = []
    controller, target_root = _real_repo(tmp_path)
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(target_root))

    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_retained = _real_contract(controller, target_root, "retained", ["scope/a.txt"])
    retained_lease = manager.create_lease(contract_retained, task_states={})

    # Real registered worktree and real durable ownership record exist on disk
    assert Path(retained_lease.target_worktree).exists()
    assert manager._ownership_record_path(controller, contract_retained.task_id).exists()

    def runner(contract, request, update):
        calls.append((contract.task_id, contract.target_repo_root))
        return {"promotion_status": "PENDING_HUMAN_APPROVAL"}

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    # Set descriptive FINAL_BLOCK lifecycle state for task 'retained'
    base = _task(task_id="retained", allowed_files=["scope/a.txt"], status="FINAL_BLOCK")
    base["controller_worktree"] = str(controller)
    base["expected_controller_worktree"] = str(controller)
    service._write_state(
        "retained",
        {
            **base,
            "attempt_id": retained_lease.lease_id,
            "expected_attempt_id": retained_lease.lease_id,
            "lease_id": retained_lease.lease_id,
            "expected_lease_id": retained_lease.lease_id,
            "request": {"task_id": "retained", "allowed_files": ["scope/a.txt"]},
            "contract": contract_retained.model_dump(mode="json"),
            "lease": retained_lease.__dict__,
        },
    )

    request_overlap = {
        "task_id": "overlap-task",
        "what": "overlapping",
        "why": "test",
        "controller_revision": contract_retained.controller_revision,
        "target_base_revision": contract_retained.target_base_revision,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "overlap-task"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["scope/a.txt"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "execution_lane": "ISOLATED_TARGET",
        "worker": "codex",
        "allow_unbound_test_identity": True,
        "task_card_path": str(tmp_path / "missing-card.txt"),
        "idempotency_key": "overlap-idempotent",
    }
    # Direct service admission must block because physical Target and durable ownership remain reserved
    with pytest.raises(RuntimeError, match="overlapping Target"):
        service.submit_task(request_overlap)
    assert calls == []

    # Perform verified physical cleanup
    receipt = manager.cleanup_terminal_target(contract_retained, retained_lease)
    assert receipt.decision == "REMOVED"

    # Update lifecycle state cleanup_decision
    service._write_state(
        "retained",
        {
            **service._read_state_snapshot("retained"),
            "cleanup_decision": "REMOVED",
        },
    )

    # Now submission succeeds and invokes runner
    service.submit_task(request_overlap)
    for _ in range(100):
        if calls:
            break
        time.sleep(0.01)
    assert len(calls) == 1
    assert calls[0][0] == "overlap-task"


def test_service_submission_binds_source_identity_and_attempt_id(tmp_path, monkeypatch):
    controller, target_root = _real_repo(tmp_path)
    state_dir = tmp_path / "state"
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(target_root))
    calls = []

    def runner(contract, state, progress_cb):
        calls.append((contract.task_id, state.get("attempt_id"), state.get("source_identity")))
        return {"status": "SUCCESS"}

    service = SelfHostedTaskService(
        state_dir=state_dir,
        runner=runner,
        auto_reconcile=False,
        ephemeral=True,
    )
    rev = _git(controller, "rev-parse", "HEAD")
    request = {
        "task_id": "bind-task",
        "what": "testing source identity binding",
        "why": "test",
        "controller_revision": rev,
        "target_base_revision": rev,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "bind-task"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["scope/bind.txt"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "execution_lane": "ISOLATED_TARGET",
        "worker": "codex",
        "allow_unbound_test_identity": True,
        "task_card_path": str(tmp_path / "card.txt"),
        "idempotency_key": "bind-idempotent",
    }
    result = service.submit_task(request)
    assert result["task_id"] == "bind-task"
    state = service._read_state_snapshot("bind-task")
    assert state["attempt_id"] == result["attempt_id"]
    assert "source_identity" in state
    assert state["source_identity"].startswith(f"controller:{controller.resolve()}:{rev}:")
    assert "authority:EPHEMERAL_TEST_RUNNER" in state["source_identity"]


def test_lingering_ownership_record_after_abrupt_worktree_deletion_blocks_service_admission(
    tmp_path, monkeypatch
):
    controller, target_root = _real_repo(tmp_path)
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(target_root))
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "lingering-a", ["scope/common.txt"])
    lease_a = manager.create_lease(contract_a)
    assert Path(lease_a.target_worktree).exists()

    record_path = manager._ownership_record_path(controller, "lingering-a")
    assert record_path.exists()

    # Abruptly remove worktree without CAS record cleanup
    _git(controller, "worktree", "remove", "--force", str(lease_a.target_worktree))
    assert not Path(lease_a.target_worktree).exists()
    assert record_path.exists()

    # Attempt to submit new task with overlapping scope through service
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        runner=lambda c, s, p: {"status": "SUCCESS"},
        auto_reconcile=False,
        ephemeral=True,
    )
    request_b = {
        "task_id": "lingering-b",
        "what": "conflicting with lingering record",
        "why": "test",
        "controller_revision": contract_a.controller_revision,
        "target_base_revision": contract_a.target_base_revision,
        "controller_repo_root": str(controller),
        "target_repo_root": str(target_root / "lingering-b"),
        "target_worktree_root": str(target_root),
        "allowed_files": ["scope/common.txt"],
        "forbidden_files": [],
        "verifier_commands": [],
        "protected_contracts": [],
        "execution_lane": "ISOLATED_TARGET",
        "worker": "codex",
        "allow_unbound_test_identity": True,
        "task_card_path": str(tmp_path / "card.txt"),
        "idempotency_key": "lingering-idempotent",
    }
    with pytest.raises(RuntimeError, match="overlapping Target"):
        service.submit_task(request_b)


def test_orphan_record_tampered_allowed_files_recomputed_hashes_blocks_throughput_admission(
    tmp_path,
):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a)
    assert Path(lease_a.target_worktree).exists()

    record_path = manager._ownership_record_path(controller, "a")
    assert record_path.exists()

    _git(controller, "worktree", "remove", "--force", str(lease_a.target_worktree))
    assert not Path(lease_a.target_worktree).exists()

    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["contract"]["allowed_files"] = ["scope/tampered_disjoint.txt"]
    new_contract_hash = _contract_digest(record["contract"])
    record["contract_hash"] = new_contract_hash
    record["expected_contract_hash"] = new_contract_hash
    record["domain_fingerprint"] = _domain_fingerprint(record)
    record["expected_domain_fingerprint"] = record["domain_fingerprint"]
    record["source_identity"] = _source_identity(
        str(controller.resolve()),
        contract_a.controller_revision,
        new_contract_hash,
        execution_authority="WORKER_REGISTRY",
    )
    record["expected_source_identity"] = record["source_identity"]
    record["integrity_sha256"] = manager._ownership_digest(record)
    record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

    state_a = {
        "a": {
            "task_id": "a",
            "status": "CANDIDATE_CAPTURED",
            "attempt_id": lease_a.attempt_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller.resolve()),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
            "expected_attempt_id": lease_a.attempt_id,
            "expected_lease_id": lease_a.lease_id,
            "expected_controller_revision": contract_a.controller_revision,
            "expected_controller_worktree": str(controller.resolve()),
        }
    }

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    # Tampered orphan record fails closed when cross-checked against unchanged snapshot
    assert manager.target_conflict(contract_b, task_states=state_a) is True
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(contract_b, task_states=state_a)


def test_orphan_record_without_snapshot_fails_closed_even_when_paths_disjoint(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a)
    assert Path(lease_a.target_worktree).exists()

    record_path = manager._ownership_record_path(controller, "a")
    assert record_path.exists()

    _git(controller, "worktree", "remove", "--force", str(lease_a.target_worktree))
    assert not Path(lease_a.target_worktree).exists()

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    # Orphan record without snapshot in task_states fails closed
    assert manager.target_conflict(contract_b, task_states={}) is True
    with pytest.raises(RuntimeError, match="serial Target budget exceeded"):
        manager.create_lease(contract_b, task_states={})


def test_valid_orphan_record_with_matching_snapshot_allows_disjoint_concurrency(tmp_path):
    controller, target_root = _real_repo(tmp_path)
    manager = WorktreeManager(root_dir=target_root, process_checker=lambda _: False)
    contract_a = _real_contract(controller, target_root, "a", ["scope/a.txt"])
    lease_a = manager.create_lease(contract_a)
    assert Path(lease_a.target_worktree).exists()

    record_path = manager._ownership_record_path(controller, "a")
    assert record_path.exists()

    _git(controller, "worktree", "remove", "--force", str(lease_a.target_worktree))
    assert not Path(lease_a.target_worktree).exists()

    record = json.loads(record_path.read_text(encoding="utf-8"))
    state_a = {
        "a": {
            "task_id": "a",
            "status": "CANDIDATE_CAPTURED",
            "attempt_id": lease_a.attempt_id,
            "lease_id": lease_a.lease_id,
            "controller_revision": contract_a.controller_revision,
            "controller_worktree": str(controller.resolve()),
            "contract": contract_a.model_dump(mode="json"),
            "lease": lease_a.__dict__,
            "expected_attempt_id": lease_a.attempt_id,
            "expected_lease_id": lease_a.lease_id,
            "expected_controller_revision": contract_a.controller_revision,
            "expected_controller_worktree": str(controller.resolve()),
            "contract_hash": record.get("contract_hash"),
            "source_identity": record.get("source_identity"),
        }
    }

    contract_b = _real_contract(controller, target_root, "b", ["scope/b.txt"])
    assert manager.target_conflict(contract_b, task_states=state_a) is False
    lease_b = manager.create_lease(contract_b, task_states=state_a)
    assert lease_b.task_id == "b"
    assert Path(lease_b.target_worktree).exists()
