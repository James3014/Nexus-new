from __future__ import annotations

from scripts.ops.fast_start_v2 import (
    affected_entries_for_event,
    decide_reconcile,
    sha256_json,
)


def test_pr_479_only_impacts_129() -> None:
    hint = affected_entries_for_event(
        "pull_request_target",
        {
            "action": "synchronize",
            "number": 479,
            "pull_request": {"number": 479, "head": {"sha": "a" * 40}},
        },
        changed_paths=["nexus/orchestrator/self_hosted_task_service.py"],
    )
    assert hint.affected_entries == (129,)
    assert "DIRECT_PR_INPUT" in hint.reason_codes
    assert "PATH_OVERLAP" in hint.reason_codes


def test_pr_403_dependency_and_path_deduplicate_92() -> None:
    hint = affected_entries_for_event(
        "pull_request_target",
        {
            "action": "synchronize",
            "number": 403,
            "pull_request": {"number": 403, "head": {"sha": "b" * 40}},
        },
        changed_paths=["nexus/services/unified_runtime.py"],
    )
    assert hint.affected_entries == (92,)


def test_pr_402_only_impacts_419() -> None:
    hint = affected_entries_for_event(
        "pull_request_target",
        {
            "action": "closed",
            "number": 402,
            "pull_request": {"number": 402, "head": {"sha": "c" * 40}},
        },
        changed_paths=["AGENTS.md", "tests/ops/test_bootstrap_authority_files.py"],
    )
    assert hint.affected_entries == (419,)


def test_issue_29_only_impacts_92() -> None:
    hint = affected_entries_for_event(
        "issues", {"action": "closed", "issue": {"number": 29}}
    )
    assert hint.affected_entries == (92,)


def test_registry_self_comment_is_suppressed() -> None:
    hint = affected_entries_for_event(
        "issue_comment", {"action": "created", "issue": {"number": 549}}
    )
    assert hint.affected_entries == ()
    assert hint.reason_codes == ("REGISTRY_SELF_EVENT_SUPPRESSED",)


def test_readme_only_push_has_no_semantic_impact() -> None:
    hint = affected_entries_for_event(
        "push",
        {"ref": "refs/heads/main", "after": "d" * 40},
        changed_paths=["README.md"],
    )
    assert hint.affected_entries == ()
    assert hint.reason_codes == ("NO_RELEVANT_IMPACT",)


def test_agents_push_impacts_only_419() -> None:
    hint = affected_entries_for_event(
        "push",
        {"ref": "refs/heads/main", "after": "e" * 40},
        changed_paths=["AGENTS.md"],
    )
    assert hint.affected_entries == (419,)


def test_authority_bundle_path_impacts_only_526() -> None:
    hint = affected_entries_for_event(
        "push",
        {"ref": "refs/heads/main", "after": "f" * 40},
        changed_paths=[
            "tasks/github-issue-526-host-authority-and-canary-20260823/02-host-effect-authority-receipt.json"
        ],
    )
    assert hint.affected_entries == (526,)


def test_push_without_changed_paths_fails_closed_for_path_discovery() -> None:
    hint = affected_entries_for_event(
        "push", {"ref": "refs/heads/main", "after": "1" * 40}
    )
    assert hint.affected_entries == ()
    assert "PATH_IMPACT_DISCOVERY_REQUIRED" in hint.reason_codes


def test_blocked_head_change_is_targeted_rebind_with_zero_implementation_reads() -> None:
    decision = decide_reconcile(frontier_state="BLOCKED", dispatch_changed=True)
    assert decision.reconcile_action == "TARGETED_REBIND"
    assert decision.source_body_reads_allowed is False
    assert decision.test_body_reads_allowed is False


def test_contract_change_while_blocked_still_has_zero_implementation_reads() -> None:
    decision = decide_reconcile(frontier_state="BLOCKED", contract_changed=True)
    assert decision.reconcile_action == "FULL_REBUILD"
    assert decision.source_body_reads_allowed is False
    assert decision.test_body_reads_allowed is False


def test_dirty_implementation_context_is_deferred_while_blocked() -> None:
    decision = decide_reconcile(
        frontier_state="BLOCKED", implementation_dirty=True
    )
    assert decision.implementation_context == "DIRTY_DEFERRED"
    assert decision.source_body_reads_allowed is False


def test_host_frontier_is_orthogonal_to_cache_hit() -> None:
    decision = decide_reconcile(frontier_state="HOST_REBIND_REQUIRED")
    assert decision.reconcile_action == "CACHE_HIT"
    assert decision.frontier_state == "HOST_REBIND_REQUIRED"
    assert decision.source_body_reads_allowed is False


def test_missing_evidence_can_never_be_ready() -> None:
    decision = decide_reconcile(
        frontier_state="READY_CANDIDATE", evidence_complete=False
    )
    assert decision.frontier_state == "EVIDENCE_BLOCKED"
    assert decision.source_body_reads_allowed is False


def test_ready_candidate_is_only_frontier_that_allows_implementation_reads() -> None:
    decision = decide_reconcile(
        frontier_state="READY_CANDIDATE", implementation_dirty=True
    )
    assert decision.source_body_reads_allowed is True
    assert decision.test_body_reads_allowed is True
    assert decision.implementation_context == "DIRTY_REBIND_REQUIRED"


def test_hint_hash_is_deterministic() -> None:
    payload_a = {"b": [2, 1], "a": {"x": "y"}}
    payload_b = {"a": {"x": "y"}, "b": [2, 1]}
    assert sha256_json(payload_a) == sha256_json(payload_b)
