"""Pure reducer/preparer: no provider, subprocess, network, or merge calls."""

from __future__ import annotations

from datetime import datetime, timezone

from nexus.contracts.autonomy_goal import StandingGrantContext
from nexus.contracts.github_orchestration import (
    GitHubOrchestrationEvidence,
    MergeIntent,
    canonical_hash,
)
from nexus.orchestrator.autonomy_policy import (
    StandingGrantOutcome,
    StandingGrantRequest,
    evaluate_standing_grant_decision,
)


def _safe(model, typ):
    try:
        return typ.model_validate(
            model.model_dump(mode="json") if hasattr(model, "model_dump") else model
        )
    except Exception as exc:
        raise ValueError("MALFORMED_INPUT") from exc


def evaluate_action(context, request, *, platform_approval_required: bool = False):
    """Return the one standing-grant decision for an exact GitHub action."""
    try:
        return evaluate_standing_grant_decision(
            _safe(context, StandingGrantContext),
            _safe(request, StandingGrantRequest),
            platform_approval_required=platform_approval_required,
        )
    except ValueError:
        return evaluate_standing_grant_decision({}, {})


def _check(evidence, now):
    if now < evidence.observed_at or now > evidence.fresh_until:
        raise ValueError("EVIDENCE_STALE")
    if not evidence.checks_passed:
        raise ValueError("CHECKS_FAILED_OR_MISSING")
    if not evidence.required_checks or any(
        not c.terminal or c.conclusion.lower() not in {"success", "passed"}
        for c in evidence.required_checks
    ):
        raise ValueError("CHECK_FAILED_OR_MISSING")
    if evidence.reviews and any(
        r.unresolved_threads or r.state.upper() in {"CHANGES_REQUESTED", "REQUESTED_CHANGES"}
        for r in evidence.reviews
    ):
        raise ValueError("REVIEW_UNRESOLVED")
    if evidence.impact and (not evidence.impact.known or not evidence.impact.regression_free):
        raise ValueError("IMPACT_UNKNOWN_OR_REGRESSION")
    if not evidence.independent_acceptance:
        raise ValueError("INDEPENDENT_ACCEPTANCE_MISSING")


def prepare_merge_intent(
    context, request, evidence: GitHubOrchestrationEvidence, *, now: datetime | None = None
) -> MergeIntent:
    evidence = _safe(evidence, GitHubOrchestrationEvidence)
    now = now or datetime.now(timezone.utc)
    _check(evidence, now)
    decision = evaluate_action(context, request)
    if (
        decision.outcome is not StandingGrantOutcome.GRANT_MATCH
        or not decision.mutation_authorized
    ):
        raise ValueError(decision.outcome.value)
    payload = {
        "schema": "nexus.github_merge_intent.v2",
        "kind": "MERGE_INTENT",
        "evidence": evidence.model_dump(mode="json"),
        "grant_outcome": "GRANT_MATCH",
        "mutation_authorized": False,
        "claim_ceiling": "m4_merge_eligible_and_intent_ready_only",
    }
    return MergeIntent.model_validate({**payload, "intent_hash": canonical_hash(payload)})


def revalidate_merge_intent(intent, context, request, evidence, *, now: datetime | None = None):
    intent = _safe(intent, MergeIntent)
    evidence = _safe(evidence, GitHubOrchestrationEvidence)
    if evidence != intent.evidence:
        raise ValueError("DRIFT_HEAD_BASE_MAIN_DIFF_CHECK_REVIEW_ISSUE_CANDIDATE_ACCEPTANCE_IMPACT")
    if intent.intent_hash != canonical_hash(
        intent.model_dump(mode="json", exclude={"intent_hash"})
    ):
        raise ValueError("INTENT_REPLAY_OR_TAMPER")
    return prepare_merge_intent(context, request, evidence, now=now)


def resolve_merge_authorization(
    intent,
    context,
    request,
    evidence,
    *,
    now: datetime | None = None,
    platform_approval_required: bool = False,
):
    """Revalidate exact merge evidence, then return its typed authority result."""
    revalidate_merge_intent(intent, context, request, evidence, now=now)
    return evaluate_action(
        context,
        request,
        platform_approval_required=platform_approval_required,
    )
