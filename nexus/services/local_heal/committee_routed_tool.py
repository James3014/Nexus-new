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
    execution_topology: str = ""
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


def evaluate_and_execute(request: CommitteeRoutedToolRequest) -> CommitteeRoutedToolResult:
    """Evaluate gate → if allowed, execute committee (stub for now)."""
    from nexus.services.local_heal.committee_activation_gate import (
        CommitteeActivationInput,
        evaluate_committee_activation,
    )

    # Build activation inputs from request
    inputs = CommitteeActivationInput(
        execution_topology=request.execution_topology,
        p3_route_status=request.p3_route_status,
        hard_case_escalation_recommended=bool(request.hard_case_escalation_reason),
        difficulty=request.difficulty,
        local_committee_enabled=True,
        proposer_specs=request.proposer_specs,
        judge_model=request.judge_model,
    )

    gate = evaluate_committee_activation(inputs)

    if not gate["invocation_allowed"]:
        return CommitteeRoutedToolResult(
            invoked=False,
            invocation_allowed=False,
            blocked_reason=gate["blocked_reason"],
            receipt_fragment=gate,
        )

    # P4-I4: Stub committee execution (no real provider yet)
    # P4-I5 will add actual candidate generation + selection
    return CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=0,
        canonical_candidate_count=0,
        winner_found=False,
        receipt_fragment=gate,
    )


def adapt_candidates(
    raw_candidates: list[dict],
    target_file: str,
    target_symbol: str,
) -> dict:
    """Adapt raw candidates to canonical. Returns result summary."""
    from nexus.services.local_heal.committee_candidate_adapter import adapt_committee_candidates

    valid, rejections = adapt_committee_candidates(raw_candidates, target_file, target_symbol)
    return {
        "raw_candidate_count": len(raw_candidates),
        "canonical_candidate_count": len(valid),
        "rejected_count": len(rejections),
        "rejection_reasons": [r.get("reason", "") for r in rejections],
        "candidate_hashes": [c.candidate_id for c in valid],
    }
