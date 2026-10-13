"""Nightly quarantine entry: tests/engine/test_capability_routing_contracts.py (#1924). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/engine/test_capability_routing_contracts.py",
    "disposition": "quarantine",
    "issue": "#1924",
    "cause": "capability-phase e2e expectations (plan membership, invoked/gate_passed/wall_time) drifted from the current capability planner; stale expectations, needs owner fix-or-delete decision",
    "tests": (
        "test_autoreason_receipt_requires_winner_and_exposes_tournament_context",
        "test_autoreason_success_status_counts_as_invoked_for_public_receipt",
        "test_core_gate_failed_receipts_count_as_fail_closed_outcomes_not_public_safe",
        "test_core_gate_receipts_require_specific_evidence_before_public_claim",
        "test_ddtree_receipt_requires_real_candidate_pruning",
        "test_knowledge_receipts_keep_signals_separate_from_public_evidence",
        "test_msa_receipts_become_public_safe_with_executor_evidence",
        "test_trace_receipts_promote_only_invoked_evidence_and_gate_chain",
    ),
}
