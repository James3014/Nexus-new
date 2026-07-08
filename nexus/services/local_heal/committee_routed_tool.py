from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommitteeRoutedToolRequest:
    task_id: str
    repo_root: str
    target_file: str
    target_symbol: str = ""
    locked_search: str = ""
    source_hash: str = ""
    difficulty: str = ""
    p3_route_status: str = ""
    hard_case_escalation_reason: str = ""
    evidence_refs: tuple[str, ...] = ()
    proposer_specs: list[dict[str, str]] = field(default_factory=list)
    judge_model: str = ""
    max_candidates: int = 3
    mutation_allowed: bool = True
    verifier_allowed: bool = True


@dataclass
class CommitteeRoutedToolResult:
    invoked: bool = False
    invocation_allowed: bool = False
    blocked_reason: str = ""
    candidate_count: int = 0
    canonical_candidate_count: int = 0
    selected_candidate_hash: str = ""
    selected_candidate_source_model: str = ""
    selected_candidate_apply_status: str = ""
    selected_candidate_verifier_status: str = ""
    winner_found: bool = False
    solved_by_committee: bool = False
    failure_reasons: list[str] = field(default_factory=list)
    receipt_fragment: dict[str, Any] = field(default_factory=dict)


def validate_committee_request(request: CommitteeRoutedToolRequest) -> list[str]:
    """Validate request — return list of failure reasons. Empty = valid."""
    failures = []
    if not request.target_file:
        failures.append("missing_target_file")
    if not request.proposer_specs or len(request.proposer_specs) < 2:
        failures.append("insufficient_proposer_specs")
    if not request.judge_model:
        failures.append("missing_judge_model")
    if not request.task_id:
        failures.append("missing_task_id")
    return failures


def build_committee_receipt_fragment(result: CommitteeRoutedToolResult) -> dict:
    """Build receipt fragment from tool result."""
    return {
        "p4_committee_invoked": result.invoked,
        "p4_committee_invocation_allowed": result.invocation_allowed,
        "p4_committee_blocked_reason": result.blocked_reason,
        "p4_committee_candidate_count": result.candidate_count,
        "p4_canonical_candidate_count": result.canonical_candidate_count,
        "p4_selected_candidate_hash": result.selected_candidate_hash,
        "p4_selected_candidate_model": result.selected_candidate_source_model,
        "p4_selected_candidate_apply_status": result.selected_candidate_apply_status,
        "p4_selected_candidate_verifier_status": result.selected_candidate_verifier_status,
        "p4_winner_found": result.winner_found,
        "p4_solved_by_committee": result.solved_by_committee,
        "p4_failure_reasons": result.failure_reasons,
        "p4_fail_closed": bool(result.failure_reasons),
    }
