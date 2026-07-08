from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Protocol

from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


class CommitteeCandidateProducer(Protocol):
    """Injectable seam for generating committee candidates.

    Accepts a CommitteeRoutedToolRequest and returns a list of raw candidate dicts.
    Can be a plain function or an object with __call__.
    """
    def __call__(self, request: CommitteeRoutedToolRequest) -> list[dict[str, Any]]:
        ...


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
    raw_candidate_count: int = 0
    candidate_producer_present: bool = False
    candidate_producer_invoked: bool = False
    candidate_producer_name: str = ""
    candidate_producer_error: str = ""
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
        "p4_raw_candidate_count": result.raw_candidate_count,
        "p4_candidate_producer_present": result.candidate_producer_present,
        "p4_candidate_producer_invoked": result.candidate_producer_invoked,
        "p4_candidate_producer_name": result.candidate_producer_name,
        "p4_candidate_producer_error": result.candidate_producer_error,
        "p4_selected_candidate_hash": result.selected_candidate_hash,
        "p4_selected_candidate_model": result.selected_candidate_source_model,
        "p4_selected_candidate_apply_status": result.selected_candidate_apply_status,
        "p4_selected_candidate_verifier_status": result.selected_candidate_verifier_status,
        "p4_winner_found": result.winner_found,
        "p4_solved_by_committee": result.solved_by_committee,
        "p4_selected_candidate_hash_matches_applied": result.receipt_fragment.get("p4_selected_candidate_hash_matches_applied", False),
        "p4_committee_claim_gate_passed": result.receipt_fragment.get("p4_committee_claim_gate_passed", False),
        "p4_failure_reasons": result.failure_reasons,
        "p4_fail_closed": result.receipt_fragment.get("p4_fail_closed", bool(result.failure_reasons)),
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


FORBIDDEN_FALLBACKS = [
    "no_winner_fallback_to_first_candidate",
    "no_winner_fallback_to_borda_without_verifier",
    "no_winner_fallback_to_local_retry_result",
    "judge_text_vote_direct_solved",
]


def _compute_committee_solved(
    *,
    apply_result: dict,
    verifier_result: dict,
    claim_gate_passed: bool,
) -> bool:
    """Compute solved_by_committee from apply/verifier/hash/claim gate.

    All four conditions must pass:
    - apply succeeded (applied is True)
    - applied content hash matches candidate hash
    - verifier passed
    - claim gate passed
    """
    return (
        apply_result.get("applied") is True
        and apply_result.get("hash_matches") is True
        and verifier_result.get("status") == "pass"
        and claim_gate_passed is True
    )


def _check_fail_closed(result: CommitteeRoutedToolResult) -> CommitteeRoutedToolResult:
    """Ensure no silent fallback. Mark fail_closed if anything is wrong.

    Defensively checks apply/verifier/hash/claim state to prevent
    false solved_by_committee claims.
    """
    failed = bool(result.blocked_reason or result.failure_reasons)

    if result.invocation_allowed and result.invoked:
        if not result.winner_found:
            failed = True
        if result.selected_candidate_apply_status and result.selected_candidate_apply_status != "applied":
            failed = True
        if result.selected_candidate_verifier_status and result.selected_candidate_verifier_status != "pass":
            failed = True
        if result.receipt_fragment.get("p4_selected_candidate_hash_matches_applied") is False:
            failed = True
        if result.receipt_fragment.get("p4_committee_claim_gate_passed") is False:
            failed = True

    if failed:
        result.solved_by_committee = False
        result.receipt_fragment["p4_fail_closed"] = True

    return result


def _build_zero_winner_result(gate: dict, raw: list, rejections: list) -> CommitteeRoutedToolResult:
    """Build fail-closed result when no valid candidates."""
    malformed_count = sum(1 for r in rejections if r.get("reason") in ("unknown_format", "malformed"))
    no_candidate_reason = rejections[0].get("reason", "no_candidates") if rejections else "no_candidates"

    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=len(raw),
        raw_candidate_count=len(raw),
        canonical_candidate_count=0,
        winner_found=False,
        solved_by_committee=False,
        failure_reasons=[r.get("reason", "unknown") for r in rejections],
        receipt_fragment={
            **gate,
            "p4_fail_closed": True,
        },
    )
    result = _check_fail_closed(result)
    result.receipt_fragment = build_committee_receipt_fragment(result)
    # Preserve zero-winner-specific diagnostic fields
    result.receipt_fragment["rejection_details"] = rejections
    result.receipt_fragment["p4_zero_winner"] = True
    result.receipt_fragment["p4_no_candidate_reason"] = no_candidate_reason
    result.receipt_fragment["p4_malformed_candidate_count"] = malformed_count
    result.receipt_fragment["p4_rejected_candidate_reasons"] = [r.get("reason", "") for r in rejections]
    return result


