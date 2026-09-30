"""Pure reducer/preparer: no provider, subprocess, network, or merge calls."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from nexus.contracts.autonomy_goal import StandingGrantContext
from nexus.contracts.github_orchestration import (
    CandidateLineage,
    CheckResult,
    GitHubOrchestrationEvidence,
    ImpactResult,
    MainMovementDimensionResult,
    MainMovementEvidence,
    MainMovementRequalification,
    MergeIntent,
    ReviewResult,
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
    *,
    root: Path | None = None,
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

    try:
        from scripts.ops.pr_impact_gate import verify_exact_git_main_movement_paths

        git_proof = verify_exact_git_main_movement_paths(
            old_main_sha=movement.old_main_sha,
            old_main_tree_sha=movement.old_main_tree_sha,
            new_main_sha=movement.new_main_sha,
            new_main_tree_sha=movement.new_main_tree_sha,
            changed_main_paths=movement.changed_main_paths,
            root=root,
        )
        if not git_proof.get("valid"):
            unknown_reasons.extend(git_proof.get("reasons", ["physical_git_path_proof_failed"]))
            proven_main_paths = set(movement.changed_main_paths)
        else:
            proven_main_paths = set(git_proof.get("proven_paths", ()))
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        unknown_reasons.append(f"physical_git_verifier_unavailable:{type(exc).__name__}")
        proven_main_paths = set(movement.changed_main_paths)

    # Reuse the canonical exact-base classifier.  A malformed/unreadable
    # impact universe is intentionally converted to IMPACT_UNKNOWN here.
    try:
        from scripts.ops.pr_impact_gate import build_impact_plan

        plan_kwargs = {"root": root} if root is not None else {}
        plan = build_impact_plan(
            list(proven_main_paths),
            base_sha=movement.old_main_sha,
            head_sha=movement.new_main_sha,
            **plan_kwargs,
        )
        impact_unknown = plan.impact_class == "IMPACT_UNKNOWN" or bool(plan.unmatched_paths)
    except Exception as exc:  # pragma: no cover - defensive fail-closed boundary
        plan = None
        impact_unknown = True
        unknown_reasons.append(f"impact_classifier_unavailable:{type(exc).__name__}")

    candidate_paths = set(movement.candidate_changed_paths)
    main_paths = proven_main_paths
    direct_overlap = bool(candidate_paths & main_paths)
    semantic_overlap = direct_overlap or bool(
        plan is not None
        and plan.impact_class == "HIGH_RISK_INTEGRATION"
        and any(path.startswith(("nexus/", "scripts/")) for path in candidate_paths)
    )
    test_impact = any(
        path.startswith("tests/")
        or path in {"pyproject.toml", "uv.lock", "pytest.ini", "pyrightconfig.json", "ruff.toml"}
        for path in main_paths
    )
    from nexus.orchestrator.repository_contract_gate import RepositoryContractGate

    authority_paths = tuple(
        path
        for path in main_paths
        if RepositoryContractGate._drift_kind(path) is not None
        or path in {"AGENTS.md", "MUSE_PROTO.md"}
        or path.startswith(("tasks/", "docs/agents/", "nexus/verifiers/"))
        or "merge" in path.lower()
        or "governance" in path.lower()
        or "authority" in path.lower()
        or "verifier" in path.lower()
    )
    transport_paths = tuple(
        path
        for path in main_paths
        if RepositoryContractGate._drift_kind(path) == "ci_workflow_authority_drift"
        or path.startswith((".github/workflows/", "scripts/ops/"))
        or any(token in path.lower() for token in ("provider", "transport", "mcp"))
    )

    def result(dimension: str, classification: str, affected: bool, reasons=()):
        if unknown_reasons:
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
        result(
            "SEMANTIC_OVERLAP",
            "SEMANTIC_OVERLAP",
            semantic_overlap,
            ("candidate path/dependency overlap",),
        ),
        result(
            "TEST_IMPACT", "TEST_IMPACT", test_impact, ("test inventory or dependency changed",)
        ),
        result("AUTHORITY_DRIFT", "AUTHORITY_DRIFT", bool(authority_paths), tuple(authority_paths)),
        result("TRANSPORT_DRIFT", "TRANSPORT_DRIFT", bool(transport_paths), tuple(transport_paths)),
        result("IRRELEVANT_MAIN_MOVEMENT", "IRRELEVANT_MAIN_MOVEMENT", False),
    )
    if impact_unknown and not unknown_reasons:
        dimensions = tuple(
            MainMovementDimensionResult(
                dimension=item.dimension,
                classification="IMPACT_UNKNOWN",
                action="IMPACT_UNKNOWN",
                reasons=("impact universe is unknown",),
            )
            if item.dimension == "SEMANTIC_OVERLAP"
            else item
            for item in dimensions
        )
    blocked = bool(
        unknown_reasons
        or authority_paths
        or any(item.action == "IMPACT_UNKNOWN" for item in dimensions)
    )
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
        receipt = load_standing_grant_receipt(
            now=effective_now,
            repository=safe_request.repository,
            goal_id=safe_request.goal_id,
            thread_id=safe_request.thread_id,
        )
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


_MERGE_LANE_BLOCK_RE = re.compile(
    r"<!--\s*NEXUS_MERGE_LANE_V1\s*\n(.*?)\nNEXUS_MERGE_LANE_V1\s*-->",
    re.DOTALL,
)
_BACKTICK_SHA_RE = re.compile(r"`([0-9a-f]{40,64})`")
_PATH_BULLET_RE = re.compile(r"^\s*-\s+`?([^`]+?)`?\s*$")
_TASK_ID_RE = re.compile(r"^task_id:\s*`?([^`\s]+)`?\s*$", re.MULTILINE)


class GovernedEvidenceProjectionError(ValueError):
    """Typed fail-closed error for governed evidence compatibility projection."""


def _projection_error(code: str) -> GovernedEvidenceProjectionError:
    return GovernedEvidenceProjectionError(code)


def _sha256_bytes(value: bytes) -> str:
    if not isinstance(value, bytes) or not value:
        raise _projection_error("SUBJECT_IDENTITY_MISMATCH")
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: bytes, *, missing_code: str) -> Mapping[str, Any]:
    if not isinstance(value, bytes) or not value:
        raise _projection_error(missing_code)
    try:
        payload = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _projection_error(missing_code) from exc
    if not isinstance(payload, dict):
        raise _projection_error(missing_code)
    return payload


def _parse_merge_lane_binding(pr_body: str) -> Mapping[str, Any]:
    if not isinstance(pr_body, str):
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    matches = _MERGE_LANE_BLOCK_RE.findall(pr_body)
    if len(matches) != 1:
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise _projection_error("MERGE_LANE_BINDING_INVALID") from exc
    if not isinstance(payload, dict):
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    binding_hash = payload.get("binding_hash")
    unsigned = {key: value for key, value in payload.items() if key != "binding_hash"}
    if (
        payload.get("schema") != "nexus.merge_lane_binding.v1"
        or payload.get("execution_lane") != "GOVERNED"
        or not isinstance(binding_hash, str)
        or canonical_hash(unsigned) != binding_hash
    ):
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    return payload


def governed_evidence_task_card_path(pr_body: str) -> str:
    """Return the Task Card path from the canonical merge-lane binding."""
    payload = _parse_merge_lane_binding(pr_body)
    path = payload.get("task_card_path")
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    return path


def _parse_task_card(task_card_bytes: bytes) -> tuple[str, tuple[str, ...], str]:
    try:
        text = task_card_bytes.decode("utf-8")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise _projection_error("TASK_CARD_IDENTITY_MISSING") from exc
    task_match = _TASK_ID_RE.search(text)
    if not task_match:
        raise _projection_error("TASK_CARD_IDENTITY_MISSING")
    declared_lanes = re.findall(
        r"^execution_lane:\s*`?([A-Z_]+)`?\s*$",
        text,
        re.MULTILINE,
    )
    if len(declared_lanes) > 1 or (declared_lanes and declared_lanes[0] != "GOVERNED"):
        raise _projection_error("UNSUPPORTED_LEGACY_CONTRACT_GENERATION")

    sources: list[tuple[str, ...]] = []
    lines = text.splitlines()

    for index, line in enumerate(lines):
        if line.strip() != "allowed_files:":
            continue
        values: list[str] = []
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            match = _PATH_BULLET_RE.match(candidate)
            if match:
                path = match.group(1).strip()
                if path.startswith("/") or ".." in path.split("/"):
                    raise _projection_error("TASK_CARD_IDENTITY_MISSING")
                values.append(path)
                continue
            if not stripped:
                continue
            break
        if values:
            sources.append(tuple(sorted(set(values))))

    for index, line in enumerate(lines):
        if line.strip().lower() != "## allowed files":
            continue
        values = []
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if stripped.startswith("## "):
                break
            match = _PATH_BULLET_RE.match(candidate)
            if match:
                path = match.group(1).strip()
                if path.startswith("/") or ".." in path.split("/"):
                    raise _projection_error("TASK_CARD_IDENTITY_MISSING")
                values.append(path)
        if values:
            sources.append(tuple(sorted(set(values))))

    if not sources or any(source != sources[0] for source in sources[1:]):
        raise _projection_error("TASK_CARD_IDENTITY_MISSING")
    return (
        task_match.group(1),
        sources[0],
        hashlib.sha256(task_card_bytes).hexdigest(),
    )


def _require_subject(
    payload: Mapping[str, Any],
    *,
    repository: str,
    pull_request_number: int,
    base_sha: str,
    head_sha: str,
    tree_sha: str,
    diff_hash: str | None = None,
    status: str | None = None,
    error_code: str,
) -> None:
    identity = payload.get("workflow_identity")
    if not isinstance(identity, dict):
        raise _projection_error(error_code)
    if (
        identity.get("repository") != repository
        or identity.get("pull_request_number") != pull_request_number
        or identity.get("event_name") != "pull_request_target"
        or identity.get("default_branch") != "main"
        or identity.get("workflow_sha") != base_sha
        or not str(identity.get("workflow_ref", "")).endswith("@refs/heads/main")
        or payload.get("base_sha") != base_sha
        or payload.get("head_sha") != head_sha
        or payload.get("head_tree") != tree_sha
        or identity.get("run_id") != payload.get("run_id")
    ):
        raise _projection_error(error_code)
    if diff_hash is not None and payload.get("raw_diff_sha256") != diff_hash:
        raise _projection_error(error_code)
    if status is not None and payload.get("status") != status:
        raise _projection_error(error_code)


def _parse_legacy_acceptance(
    body: str,
    *,
    comment_id: int,
    author: str,
    base_sha: str,
    head_sha: str,
    tree_sha: str,
    card_hash: str,
) -> tuple[str, str]:
    if not isinstance(body, str) or not body.strip():
        raise _projection_error("INDEPENDENT_ACCEPTANCE_MISSING")

    def one(pattern: str) -> str:
        found = re.findall(pattern, body, re.IGNORECASE)
        if len(found) != 1:
            raise _projection_error("INDEPENDENT_ACCEPTANCE_SUBJECT_MISMATCH")
        return found[0]

    observed_base = one(r"base:\s*`([0-9a-f]{40})`")
    observed_head = one(r"head:\s*`([0-9a-f]{40})`")
    observed_tree = one(r"tree:\s*`([0-9a-f]{40})`")
    observed_card = one(r"Task Card SHA-256:\s*`([0-9a-f]{64})`")
    reviewer = one(r"(?:reviewer transport/session|reviewer session):[^`\n]*`([^`\n]+)`")
    output_hash = one(r"reviewer output SHA-256:\s*`([0-9a-f]{64})`")
    max_claim = one(r"(?:Maximum claim|max(?:imum)? claim):\s*`([^`]+)`")
    lower = body.lower()
    accepted = (
        "blockers: none" in lower or "accept_candidate" in lower or "accept candidate" in lower
    )
    if not accepted:
        raise _projection_error("INDEPENDENT_ACCEPTANCE_MISSING")
    if (observed_base, observed_head, observed_tree, observed_card) != (
        base_sha,
        head_sha,
        tree_sha,
        card_hash,
    ):
        raise _projection_error("INDEPENDENT_ACCEPTANCE_SUBJECT_MISMATCH")
    projection = {
        "schema": "nexus.legacy_independent_acceptance_projection.v1",
        "comment_id": comment_id,
        "comment_author": author,
        "base_sha": observed_base,
        "head_sha": observed_head,
        "tree_sha": observed_tree,
        "task_card_sha256": observed_card,
        "reviewer": reviewer,
        "reviewer_output_sha256": output_hash,
        "verdict": "ACCEPT",
        "maximum_claim": max_claim,
    }
    return reviewer, canonical_hash(projection)


def _project_required_checks(
    required_names: Sequence[str],
    observations: Sequence[Mapping[str, Any]],
    *,
    head_sha: str,
) -> tuple[CheckResult, ...]:
    names = tuple(sorted(set(str(name) for name in required_names if str(name).strip())))
    if not names:
        raise _projection_error("REQUIRED_CHECK_STATE_UNPROVEN")
    by_name: dict[str, Mapping[str, Any]] = {}
    for item in observations:
        name = item.get("name")
        if name not in names:
            continue
        if name in by_name:
            raise _projection_error("REQUIRED_CHECK_STATE_UNPROVEN")
        by_name[str(name)] = item
    if set(by_name) != set(names):
        raise _projection_error("REQUIRED_CHECK_STATE_UNPROVEN")
    projected: list[CheckResult] = []
    for name in names:
        item = by_name[name]
        if (
            item.get("head_sha") != head_sha
            or str(item.get("status", "")).lower() not in {"completed", "success", "passed"}
            or str(item.get("conclusion", "")).lower() not in {"success", "passed"}
        ):
            raise _projection_error("REQUIRED_CHECK_STATE_UNPROVEN")
        projected.append(
            CheckResult(
                name=name,
                status=str(item["status"]),
                conclusion=str(item["conclusion"]),
                terminal=True,
                head_sha=head_sha,
            )
        )
    return tuple(projected)


def _project_impact(
    plan: Mapping[str, Any],
    classification: Mapping[str, Any],
    *,
    base_sha: str,
    head_sha: str,
    tree_sha: str,
    changed_paths: tuple[str, ...],
) -> ImpactResult:
    if (
        plan.get("base_sha") != base_sha
        or plan.get("head_sha") != head_sha
        or plan.get("source_tree") != tree_sha
        or tuple(sorted(plan.get("changed_paths") or ())) != changed_paths
        or classification.get("blocking") is not False
        or classification.get("new_failures") not in ([], ())
        or str(classification.get("classification", "")).upper()
        in {"", "UNKNOWN", "IMPACT_UNKNOWN", "NEW_REGRESSION", "REGRESSION"}
    ):
        raise _projection_error("IMPACT_EVIDENCE_UNPROVEN")
    return ImpactResult(
        classification=str(classification["classification"]),
        known=True,
        regression_free=True,
    )


def build_governed_orchestration_evidence(
    *,
    repository: str,
    issue_number: int,
    pull_request_number: int,
    pr_body: str,
    task_card_path: str,
    task_card_bytes: bytes,
    controller_manifest_bytes: bytes,
    verifier_evidence_bytes: bytes,
    acceptance_comment_id: int,
    acceptance_comment_author: str,
    acceptance_comment_body: str,
    required_check_names: Sequence[str],
    check_observations: Sequence[Mapping[str, Any]],
    impact_plan: Mapping[str, Any],
    impact_classification: Mapping[str, Any],
    implementer: str,
    observed_at: datetime,
    fresh_until: datetime,
) -> GitHubOrchestrationEvidence:
    """Project authoritative legacy/current evidence into the existing v2 contract.

    This function is deliberately pure: it performs no network, subprocess,
    grant, merge, runtime, or filesystem effects.
    """
    binding = _parse_merge_lane_binding(pr_body)
    task_id, allowed_paths, card_hash = _parse_task_card(task_card_bytes)
    if (
        repository != "James3014/Nexus-new"
        or binding.get("owner_id") != "James3014"
        or binding.get("issue_number") != issue_number
        or binding.get("task_id") != task_id
        or binding.get("task_card_path") != task_card_path
        or binding.get("task_card_sha256") != card_hash
    ):
        raise _projection_error("MERGE_LANE_BINDING_INVALID")
    attempt_id = binding.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id.strip():
        raise _projection_error("MERGE_LANE_BINDING_INVALID")

    manifest = _json_bytes(controller_manifest_bytes, missing_code="CANDIDATE_PROVENANCE_MISSING")
    verifier = _json_bytes(verifier_evidence_bytes, missing_code="VERIFIER_PROVENANCE_MISSING")
    try:
        base_sha = str(manifest["base_sha"])
        head_sha = str(manifest["head_sha"])
        tree_sha = str(manifest["head_tree"])
        diff_hash = str(manifest["raw_diff_sha256"])
    except KeyError as exc:
        raise _projection_error("CANDIDATE_PROVENANCE_MISSING") from exc
    _require_subject(
        manifest,
        repository=repository,
        pull_request_number=pull_request_number,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
        diff_hash=diff_hash,
        status="CONTROLLER_COMPLETE",
        error_code="CANDIDATE_SUBJECT_MISMATCH",
    )
    if (
        impact_plan.get("base_sha") != base_sha
        or impact_plan.get("head_sha") != head_sha
        or impact_plan.get("source_tree") != tree_sha
    ):
        raise _projection_error("CANDIDATE_SUBJECT_MISMATCH")
    _require_subject(
        verifier,
        repository=repository,
        pull_request_number=pull_request_number,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
        diff_hash=diff_hash,
        status="COMPLETE",
        error_code="VERIFIER_SUBJECT_MISMATCH",
    )
    executor = verifier.get("executor")
    if not isinstance(executor, dict) or executor.get("exit_code") != 0:
        raise _projection_error("VERIFIER_PROVENANCE_MISSING")

    changed_paths = tuple(sorted(str(path) for path in impact_plan.get("changed_paths") or ()))
    if changed_paths != allowed_paths:
        raise _projection_error("SUBJECT_IDENTITY_MISMATCH")
    impact = _project_impact(
        impact_plan,
        impact_classification,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
        changed_paths=changed_paths,
    )
    reviewer, acceptance_hash = _parse_legacy_acceptance(
        acceptance_comment_body,
        comment_id=acceptance_comment_id,
        author=acceptance_comment_author,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
        card_hash=card_hash,
    )
    if not implementer.strip() or implementer.strip() == reviewer.strip():
        raise _projection_error("SUBJECT_IDENTITY_MISMATCH")
    checks = _project_required_checks(required_check_names, check_observations, head_sha=head_sha)
    reviews = (ReviewResult(reviewer=reviewer, state="APPROVED", unresolved_threads=0),)
    contract_hash = canonical_hash({
        "schema": "nexus.governed_task_attempt_projection.v1",
        "repository": repository,
        "issue_number": issue_number,
        "pull_request_number": pull_request_number,
        "execution_lane": "GOVERNED",
        "task_id": task_id,
        "attempt_id": attempt_id,
        "task_card_path": task_card_path,
        "task_card_sha256": card_hash,
        "candidate_head_sha": head_sha,
        "merge_lane_binding_hash": binding["binding_hash"],
    })
    candidate_state_hash = _sha256_bytes(controller_manifest_bytes)
    verifier_hash = _sha256_bytes(verifier_evidence_bytes)
    candidate = CandidateLineage(
        task_id=task_id,
        attempt_id=attempt_id,
        contract_hash=contract_hash,
        card_hash=card_hash,
        candidate_commit_sha=head_sha,
        candidate_tree_sha=tree_sha,
        candidate_state_hash=candidate_state_hash,
        verified_receipt_hash=verifier_hash,
        independent_acceptance_hash=acceptance_hash,
        reviewer=reviewer,
        implementer=implementer.strip(),
    )
    return GitHubOrchestrationEvidence(
        repository=repository,
        issue_number=issue_number,
        pull_request_number=pull_request_number,
        base_sha=base_sha,
        head_sha=head_sha,
        tree_sha=tree_sha,
        current_main_sha=base_sha,
        diff_hash=diff_hash,
        checks_hash=canonical_hash({"checks": [item.model_dump(mode="json") for item in checks]}),
        reviews_hash=canonical_hash({
            "reviews": [item.model_dump(mode="json") for item in reviews]
        }),
        task_attempt_contract_hash=contract_hash,
        candidate_hash=candidate_state_hash,
        verifier_hash=verifier_hash,
        independent_acceptance_hash=acceptance_hash,
        impact_hash=canonical_hash(impact.model_dump(mode="json")),
        observed_at=observed_at,
        fresh_until=fresh_until,
        allowed_paths=allowed_paths,
        changed_paths=changed_paths,
        required_checks=checks,
        reviews=reviews,
        candidate=candidate,
        impact=impact,
    )
