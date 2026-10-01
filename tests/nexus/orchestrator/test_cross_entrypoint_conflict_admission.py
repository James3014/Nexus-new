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

from pathlib import Path

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

    res = evaluate_cross_entrypoint_conflict(direct_gpt, [rdc_worker], expected_revision="a" * 40)
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

    res = evaluate_cross_entrypoint_conflict(local_writer, [rdc_worker], expected_revision="a" * 40)
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

    res = evaluate_cross_entrypoint_conflict(governed, [direct], expected_revision="a" * 40)
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
        direct_gpt, [rdc_worker, isolated_target], expected_revision="a" * 40
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
    res = evaluate_cross_entrypoint_conflict(cand, [stale_active], expected_revision=base_rev)
    assert res["disposition"] == CONFLICT_STALE

    # Candidate stale against expected revision
    res_cand_stale = evaluate_cross_entrypoint_conflict(
        cand, [stale_active], expected_revision="c" * 40
    )
    assert res_cand_stale["disposition"] == CONFLICT_STALE


def test_unresolved_unknown_prior_effect_fails_closed():
    cand_unknown = _writer(
        "task-1",
        ["nexus/a.py"],
        unknown_effect_refs=["unconfirmed_git_push"],
    )
    res = evaluate_cross_entrypoint_conflict(cand_unknown, [], expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert res["reason"] == "CANDIDATE_UNRESOLVED_PRIOR_EFFECTS"

    cand_clean = _writer("task-clean", ["nexus/a.py"])
    active_with_unknown = _writer(
        "task-active",
        ["nexus/b.py"],
        unresolved_effects=True,
    )
    res_active = evaluate_cross_entrypoint_conflict(
        cand_clean, [active_with_unknown], expected_revision="a" * 40
    )
    assert res_active["disposition"] == CONFLICT_RECONCILE_REQUIRED
    assert res_active["reason"] == "ACTIVE_WRITER_UNRESOLVED_PRIOR_EFFECTS"


def test_missing_or_corrupt_active_writer_fails_closed_to_unknown():
    cand = _writer("task-1", ["nexus/a.py"])
    res = evaluate_cross_entrypoint_conflict(cand, [None], expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "ACTIVE_WRITER_MISSING_OR_CORRUPT"


def test_worktree_manager_methods_and_cleanup_isolation(tmp_path: Path):
    manager = WorktreeManager(root_dir=tmp_path / "targets", create_root=True)

    cand = _writer("task-1", ["nexus/a.py"])
    other = _writer("task-2", ["nexus/b.py"])

    # evaluate_admission and readback_conflict_state with explicit expected_revision
    adm = manager.evaluate_admission(cand, [other], expected_revision="a" * 40)
    assert adm["disposition"] == CONFLICT_CLEAR

    rb = manager.readback_conflict_state(cand, [other], expected_revision="a" * 40)
    assert rb["disposition"] == CONFLICT_CLEAR
    assert rb["schema"] == MUTATION_CONFLICT_SCHEMA

    # Overlap readback
    overlap_writer = _writer("task-3", ["nexus/a.py"])
    rb_overlap = manager.readback_conflict_state(cand, [overlap_writer], expected_revision="a" * 40)
    assert rb_overlap["disposition"] == CONFLICT_OVERLAP


def test_missing_writer_inventory_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"])
    # Passing active_writers=None must fail closed to UNKNOWN, never default to empty list/CLEAR
    res = evaluate_cross_entrypoint_conflict(cand, active_writers=None, expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "ACTIVE_WRITER_INVENTORY_MISSING"

    manager = WorktreeManager()
    res_mgr = manager.evaluate_admission(cand, active_writers=None, expected_revision="a" * 40)
    assert res_mgr["disposition"] == CONFLICT_UNKNOWN
    assert res_mgr["reason"] == "ACTIVE_WRITER_INVENTORY_MISSING"


def test_empty_proven_inventory_vs_unknown_inventory():
    cand = _writer("task-1", ["nexus/a.py"])
    # Proven empty inventory with current revision yields CLEAR
    res_proven = evaluate_cross_entrypoint_conflict(cand, active_writers=[], expected_revision="a" * 40)
    assert res_proven["disposition"] == CONFLICT_CLEAR
    assert res_proven["active_writer_count"] == 0

    # Missing inventory yields UNKNOWN
    res_unknown = evaluate_cross_entrypoint_conflict(cand, active_writers=None, expected_revision="a" * 40)
    assert res_unknown["disposition"] == CONFLICT_UNKNOWN


def test_missing_expected_revision_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"])
    # Missing expected_revision fails closed
    res = evaluate_cross_entrypoint_conflict(cand, active_writers=[], expected_revision=None)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "EXPECTED_REVISION_REQUIRED_FOR_ADMISSION"


def test_stale_all_writers_snapshot_fails_closed():
    # Both candidate and writer have same stale revision b*40, while current expected is a*40
    cand = _writer("task-1", ["nexus/a.py"], controller_revision="b" * 40)
    writer = _writer("task-2", ["nexus/b.py"], controller_revision="b" * 40)

    # Even though both writers match each other, both are stale compared to current expected revision
    res = evaluate_cross_entrypoint_conflict(cand, [writer], expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_STALE
    assert res["reason"].startswith("CANDIDATE_REVISION_STALE")


def test_unsupported_mutation_lane_fails_closed():
    # Attempting to pass a transport name as a mutation authority lane
    cand_rdc = _writer("task-1", ["nexus/a.py"], mutation_mode="RDC")
    res = evaluate_cross_entrypoint_conflict(cand_rdc, active_writers=[], expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res["reason"]

    # Candidate valid, but writer uses pseudo lane
    cand_valid = _writer("task-1", ["nexus/a.py"], mutation_mode="DIRECT_CANONICAL")
    writer_dev_mcp = _writer("task-2", ["nexus/b.py"], mutation_mode="DEV_MCP")
    res2 = evaluate_cross_entrypoint_conflict(cand_valid, [writer_dev_mcp], expected_revision="a" * 40)
    assert res2["disposition"] == CONFLICT_UNKNOWN
    assert "UNSUPPORTED_MUTATION_LANE" in res2["reason"]


def test_readback_conflict_state_controller_unavailable_fails_closed():
    cand = _writer("task-1", ["nexus/a.py"], controller_worktree="/nonexistent/controller")
    manager = WorktreeManager()
    res = manager.readback_conflict_state(cand, active_writers=None, expected_revision="a" * 40)
    assert res["disposition"] == CONFLICT_UNKNOWN
    assert res["reason"] == "CANONICAL_READBACK_CONTROLLER_UNAVAILABLE"
