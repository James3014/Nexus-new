"""Verifier-eligible replay gate design v0."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class VerifierReplayDecisionKind(Enum):
    ELIGIBLE_FOR_VERIFIER_REPLAY = "ELIGIBLE_FOR_VERIFIER_REPLAY"
    NOT_ELIGIBLE_SOURCE_UNAVAILABLE = "NOT_ELIGIBLE_SOURCE_UNAVAILABLE"
    NOT_ELIGIBLE_SOURCE_PREFIXED = "NOT_ELIGIBLE_SOURCE_PREFIXED"
    NOT_ELIGIBLE_SYMBOL_NOT_FOUND = "NOT_ELIGIBLE_SYMBOL_NOT_FOUND"
    NOT_ELIGIBLE_AMBIGUOUS_SYMBOL = "NOT_ELIGIBLE_AMBIGUOUS_SYMBOL"
    NOT_ELIGIBLE_SOURCE_STALE = "NOT_ELIGIBLE_SOURCE_STALE"
    NOT_ELIGIBLE_AST_INVALID = "NOT_ELIGIBLE_AST_INVALID"
    NOT_ELIGIBLE_PATCH_INTENT_INVALID = "NOT_ELIGIBLE_PATCH_INTENT_INVALID"
    NOT_ELIGIBLE_PREVIEW_FAILED = "NOT_ELIGIBLE_PREVIEW_FAILED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass
class VerifierReplayDecision:
    task_id: str
    model: str
    decision_kind: VerifierReplayDecisionKind
    eligible: bool
    reason: str
    required_preconditions: list
    failed_preconditions: list
    governance: dict
    recommended_next_action: str


def evaluate_verifier_replay_eligibility(replay_result: dict) -> VerifierReplayDecision:
    task_id = replay_result.get("task_id", "unknown")
    model = replay_result.get("model", "unknown")
    required = [
        "source_available",
        "ast_locator_ok",
        "symbol_found",
        "hash_verified",
        "patch_intent_representable",
        "preview_ast_valid",
    ]
    failed = []

    if not replay_result.get("source_available"):
        failed.append("source_available")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_SOURCE_UNAVAILABLE, False, "source not available", required, failed, _governance(), "obtain source or skip")

    ast = replay_result.get("ast_locator_result", {})
    if ast.get("status") == "error":
        error_kind = ast.get("error_kind", "")
        if "SYMBOL_NOT_FOUND" in error_kind:
            failed.append("symbol_found")
            return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_SYMBOL_NOT_FOUND, False, f"symbol not found: {error_kind}", required, failed, _governance(), "check source or use different symbol")
        if "AMBIGUOUS" in error_kind:
            failed.append("symbol_found")
            return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_AMBIGUOUS_SYMBOL, False, f"ambiguous symbol", required, failed, _governance(), "disambiguate symbol")
        failed.append("ast_locator_ok")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_SOURCE_PREFIXED, False, f"source pre-fixed or drifted: {error_kind}", required, failed, _governance(), "check source state")

    if not ast.get("span_start"):
        failed.append("symbol_found")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_SYMBOL_NOT_FOUND, False, "symbol not found in AST", required, failed, _governance(), "check source")

    guard = replay_result.get("source_hash_guard_result", {})
    if not guard.get("hash_verified"):
        failed.append("hash_verified")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_SOURCE_STALE, False, "hash mismatch", required, failed, _governance(), "refresh source hash")

    preview = replay_result.get("preview_result", {})
    if not preview.get("preview_ok"):
        failed.append("preview_ast_valid")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_AST_INVALID, False, "preview ast invalid", required, failed, _governance(), "fix replacement")

    if not preview.get("ast_valid"):
        failed.append("preview_ast_valid")
        return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.NOT_ELIGIBLE_PREVIEW_FAILED, False, "preview ast check failed", required, failed, _governance(), "fix replacement")

    return VerifierReplayDecision(task_id, model, VerifierReplayDecisionKind.ELIGIBLE_FOR_VERIFIER_REPLAY, True, "all preconditions met", required, [], _governance(), "proceed with verifier replay")


def _governance() -> dict:
    return {
        "verifier_run": False,
        "m6_executed": False,
        "training_export": False,
        "public_claim_allowed": False,
    }
