from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any

from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


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


def _apply_candidate(candidate: CanonicalPatchCandidate, request: CommitteeRoutedToolRequest) -> dict:
    """Isolated workspace apply. Returns status dict."""
    if not request.mutation_allowed:
        return {"applied": False, "hash_matches": False, "error": "mutation_not_allowed"}

    try:
        target_path = os.path.join(request.repo_root, request.target_file)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Write candidate patch content
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(candidate.normalized_patch)

        # Compute hash of applied content
        applied_hash = hashlib.sha256(candidate.normalized_patch.encode("utf-8")).hexdigest()
        hash_matches = (applied_hash == candidate.raw_output_hash)

        return {"applied": True, "hash_matches": hash_matches, "error": ""}
    except Exception as e:
        return {"applied": False, "hash_matches": False, "error": str(e)}


def _verify_applied_candidate(candidate: CanonicalPatchCandidate, request: CommitteeRoutedToolRequest) -> dict:
    """Run verifier on applied candidate. Returns status dict."""
    if not request.verifier_allowed:
        return {"status": "skip", "reason": "verifier_not_allowed"}

    # For now, basic verification: check file exists and is non-empty
    try:
        target_path = os.path.join(request.repo_root, request.target_file)
        if not os.path.exists(target_path):
            return {"status": "fail", "reason": "file_not_found"}

        with open(target_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            return {"status": "fail", "reason": "empty_file"}

        # Basic syntax check for Python files
        if request.target_file.endswith(".py"):
            try:
                compile(content, target_path, "exec")
            except SyntaxError as e:
                return {"status": "fail", "reason": f"syntax_error: {e}"}

        return {"status": "pass", "reason": "basic_checks_passed"}
    except Exception as e:
        return {"status": "fail", "reason": str(e)}


def _build_zero_winner_result(gate: dict, raw: list, rejections: list) -> CommitteeRoutedToolResult:
    """Build fail-closed result when no valid candidates."""
    return CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=len(raw),
        canonical_candidate_count=0,
        winner_found=False,
        solved_by_committee=False,
        failure_reasons=[r.get("reason", "unknown") for r in rejections],
        receipt_fragment={
            **gate,
            "rejection_details": rejections,
        },
    )


def evaluate_and_execute(request: CommitteeRoutedToolRequest) -> CommitteeRoutedToolResult:
    """Evaluate gate → if allowed, execute full committee flow."""
    from nexus.services.local_heal.committee_activation_gate import (
        CommitteeActivationInput,
        evaluate_committee_activation,
    )
    from nexus.services.local_heal.committee_candidate_adapter import adapt_committee_candidates
    from nexus.services.local_heal.claim_delivery_gate import ClaimDeliveryGate

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

    # P4-I5: Generate candidates via committee provider (stub for now)
    # In production, this would call LocalCommitteeCandidateProvider
    raw_candidates = []

    # Adapt to CanonicalPatchCandidate
    valid_candidates, rejections = adapt_committee_candidates(
        raw_candidates, request.target_file, request.target_symbol,
    )

    if not valid_candidates:
        return _build_zero_winner_result(gate, raw_candidates, rejections)

    # Select winner (first valid for now — no diversity engine)
    winner = valid_candidates[0]

    # Re-apply in isolated workspace
    apply_result = _apply_candidate(winner, request)

    # Run verifier
    verifier_result = _verify_applied_candidate(winner, request)

    # P2 claim gate
    claim_gate = ClaimDeliveryGate()
    claim_input = {
        "verifier_status": verifier_result.get("status", "fail"),
        "source_hash": request.source_hash,
        "patch_applied": apply_result.get("applied", False),
        "candidate_hash_matches_applied": apply_result.get("hash_matches", False),
        "candidate_target_file": request.target_file,
        "artifact_refs": list(request.evidence_refs),
    }
    claim_decision = claim_gate.validate(claim_input)

    return CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=len(raw_candidates),
        canonical_candidate_count=len(valid_candidates),
        selected_candidate_hash=winner.candidate_id,
        selected_candidate_source_model=winner.source_format,
        selected_candidate_apply_status="applied" if apply_result.get("applied") else "failed",
        selected_candidate_verifier_status=verifier_result.get("status", "fail"),
        winner_found=True,
        solved_by_committee=(
            apply_result.get("applied", False)
            and verifier_result.get("status") == "pass"
            and apply_result.get("hash_matches", False)
            and claim_decision.claim_gate_passed
        ),
        failure_reasons=[],
        receipt_fragment={
            **gate,
            "apply_result": apply_result,
            "verifier_result": verifier_result,
            "claim_decision": {
                "claim_gate_passed": claim_decision.claim_gate_passed,
            },
        },
    )
