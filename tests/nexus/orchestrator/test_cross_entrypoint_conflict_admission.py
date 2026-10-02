"""Tests for #98 cross-entrypoint physical mutation-conflict admission.

Invariants verified:
1. direct GPT writer (DIRECT_CANONICAL) vs overlapping RDC worker (DIRECT_DELEGATED) -> OVERLAP
2. RDC worker (DIRECT_DELEGATED) vs Local writer (LOCAL) overlapping domain -> OVERLAP
3. governed Target (ISOLATED_TARGET) vs direct mutation (DIRECT_CANONICAL) overlapping -> OVERLAP
4. disjoint mutation domains -> CLEAR / SAFE
5. stale writer identity -> STALE (fail closed)
6. unresolved/unknown prior effect -> RECONCILE_REQUIRED (fail closed)
7. cleanup/release does not invalidate another live owner
8. UNKNOWN and STALE fail closed into non-CLEAR disposition
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path

import pytest

import nexus.services.live_execution_provenance as provenance_module
from nexus.orchestrator.task_contract import SelfHostedTaskContract
from nexus.orchestrator.worktree_manager import (
    CONFLICT_CLEAR,
    CONFLICT_OVERLAP,
    CONFLICT_RECONCILE_REQUIRED,
    CONFLICT_STALE,
    CONFLICT_UNKNOWN,
    MUTATION_CONFLICT_CLAIM_CEILING,
    MUTATION_CONFLICT_SCHEMA,
    WorktreeManager,
    evaluate_cross_entrypoint_conflict,
    mutation_domains_conflict,
)
from nexus.services.direct_operation_journal import DirectOperationJournal
from nexus.services.live_execution_provenance import (
    PRODUCER_SCHEMA_AGY_OPERATION_V1,
    PRODUCER_SCHEMA_DEV_MCP_V1,
    PRODUCER_SCHEMA_RDC_V1,
)


def _writer(
    task_id: str,
    allowed_files: list[str],
    *,
    attempt_id: str = "att-01",
    mutation_mode: str = "ISOLATED_TARGET",
    controller_revision: str = "a" * 40,
    controller_worktree: str = "/repo",
    status: str = "CANDIDATE_CAPTURED",
    **extra,
) -> dict:
    return {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lease_id": f"lease-{task_id}",
        "controller_revision": controller_revision,
        "controller_worktree": controller_worktree,
        "status": status,
        "mutation_mode": mutation_mode,
        "contract": {
            "task_id": task_id,
            "controller_repo_root": controller_worktree,
            "controller_revision": controller_revision,
            "allowed_files": list(allowed_files),
            "mutation_mode": mutation_mode,
        },
        **extra,
    }


def test_direct_gpt_vs_overlapping_rdc_worker():
    # Main GPT direct mutation on controller vs RDC delegated worker overlapping on same file
    direct_gpt = _writer(
        "task-gpt",
        ["nexus/services/direct_operation_journal.py"],
        mutation_mode="DIRECT_CANONICAL",
    )
    rdc_worker = _writer(
        "task-rdc",
        ["nexus/services/direct_operation_journal.py"],
        mutation_mode="DIRECT_DELEGATED",
    )

    res = evaluate_cross_entrypoint_conflict(
        direct_gpt, [rdc_worker], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["schema"] == MUTATION_CONFLICT_SCHEMA
    assert res["claim_ceiling"] == MUTATION_CONFLICT_CLAIM_CEILING
    assert res["disposition"] == CONFLICT_OVERLAP
    assert res["conflicting_writers"]


def test_rdc_worker_vs_local_writer_overlapping_domain():
    # RDC worker vs Local worker overlapping normalized domain
    rdc_worker = _writer(
        "task-rdc",
        ["nexus/engine/capability_planner.py"],
        mutation_mode="DIRECT_DELEGATED",
    )
    local_writer = _writer(
        "task-local",
        ["nexus/engine"],  # parent dir overlaps file
        mutation_mode="LOCAL",
    )

    res = evaluate_cross_entrypoint_conflict(
        local_writer, [rdc_worker], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_OVERLAP


def test_governed_target_vs_direct_mutation():
    # Governed isolated Target vs direct mutation overlapping domain
    governed = _writer(
        "task-gov",
        ["nexus/orchestrator/worktree_manager.py"],
        mutation_mode="ISOLATED_TARGET",
    )
    direct = _writer(
        "task-direct",
        ["nexus/orchestrator/worktree_manager.py"],
        mutation_mode="DIRECT_CANONICAL",
    )

    res = evaluate_cross_entrypoint_conflict(
        governed, [direct], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_OVERLAP


def test_disjoint_mutation_domains_allows_clear():
    # Disjoint paths across direct, delegated, and isolated writers
    direct_gpt = _writer(
        "task-gpt",
        ["nexus/services/auth.py"],
        mutation_mode="DIRECT_CANONICAL",
    )
    rdc_worker = _writer(
        "task-rdc",
        ["nexus/engine/planner.py"],
        mutation_mode="DIRECT_DELEGATED",
    )
    isolated_target = _writer(
        "task-gov",
        ["nexus/orchestrator/queue.py"],
        mutation_mode="ISOLATED_TARGET",
    )

    res = evaluate_cross_entrypoint_conflict(
        direct_gpt,
        [rdc_worker, isolated_target],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert res["disposition"] == CONFLICT_CLEAR
    assert res["active_writer_count"] == 2
    assert res["normalized_domain"] == ["nexus/services/auth.py"]


def test_stale_writer_identity_fails_closed():
    base_rev = "a" * 40
    stale_rev = "b" * 40

    cand = _writer("task-1", ["nexus/a.py"], controller_revision=base_rev)
    stale_active = _writer("task-2", ["nexus/b.py"], controller_revision=stale_rev)

    # Writer stale against expected revision
    res = evaluate_cross_entrypoint_conflict(
        cand, [stale_active], expected_revision=base_rev, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_STALE

    # Candidate stale against expected revision
    res_cand_stale = evaluate_cross_entrypoint_conflict(
        cand,
        [stale_active],
        expected_revision="c" * 40,
        inventory_complete=True,
    )
    assert res_cand_stale["disposition"] == CONFLICT_STALE


def test_unresolved_unknown_prior_effect_fails_closed():
    cand_unknown = _writer(
        "task-1",
        ["nexus/a.py"],
        unknown_effect_refs=["unconfirmed_git_push"],
    )
    res = evaluate_cross_entrypoint_conflict(
        cand_unknown, [], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert res["reason"] == "CANDIDATE_UNRESOLVED_PRIOR_EFFECTS"

    cand_clean = _writer("task-clean", ["nexus/a.py"])
    active_with_unknown = _writer(
        "task-active",
        ["nexus/b.py"],
        unresolved_effects=True,
    )
    res_active = evaluate_cross_entrypoint_conflict(
        cand_clean,
        [active_with_unknown],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert res_active["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert res_active["reason"] == "ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS"


def test_missing_or_corrupt_active_writer_fails_closed_to_unknown():
    cand = _writer("task-1", ["nexus/a.py"])
    res = evaluate_cross_entrypoint_conflict(
        cand, [None], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "ACTIVE_WRITER_MISSING_OR_CORRUPT"


def test_worktree_manager_methods_and_cleanup_isolation(tmp_path: Path):
    manager = WorktreeManager(root_dir=tmp_path / "targets", create_root=True)

    cand = _writer("task-1", ["nexus/a.py"])
    other = _writer("task-2", ["nexus/b.py"])

    # evaluate_admission and readback_conflict_state with explicit expected_revision
    adm = manager.evaluate_admission(
        cand, [other], expected_revision="a" * 40, inventory_complete=True
    )
    assert adm["disposition"] == CONFLICT_CLEAR

    rb = manager.readback_conflict_state(
        cand, [other], expected_revision="a" * 40, inventory_complete=True
    )
    assert rb["disposition"] == CONFLICT_CLEAR
    assert rb["schema"] == MUTATION_CONFLICT_SCHEMA

    # Overlap readback
    overlap_writer = _writer("task-3", ["nexus/a.py"])
    rb_overlap = manager.readback_conflict_state(
        cand, [overlap_writer], expected_revision="a" * 40, inventory_complete=True
    )
    assert rb_overlap["disposition"] == CONFLICT_OVERLAP


def test_missing_writer_inventory_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"])
    # Passing active_writers=None must fail closed to UNKNOWN, never default to empty list/CLEAR
    res = evaluate_cross_entrypoint_conflict(
        cand, active_writers=None, expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "ACTIVE_WRITER_INVENTORY_MISSING"

    manager = WorktreeManager()
    res_mgr = manager.evaluate_admission(
        cand, active_writers=None, expected_revision="a" * 40, inventory_complete=True
    )
    assert res_mgr["disposition"] == CONFLICT_UNKNOWN
    assert res_mgr["reason"] == "ACTIVE_WRITER_INVENTORY_MISSING"


def test_empty_proven_inventory_vs_unknown_inventory():
    cand = _writer("task-1", ["nexus/a.py"])
    # Proven empty inventory with current revision yields CLEAR
    res_proven = evaluate_cross_entrypoint_conflict(
        cand, active_writers=[], expected_revision="a" * 40, inventory_complete=True
    )
    assert res_proven["disposition"] == CONFLICT_CLEAR
    assert res_proven["active_writer_count"] == 0

    # Missing inventory yields UNKNOWN
    res_unknown = evaluate_cross_entrypoint_conflict(
        cand, active_writers=None, expected_revision="a" * 40, inventory_complete=True
    )
    assert res_unknown["disposition"] == CONFLICT_UNKNOWN


def test_missing_expected_revision_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"])
    # Missing expected_revision fails closed
    res = evaluate_cross_entrypoint_conflict(
        cand, active_writers=[], expected_revision=None, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "EXPECTED_REVISION_REQUIRED_FOR_ADMISSION"


def test_stale_all_writers_snapshot_fails_closed():
    # Both candidate and writer have same stale revision b*40, while current expected is a*40
    cand = _writer("task-1", ["nexus/a.py"], controller_revision="b" * 40)
    writer = _writer("task-2", ["nexus/b.py"], controller_revision="b" * 40)

    # Even though both writers match each other, both are stale compared to current expected revision
    res = evaluate_cross_entrypoint_conflict(
        cand, [writer], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_STALE
    assert res["reason"].startswith("CANDIDATE_REVISION_STALE")


def test_unsupported_mutation_lane_fails_closed():
    # Attempting to pass a transport name as a mutation authority lane
    cand_rdc = _writer("task-1", ["nexus/a.py"], mutation_mode="RDC")
    res = evaluate_cross_entrypoint_conflict(
        cand_rdc, active_writers=[], expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res["reason"]

    # Candidate valid, but writer uses pseudo lane
    cand_valid = _writer("task-1", ["nexus/a.py"], mutation_mode="DIRECT_CANONICAL")
    writer_dev_mcp = _writer("task-2", ["nexus/b.py"], mutation_mode="DEV_MCP")
    res2 = evaluate_cross_entrypoint_conflict(
        cand_valid, [writer_dev_mcp], expected_revision="a" * 40, inventory_complete=True
    )
    assert res2["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res2["reason"]


def test_readback_conflict_state_controller_unavailable_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"], controller_worktree="/nonexistent/controller")
    manager = WorktreeManager()
    res = manager.readback_conflict_state(
        cand, active_writers=None, expected_revision="a" * 40, inventory_complete=True
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "CANONICAL_READBACK_CONTROLLER_UNAVAILABLE"


def test_target_only_or_unproven_empty_inventory_never_clears():
    cand = _writer("task-1", ["nexus/a.py"])
    manager = WorktreeManager()

    incomplete = manager.evaluate_admission(
        cand,
        active_writers=[],
        expected_revision="a" * 40,
        inventory_complete=False,
    )
    assert incomplete["disposition"] == CONFLICT_UNKNOWN
    assert incomplete["reason"] == "CROSS_ENTRYPOINT_INVENTORY_INCOMPLETE"

    proven = manager.evaluate_admission(
        cand,
        active_writers=[],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert proven["disposition"] == CONFLICT_CLEAR


def test_missing_candidate_or_writer_lane_fails_closed():
    cand = _writer("task-cand", ["nexus/a.py"])
    cand["mutation_mode"] = ""
    cand["contract"]["mutation_mode"] = ""
    res = evaluate_cross_entrypoint_conflict(
        cand,
        [],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res["reason"]

    valid = _writer("task-valid", ["nexus/a.py"], mutation_mode="DIRECT_CANONICAL")
    writer = _writer("task-writer", ["nexus/b.py"])
    writer["mutation_mode"] = ""
    writer["contract"]["mutation_mode"] = ""
    res2 = evaluate_cross_entrypoint_conflict(
        valid,
        [writer],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert res2["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res2["reason"]


def test_same_task_attempt_stale_writer_cannot_skip_revision_gate():
    cand = _writer(
        "task-same",
        ["nexus/a.py"],
        attempt_id="attempt-same",
        controller_revision="a" * 40,
    )
    stale = _writer(
        "task-same",
        ["nexus/a.py"],
        attempt_id="attempt-same",
        controller_revision="b" * 40,
    )
    res = evaluate_cross_entrypoint_conflict(
        cand,
        [stale],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert res["disposition"] == CONFLICT_STALE
    assert res["reason"].startswith("WRITER_REVISION_STALE")


def test_inventory_complete_requires_literal_true():
    cand = _writer("task-1", ["nexus/a.py"])
    for non_true in (False, "False", "true", 1, 0, [], {}):
        res = evaluate_cross_entrypoint_conflict(
            cand,
            [],
            expected_revision="a" * 40,
            inventory_complete=non_true,
        )
        assert res["disposition"] == CONFLICT_UNKNOWN
        assert res["reason"] == "CROSS_ENTRYPOINT_INVENTORY_INCOMPLETE"


@pytest.mark.parametrize(
    "paths",
    [
        [],
        ["../escape.py"],
        ["/absolute.py"],
        ["scope", "scope/a.py"],
    ],
)
def test_same_attempt_writer_still_requires_valid_mutation_domain(paths):
    candidate = _writer(
        "task-same",
        ["scope/a.py"],
        attempt_id="attempt-same",
        controller_revision="a" * 40,
    )
    writer = _writer(
        "task-same",
        paths,
        attempt_id="attempt-same",
        controller_revision="a" * 40,
    )
    result = evaluate_cross_entrypoint_conflict(
        candidate,
        [writer],
        expected_revision="a" * 40,
        inventory_complete=True,
    )
    assert result["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert result["reason"].startswith("WRITER_PATHS_MALFORMED:")


def test_existing_direct_canonical_guard_remains_fail_closed():
    direct = _writer(
        "task-direct",
        ["src/direct.py"],
        mutation_mode="DIRECT_CANONICAL",
    )
    isolated = _writer(
        "task-isolated",
        ["other/isolated.py"],
        mutation_mode="ISOLATED_TARGET",
    )
    assert mutation_domains_conflict(direct, isolated) is True
    assert mutation_domains_conflict(isolated, direct) is True


def _make_git_repo(path: Path) -> tuple[Path, str]:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@nexus.local"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Nexus Test"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    (path / "src").mkdir(parents=True, exist_ok=True)
    (path / "src" / "base.py").write_text("# base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    return path, head


def _bind_canonical_producer_root(
    monkeypatch: pytest.MonkeyPatch,
    *,
    env_name: str,
    canonical_attr: str,
    root: Path,
) -> None:
    resolved = root.resolve()
    monkeypatch.setenv(env_name, str(resolved))
    monkeypatch.setattr(provenance_module, canonical_attr, resolved)


def test_live_dev_mcp_vs_rdc_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    rdc_root = tmp_path / "rdc"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_RDC_OPERATION_ROOT",
        canonical_attr="_CANONICAL_RDC_OPERATION_ROOT",
        root=rdc_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-mcp",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-mcp",
            "allowed_files": ["src/shared.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    rdc_cand = _writer(
        "task-rdc",
        ["src/shared.py"],
        mutation_mode="DIRECT_DELEGATED",
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(rdc_cand)
    assert res["schema"] == MUTATION_CONFLICT_SCHEMA
    assert res["claim_ceiling"] == MUTATION_CONFLICT_CLAIM_CEILING
    assert res["disposition"] == CONFLICT_OVERLAP
    assert res["reason"] == "MUTATION_DOMAINS_OVERLAP"
    assert any(w["task_id"] == "task-mcp" for w in res["conflicting_writers"])


def test_live_rdc_vs_local_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    rdc_root = tmp_path / "rdc"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_RDC_OPERATION_ROOT",
        canonical_attr="_CANONICAL_RDC_OPERATION_ROOT",
        root=rdc_root,
    )

    journal = DirectOperationJournal(
        rdc_root,
        schema=PRODUCER_SCHEMA_RDC_V1,
        operation_prefix="rdcop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-rdc",
        cwd=str(repo_path),
        provider="rdc",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-rdc",
            "allowed_files": ["src/engine"],
            "mutation_mode": "DIRECT_DELEGATED",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    local_cand = _writer(
        "task-local",
        ["src/engine/planner.py"],
        mutation_mode="LOCAL",
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(local_cand)
    assert res["disposition"] == CONFLICT_OVERLAP
    assert any(w["task_id"] == "task-rdc" for w in res["conflicting_writers"])


def test_live_target_lease_blocked_by_active_dev_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-dev",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-dev",
            "allowed_files": ["src/module.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    target_root = tmp_path / "targets"
    target_repo = target_root / "task-target"
    manager = WorktreeManager(root_dir=str(target_root), create_root=True)
    contract = SelfHostedTaskContract(
        task_id="task-target",
        objective="Modify overlapping module",
        controller_revision=head_sha,
        target_base_revision=head_sha,
        controller_repo_root=str(repo_path),
        target_repo_root=str(target_repo),
        target_worktree_root=str(target_root),
        allowed_files=["src/module.py"],
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
    )

    with pytest.raises(RuntimeError, match="MUTATION_CONFLICT_BLOCKED:OVERLAP"):
        manager.create_lease(contract)

    # 0 physical mutation effects: worktree was never created
    assert not target_repo.exists()


def test_live_disjoint_multiple_entrypoints_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    rdc_root = tmp_path / "rdc"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_RDC_OPERATION_ROOT",
        canonical_attr="_CANONICAL_RDC_OPERATION_ROOT",
        root=rdc_root,
    )

    # Dev MCP on src/dev.py
    dev_journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op1 = dev_journal.new_operation_id()
    dev_journal.create(
        operation_id=op1,
        attempt_id="att-1",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-dev",
            "allowed_files": ["src/dev.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    dev_journal.mark_started(op1, pid=os.getpid())

    # RDC on src/rdc.py
    rdc_journal = DirectOperationJournal(
        rdc_root,
        schema=PRODUCER_SCHEMA_RDC_V1,
        operation_prefix="rdcop_",
    )
    op2 = rdc_journal.new_operation_id()
    rdc_journal.create(
        operation_id=op2,
        attempt_id="att-2",
        cwd=str(repo_path),
        provider="rdc",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-rdc",
            "allowed_files": ["src/rdc.py"],
            "mutation_mode": "DIRECT_DELEGATED",
        },
    )
    rdc_journal.mark_started(op2, pid=os.getpid())

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        mutation_mode="ISOLATED_TARGET",
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_CLEAR
    assert res["reason"] == "DISJOINT_AND_VALID"
    assert res["active_writer_count"] == 2


def test_live_corrupt_operation_record_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    corrupt_dir = dev_mcp_root / "operations" / "devmcpop_corrupt"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    # Corrupt JSON with repo_root matching
    (corrupt_dir / "operation.json").write_text(
        f'{{"repo_root": "{repo_path}", invalid_json: }}', encoding="utf-8"
    )

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/any.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert "CORRUPT_CANONICAL_OPERATION_RECORD_DETECTED" in res["reason"]


def test_live_missing_operation_json_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    # Empty directory without operation.json
    empty_op_dir = dev_mcp_root / "operations" / "devmcpop_empty"
    empty_op_dir.mkdir(parents=True, exist_ok=True)

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/any.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert "CORRUPT_CANONICAL_OPERATION_RECORD_DETECTED" in res["reason"]


def test_live_configured_missing_dev_mcp_producer_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    missing_root = tmp_path / "missing-dev-mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=missing_root,
    )

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/any.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert "CANONICAL_PRODUCER_ROOT_UNAVAILABLE" in res["reason"]


def test_live_schema_shaped_record_with_invalid_operation_identity_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    forged_dir = dev_mcp_root / "operations" / "devmcpop_not-a-valid-id"
    forged_dir.mkdir(parents=True, exist_ok=True)
    (forged_dir / "operation.json").write_text(
        (
            '{"schema":"nexus.dev_mcp.receipt.v1",'
            '"operation_id":"devmcpop_not-a-valid-id",'
            '"attempt_id":"att-forged","status":"RUNNING",'
            f'"repo_root":"{repo_path}","pid":{os.getpid()},'
            f'"last_heartbeat_at":"{datetime.datetime.now(datetime.timezone.utc).isoformat()}",'
            '"allowed_files":["src/any.py"]}'
        ),
        encoding="utf-8",
    )

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert "CORRUPT_CANONICAL_OPERATION_RECORD_DETECTED" in res["reason"]


def test_live_configured_local_writer_without_canonical_producer_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    local_root = tmp_path / "local-writers"
    local_root.mkdir()
    monkeypatch.setenv("NEXUS_LOCAL_WRITER_ROOT", str(local_root))

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert "LOCAL_WRITER_CANONICAL_PRODUCER_UNAVAILABLE" in res["reason"]


def test_live_process_silence_without_terminal_receipt_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-dead",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-dead",
            "allowed_files": ["src/dead.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    # Bind a non-existent dead PID
    dead_pid = 9999999
    journal.update(op_id, status="RUNNING", pid=dead_pid)

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert "PROCESS_SILENCE_WITHOUT_TERMINAL_RECEIPT" in res["reason"]


def test_live_stale_heartbeat_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-stale-hb",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-stale-hb",
            "allowed_files": ["src/stale.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    # Stale heartbeat (500s ago)
    old_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=500)
    ).isoformat()
    journal.update(op_id, status="RUNNING", pid=os.getpid(), last_heartbeat_at=old_time)

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_STALE
    assert "ACTIVE_STALE_HEARTBEAT" in res["reason"]


def test_live_outcome_unknown_operation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-unknown",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-unknown",
            "allowed_files": ["src/unknown.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_terminal(op_id, status="OUTCOME_UNKNOWN", exit_code=None)

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/other.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert "ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS" in res["reason"]


def test_live_terminal_completed_operation_does_not_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )

    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-done",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-done",
            "allowed_files": ["src/shared.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_terminal(op_id, status="COMPLETED", exit_code=0)

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/shared.py"],
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_CLEAR
    assert res["active_writer_count"] == 0


def test_live_governed_target_vs_dev_mcp_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    target_root = tmp_path / "targets"
    manager = WorktreeManager(root_dir=str(target_root), create_root=True)

    contract_target = SelfHostedTaskContract(
        task_id="task-gov",
        objective="Governed target work",
        controller_revision=head_sha,
        target_base_revision=head_sha,
        controller_repo_root=str(repo_path),
        target_repo_root=str(target_root / "task-gov"),
        target_worktree_root=str(target_root),
        allowed_files=["src/base.py"],
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
    )
    manager.create_lease(contract_target)

    # Dev MCP candidate targeting same file src/base.py
    dev_mcp_cand = _writer(
        "task-dev-cand",
        ["src/base.py"],
        mutation_mode="DIRECT_CANONICAL",
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(dev_mcp_cand)
    assert res["disposition"] == CONFLICT_OVERLAP
    assert any(w["task_id"] == "task-gov" for w in res["conflicting_writers"])


def test_live_agy_operation_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    agy_root = tmp_path / "agy"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_AGY_OPERATION_ROOT",
        canonical_attr="_CANONICAL_AGY_OPERATION_ROOT",
        root=agy_root,
    )

    journal = DirectOperationJournal(
        agy_root,
        schema=PRODUCER_SCHEMA_AGY_OPERATION_V1,
        operation_prefix="agyop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-agy",
        cwd=str(repo_path),
        provider="agy",
        model="gemini-3.8-flash",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-agy",
            "allowed_files": ["src/agy_shared.py"],
            "mutation_mode": "DIRECT_DELEGATED",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    manager = WorktreeManager(root_dir=str(tmp_path / "targets"), create_root=True)
    cand = _writer(
        "task-cand",
        ["src/agy_shared.py"],
        mutation_mode="ISOLATED_TARGET",
        controller_revision=head_sha,
        controller_worktree=str(repo_path),
    )

    res = manager.readback_conflict_state(cand)
    assert res["disposition"] == CONFLICT_OVERLAP
    assert any(w["task_id"] == "task-agy" for w in res["conflicting_writers"])


def test_bridge_conflict_validation_missing_contract_fails_closed(tmp_path: Path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        ephemeral=True,
        auto_reconcile=False,
    )
    with pytest.raises(
        RuntimeError,
        match="MUTATION_CONFLICT_BLOCKED:PROVIDER_INVOKE:UNKNOWN:MUTATION_CONTRACT_UNAVAILABLE",
    ):
        service._bridge_validate_mutation_conflict(
            "missing-task",
            "attempt-01",
            None,
            operation="PROVIDER_INVOKE",
        )


def test_bridge_conflict_validation_missing_controller_root_fails_closed(tmp_path: Path):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        ephemeral=True,
        auto_reconcile=False,
    )
    contract = {
        "task_id": "task-missing-root",
        "controller_repo_root": str(tmp_path / "does-not-exist"),
        "controller_revision": "a" * 40,
        "allowed_files": ["src/a.py"],
        "mutation_mode": "ISOLATED_TARGET",
    }
    with pytest.raises(
        RuntimeError,
        match="MUTATION_CONFLICT_BLOCKED:FINALIZE_COMPLETED:UNKNOWN:CONTROLLER_ROOT_UNAVAILABLE",
    ):
        service._bridge_validate_mutation_conflict(
            "task-missing-root",
            "attempt-01",
            contract,
            operation="FINALIZE_COMPLETED",
        )


def test_runtime_coordination_bridge_worker_invoke_blocked_on_mutation_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    target_root = tmp_path / "targets"
    target_repo = target_root / "task-worker-test"

    contract = SelfHostedTaskContract(
        task_id="task-worker-test",
        objective="Worker test",
        controller_revision=head_sha,
        target_base_revision=head_sha,
        controller_repo_root=str(repo_path),
        target_repo_root=str(target_repo),
        target_worktree_root=str(target_root),
        allowed_files=["src/base.py"],
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
    )

    manager = WorktreeManager(root_dir=str(target_root), create_root=True)
    lease = manager.create_lease(contract)

    service._write_state(
        "task-worker-test",
        {
            "task_id": "task-worker-test",
            "attempt_id": "attempt-01",
            "status": "TARGET_LEASED",
            "contract": contract.model_dump(mode="json"),
            "lease": lease.__dict__,
        },
    )

    # Now create an overlapping Dev MCP active writer on src/base.py
    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-mcp",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-mcp",
            "allowed_files": ["src/base.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    worker_called = []

    def mock_invoke(*args, **kwargs):
        worker_called.append(True)
        return object()

    monkeypatch.setattr(service.worker_registry, "invoke", mock_invoke)

    # Worker invocation must be blocked before calling worker_registry.invoke!
    from nexus.orchestrator.runtime_coordination_bridge import _Worker

    worker_adapter = _Worker(service)
    with pytest.raises(RuntimeError, match="MUTATION_CONFLICT_BLOCKED:PROVIDER_INVOKE:OVERLAP"):
        worker_adapter.invoke("codex", contract, lease)

    assert len(worker_called) == 0


def test_runtime_coordination_bridge_finalize_blocked_on_mutation_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from nexus.orchestrator.runtime_coordination_bridge import _Finalization
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    repo_path, head_sha = _make_git_repo(tmp_path / "repo")
    dev_mcp_root = tmp_path / "dev_mcp"
    _bind_canonical_producer_root(
        monkeypatch,
        env_name="NEXUS_DEV_MCP_OPERATION_ROOT",
        canonical_attr="_CANONICAL_DEV_MCP_OPERATION_ROOT",
        root=dev_mcp_root,
    )
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(tmp_path / "targets"))

    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", ephemeral=True, auto_reconcile=False
    )
    target_root = tmp_path / "targets"
    target_repo = target_root / "task-fin-test"

    contract = SelfHostedTaskContract(
        task_id="task-fin-test",
        objective="Finalize test",
        controller_revision=head_sha,
        target_base_revision=head_sha,
        controller_repo_root=str(repo_path),
        target_repo_root=str(target_repo),
        target_worktree_root=str(target_root),
        allowed_files=["src/base.py"],
        forbidden_files=[],
        verifier_commands=[],
        protected_contracts=[],
    )

    manager = WorktreeManager(root_dir=str(target_root), create_root=True)
    lease = manager.create_lease(contract)

    service._write_state(
        "task-fin-test",
        {
            "task_id": "task-fin-test",
            "attempt_id": "attempt-01",
            "status": "WORKER_COMPLETED",
            "contract": contract.model_dump(mode="json"),
            "lease": lease.__dict__,
        },
    )

    # Create overlapping Dev MCP writer
    journal = DirectOperationJournal(
        dev_mcp_root,
        schema=PRODUCER_SCHEMA_DEV_MCP_V1,
        operation_prefix="devmcpop_",
    )
    op_id = journal.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id="att-mcp-fin",
        cwd=str(repo_path),
        provider="dev_mcp",
        model="gpt-test",
        effort="high",
        prompt_sha256="abcd" * 16,
        runtime_revision=head_sha,
        initial_fields={
            "task_id": "task-mcp-fin",
            "allowed_files": ["src/base.py"],
            "mutation_mode": "DIRECT_CANONICAL",
        },
    )
    journal.mark_started(op_id, pid=os.getpid())

    fin = _Finalization(
        service,
        task_id="task-fin-test",
        attempt_id="attempt-01",
    )

    finalized_called = []

    def mock_finalize(*args, **kwargs):
        finalized_called.append(True)
        return {}

    monkeypatch.setattr(service, "_finalize_runtime_candidate", mock_finalize)

    with pytest.raises(RuntimeError, match="MUTATION_CONFLICT_BLOCKED:FINALIZE_COMPLETED:OVERLAP"):
        fin.finalize_completed(
            contract,
            {},
            lease,
            service._read_state("task-fin-test"),
            1,
            execution=object(),
            status="WORKER_COMPLETED",
        )

    assert len(finalized_called) == 0
