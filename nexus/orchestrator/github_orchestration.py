"""Pure reducer/preparer: no provider, subprocess, network, or merge calls."""

from __future__ import annotations

from datetime import datetime, timezone

from nexus.contracts.autonomy_goal import StandingGrantContext
from nexus.contracts.github_orchestration import (
    GitHubOrchestrationEvidence,
    MainMovementDimensionResult,
    MainMovementEvidence,
    MainMovementRequalification,
    MergeIntent,
    canonical_hash,
)
from nexus.orchestrator.autonomy_policy import (
    StandingGrantOutcome,
    StandingGrantRequest,
    evaluate_standing_grant_decision,
)
from nexus.orchestrator.standing_grant_store import (
    StandingGrantReceiptError,
    _load_receipt_at,
    load_standing_grant_receipt,
)


def requalify_main_movement(
    evidence: GitHubOrchestrationEvidence,
    movement: MainMovementEvidence,
) -> MainMovementRequalification:
    """Classify main movement against one verified Candidate evidence packet.

    The function only projects which evidence dimensions must be rechecked.
    Existing impact, repository-contract, GitHub-evidence, review, check, CAS,
    and merge gates remain the authorities that decide integration.
    """
    evidence = _safe(evidence, GitHubOrchestrationEvidence)
    movement = _safe(movement, MainMovementEvidence)
    unknown_reasons: list[str] = []
    if (
        evidence.base_sha != movement.old_main_sha
        or evidence.current_main_sha != movement.old_main_sha
        or evidence.head_sha != movement.candidate_head_sha
        or evidence.tree_sha != movement.candidate_tree_sha
        or evidence.diff_hash != movement.candidate_diff_hash
        or tuple(evidence.changed_paths) != tuple(movement.candidate_changed_paths)
        or evidence.impact_hash != movement.prior_impact_hash
        or evidence.verifier_hash != movement.prior_verifier_hash
    ):
        unknown_reasons.append("candidate_evidence_identity_or_digest_tamper")

    # Reuse the canonical exact-base classifier.  A malformed/unreadable
    # impact universe is intentionally converted to IMPACT_UNKNOWN here.
    try:
        from scripts.ops.pr_impact_gate import build_impact_plan

        plan = build_impact_plan(
            list(movement.changed_main_paths),
            base_sha=movement.old_main_sha,
            head_sha=movement.new_main_sha,
        )
        impact_unknown = plan.impact_class == "IMPACT_UNKNOWN" or bool(plan.unmatched_paths)
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        plan = None
        impact_unknown = True
        unknown_reasons.append(f"impact_classifier_unavailable:{type(exc).__name__}")

    candidate_paths = set(movement.candidate_changed_paths)
    main_paths = set(movement.changed_main_paths)
    direct_overlap = bool(candidate_paths & main_paths)
    semantic_overlap = direct_overlap or bool(
        plan is not None and plan.impact_class == "HIGH_RISK_INTEGRATION"
        and any(path.startswith(("nexus/", "scripts/")) for path in candidate_paths)
    )
    test_impact = any(
        path.startswith("tests/")
        or path in {"pyproject.toml", "uv.lock", "pytest.ini", "pyrightconfig.json", "ruff.toml"}
        for path in main_paths
    )
    from nexus.orchestrator.repository_contract_gate import RepositoryContractGate

    authority_paths = tuple(
        path for path in main_paths
        if RepositoryContractGate._drift_kind(path) is not None
        or path in {"AGENTS.md", "MUSE_PROTO.md"}
        or path.startswith(("tasks/", "docs/agents/", "nexus/verifiers/"))
        or "merge" in path.lower()
        or "governance" in path.lower()
        or "authority" in path.lower()
        or "verifier" in path.lower()
    )
    transport_paths = tuple(
        path for path in main_paths
        if RepositoryContractGate._drift_kind(path) == "ci_workflow_authority_drift"
        or path.startswith((".github/workflows/", "scripts/ops/"))
        or any(token in path.lower() for token in ("provider", "transport", "mcp"))
    )

    def result(dimension: str, classification: str, affected: bool, reasons=()):
        if unknown_reasons and dimension in {"SOURCE_IDENTITY", "AUTHORITY_DRIFT"}:
            return MainMovementDimensionResult(
                dimension=dimension,
                classification="IMPACT_UNKNOWN",
                action="IMPACT_UNKNOWN",
                reasons=tuple(unknown_reasons),
            )
        if affected:
            return MainMovementDimensionResult(
                dimension=dimension,
                classification=classification,
                action="RECHECK_AFFECTED",
                reasons=tuple(reasons),
            )
        return MainMovementDimensionResult(
            dimension=dimension,
            classification="IRRELEVANT_MAIN_MOVEMENT",
            action="REUSE_UNAFFECTED",
            reasons=tuple(reasons),
        )

    dimensions = (
        result("SOURCE_IDENTITY", "SOURCE_IDENTITY_DRIFT", bool(unknown_reasons), unknown_reasons),
        result("SEMANTIC_OVERLAP", "SEMANTIC_OVERLAP", semantic_overlap, ("candidate path/dependency overlap",)),
        result("TEST_IMPACT", "TEST_IMPACT", test_impact, ("test inventory or dependency changed",)),
        result("AUTHORITY_DRIFT", "AUTHORITY_DRIFT", bool(authority_paths), tuple(authority_paths)),
        result("TRANSPORT_DRIFT", "TRANSPORT_DRIFT", bool(transport_paths), tuple(transport_paths)),
        result("IRRELEVANT_MAIN_MOVEMENT", "IRRELEVANT_MAIN_MOVEMENT", False),
    )
    if impact_unknown:
        dimensions = tuple(
            item if item.dimension in {"SOURCE_IDENTITY", "AUTHORITY_DRIFT", "SEMANTIC_OVERLAP"}
            else MainMovementDimensionResult(
                dimension=item.dimension, classification=item.classification,
                action=item.action, reasons=item.reasons,
            )
            for item in dimensions
        )
        dimensions = tuple(
            MainMovementDimensionResult(
                dimension=item.dimension,
                classification="IMPACT_UNKNOWN",
                action="IMPACT_UNKNOWN",
                reasons=("impact universe is unknown",),
            ) if item.dimension == "SEMANTIC_OVERLAP" else item
            for item in dimensions
        )
    blocked = bool(unknown_reasons or authority_paths or any(item.action == "IMPACT_UNKNOWN" for item in dimensions))
    return MainMovementRequalification(
        old_main_sha=movement.old_main_sha,
        new_main_sha=movement.new_main_sha,
        candidate_head_sha=movement.candidate_head_sha,
        candidate_tree_sha=movement.candidate_tree_sha,
        dimensions=dimensions,
        blocked=blocked,
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
    if not evidence.reviews_resolved:
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
    if decision.outcome is not StandingGrantOutcome.GRANT_MATCH or not decision.mutation_authorized:
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
    prepared = prepare_merge_intent(context, request, evidence, now=now)
    if intent != prepared:
        raise ValueError("INTENT_SEMANTIC_MISMATCH")
    return prepared


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


def resolve_durable_merge_authorization(
    intent,
    request,
    evidence,
    *,
    now: datetime | None = None,
    platform_approval_required: bool = False,
):
    """Revalidate exact merge evidence, then load the durable receipt and
    resolve the same evaluator decision.

    The durable receipt is only a carrier; the existing pure evaluator decides.
    A missing/tampered/malformed receipt fails closed to ``GRANT_INVALID``.
    A valid receipt that does not cover ``GITHUB_MERGE`` reports
    ``GRANT_OUT_OF_SCOPE``. Genuine external platform approval reports
    ``PLATFORM_APPROVAL_REQUIRED``, never a grant mismatch.
    """
    safe_request = _safe(request, StandingGrantRequest)
    effective_now = now or datetime.now(timezone.utc)
    try:
        receipt = load_standing_grant_receipt(now=effective_now)
    except StandingGrantReceiptError:
        return evaluate_action({}, {}, platform_approval_required=platform_approval_required)
    if receipt is None:
        return evaluate_action({}, {}, platform_approval_required=platform_approval_required)
    try:
        revalidate_merge_intent(intent, receipt.context, safe_request, evidence, now=effective_now)
    except ValueError as exc:
        # A receipt/context mismatch is a grant decision, not an evidence
        # failure. Keep evidence failures (drift, checks, reviews, acceptance)
        # as typed exceptions for the caller's fail-closed gate.
        if str(exc) not in {
            StandingGrantOutcome.INVALID.value,
            StandingGrantOutcome.OUT_OF_SCOPE.value,
        }:
            raise
    return evaluate_action(
        receipt.context,
        safe_request,
        platform_approval_required=platform_approval_required,
    )


def _resolve_durable_merge_authorization_at(
    intent,
    request,
    evidence,
    *,
    receipt_path,
    now: datetime | None = None,
    platform_approval_required: bool = False,
):
    """Test/internal-only variant bound to an explicit path (never production)."""
    safe_request = _safe(request, StandingGrantRequest)
    effective_now = now or datetime.now(timezone.utc)
    try:
        receipt = _load_receipt_at(receipt_path, now=effective_now)
    except StandingGrantReceiptError:
        return evaluate_action({}, {}, platform_approval_required=platform_approval_required)
    try:
        revalidate_merge_intent(intent, receipt.context, safe_request, evidence, now=effective_now)
    except ValueError as exc:
        if str(exc) not in {
            StandingGrantOutcome.INVALID.value,
            StandingGrantOutcome.OUT_OF_SCOPE.value,
        }:
            raise
    return evaluate_action(
        receipt.context,
        safe_request,
        platform_approval_required=platform_approval_required,
    )