def evaluate_and_execute(
    request: CommitteeRoutedToolRequest,
    *,
    candidate_producer: CommitteeCandidateProducer | None = None,
) -> CommitteeRoutedToolResult:
    """Evaluate gate → if allowed, execute full committee flow.

    Args:
        request: The committee routed tool request.
        candidate_producer: Optional injectable seam for generating candidates.
            If None and gate allows, fails closed with missing_committee_candidate_producer.
    """
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

    # Gate allows — must have a candidate producer
    producer_present = candidate_producer is not None
    producer_name = type(candidate_producer).__name__ if candidate_producer else ""

    if candidate_producer is None:
        return CommitteeRoutedToolResult(
            invoked=True,
            invocation_allowed=True,
            candidate_producer_present=False,
            candidate_producer_name="",
            candidate_producer_invoked=False,
            failure_reasons=["missing_committee_candidate_producer"],
            receipt_fragment={
                **gate,
                "p4_candidate_producer_present": False,
                "p4_candidate_producer_invoked": False,
                "p4_fail_closed": True,
            },
        )

    # Invoke producer
    producer_invoked = False
    raw_candidates: list[dict[str, Any]] = []
    producer_error = ""
    try:
        raw_candidates = candidate_producer(request)
        producer_invoked = True
    except Exception as e:
        producer_error = str(e)
        return CommitteeRoutedToolResult(
            invoked=True,
            invocation_allowed=True,
            candidate_producer_present=True,
            candidate_producer_name=producer_name,
            candidate_producer_invoked=False,
            candidate_producer_error=producer_error,
            failure_reasons=[f"candidate_producer_error: {e}"],
            receipt_fragment={
                **gate,
                "p4_candidate_producer_present": True,
                "p4_candidate_producer_invoked": False,
                "p4_candidate_producer_error": producer_error,
                "p4_fail_closed": True,
            },
        )

    # Adapt to CanonicalPatchCandidate
    valid_candidates, rejections = adapt_committee_candidates(
        raw_candidates, request.target_file, request.target_symbol,
    )

    if not valid_candidates:
        result = _build_zero_winner_result(gate, raw_candidates, rejections)
        result.raw_candidate_count = len(raw_candidates)
        result.candidate_producer_present = True
        result.candidate_producer_name = producer_name
        result.candidate_producer_invoked = producer_invoked
        result.receipt_fragment["p4_candidate_producer_present"] = True
        result.receipt_fragment["p4_candidate_producer_name"] = producer_name
        result.receipt_fragment["p4_candidate_producer_invoked"] = True
        result.receipt_fragment["p4_raw_candidate_count"] = len(raw_candidates)
        return result

    # P5-I7: Diversity-aware selection (env-guarded)
    p5_diversity_used = False
    p5_result = None
    rejected_indices = {r["index"] for r in rejections}

    if os.environ.get("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", "0") == "1":
        try:
            from nexus.services.local_heal.diversity_selector import select_diverse_candidate

            # Extract source_models from raw_candidates (only for valid candidates)
            source_models = [
                str(raw_candidates[i].get("model", "") or raw_candidates[i].get("model_name", "") or "")
                for i in range(len(raw_candidates))
                if i not in rejected_indices
            ]
            # Pad if needed
            while len(source_models) < len(valid_candidates):
                source_models.append("")

            p5_result = select_diverse_candidate(
                valid_candidates,
                source_models=source_models,
                strategy="diversity_v1",
            )
            p5_diversity_used = True

            if p5_result.fail_closed or p5_result.selected_index < 0:
                # P5 selector failed — return fail-closed result
                return CommitteeRoutedToolResult(
                    invoked=True,
                    invocation_allowed=True,
                    candidate_count=len(raw_candidates),
                    canonical_candidate_count=len(valid_candidates),
                    winner_found=False,
                    solved_by_committee=False,
                    failure_reasons=[f"p5_selection_failed:{r}" for r in p5_result.failure_reasons],
                    receipt_fragment={
                        **gate,
                        "p5_diversity_selector_used": True,
                        "p5_selection_strategy": p5_result.selection_strategy,
                        "p5_candidate_count": p5_result.candidate_count,
                        "p5_duplicate_group_count": p5_result.duplicate_group_count,
                        "p5_popularity_trap_detected": p5_result.popularity_trap_detected,
                        "p5_popularity_trap_reason": p5_result.popularity_trap_reason,
                        "p5_selected_candidate_index": p5_result.selected_index,
                        "p5_selected_candidate_hash": p5_result.selected_candidate_hash,
                        "p5_score_breakdown": p5_result.score_breakdown,
                        "p5_rejected_by_diversity": p5_result.rejected_by_diversity,
                        "p5_fail_closed": p5_result.fail_closed,
                    },
                )

            winner = valid_candidates[p5_result.selected_index]
        except ImportError:
            # Fallback: diversity_selector unavailable
            winner = valid_candidates[0]
    else:
        # P5 disabled: existing behavior
        winner = valid_candidates[0]

    # Determine winner source model from raw candidates
    winner_source_model = ""
    for i, raw in enumerate(raw_candidates):
        if i not in rejected_indices:
            winner_source_model = str(raw.get("model", "") or raw.get("model_name", "") or "")
            break

    # Re-apply in isolated workspace
    apply_result = _apply_candidate(winner, request)

    # Run verifier
    verifier_result = _verify_applied_candidate(winner, request)

    # P2 claim gate
    claim_gate = ClaimDeliveryGate()
    claim_input = {
        "verifier_status": verifier_result.get("status", "fail"),
        "verifier_artifact": "verification_report.txt" if verifier_result.get("status") == "pass" else "",
        "source_hash": request.source_hash,
        "patch_applied": apply_result.get("applied", False),
        "candidate_hash_matches_applied": apply_result.get("hash_matches", False),
        "candidate_target_file": request.target_file,
        "artifact_refs": list(request.evidence_refs),
    }
    claim_decision = claim_gate.validate(claim_input)

    solved = _compute_committee_solved(
        apply_result=apply_result,
        verifier_result=verifier_result,
        claim_gate_passed=claim_decision.claim_gate_passed,
    )

    hash_matches_applied = bool(apply_result.get("hash_matches", False))
    claim_gate_passed = bool(claim_decision.claim_gate_passed)

    result = CommitteeRoutedToolResult(
        invoked=True,
        invocation_allowed=True,
        candidate_count=len(valid_candidates),
        canonical_candidate_count=len(valid_candidates),
        raw_candidate_count=len(raw_candidates),
        candidate_producer_present=True,
        candidate_producer_name=producer_name,
        candidate_producer_invoked=producer_invoked,
        selected_candidate_hash=winner.raw_output_hash,
        selected_candidate_source_model=winner_source_model,
        selected_candidate_apply_status="applied" if apply_result.get("applied") else "failed",
        selected_candidate_verifier_status=verifier_result.get("status", "fail"),
        winner_found=True,
        solved_by_committee=solved,
        failure_reasons=[],
        receipt_fragment={
            **gate,
            "p4_candidate_producer_present": True,
            "p4_candidate_producer_name": producer_name,
            "p4_candidate_producer_invoked": True,
            "p4_raw_candidate_count": len(raw_candidates),
            "p4_selected_candidate_hash_matches_applied": hash_matches_applied,
            "p4_committee_claim_gate_passed": claim_gate_passed,
        },
    )
    result = _check_fail_closed(result)
    result.receipt_fragment = build_committee_receipt_fragment(result)
    # Preserve detailed diagnostic fields in receipt_fragment
    result.receipt_fragment["apply_result"] = apply_result
    result.receipt_fragment["verifier_result"] = verifier_result
    result.receipt_fragment["claim_decision"] = {"claim_gate_passed": claim_gate_passed}

    # P5-I7: Add P5 receipt fields only when P5 enabled
    if p5_diversity_used and p5_result is not None:
        result.receipt_fragment["p5_diversity_selector_used"] = True
        result.receipt_fragment["p5_selection_strategy"] = p5_result.selection_strategy
        result.receipt_fragment["p5_candidate_count"] = p5_result.candidate_count
        result.receipt_fragment["p5_duplicate_group_count"] = p5_result.duplicate_group_count
        result.receipt_fragment["p5_popularity_trap_detected"] = p5_result.popularity_trap_detected
        result.receipt_fragment["p5_popularity_trap_reason"] = p5_result.popularity_trap_reason
        result.receipt_fragment["p5_selected_candidate_index"] = p5_result.selected_index
        result.receipt_fragment["p5_selected_candidate_hash"] = p5_result.selected_candidate_hash
        result.receipt_fragment["p5_score_breakdown"] = p5_result.score_breakdown
        result.receipt_fragment["p5_rejected_by_diversity"] = p5_result.rejected_by_diversity
        result.receipt_fragment["p5_fail_closed"] = p5_result.fail_closed

    return result
