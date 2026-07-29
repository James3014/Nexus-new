from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


class CommitteeCandidateProducer(Protocol):
    """Injectable seam for generating committee candidates.

    Accepts a CommitteeRoutedToolRequest and returns a list of raw candidate dicts.
    Can be a plain function or an object with __call__.
    """
    def __call__(self, request: CommitteeRoutedToolRequest) -> list[dict[str, Any]]:
        ...


COMMITTEE_MEMBER_DEMAND_SCHEMA = "nexus.committee_member_demand.v1"
COMMITTEE_MEMBER_DEMANDS_SCHEMA = "nexus.committee_member_demands.v1"
COMMITTEE_ROUTE_AUTHORITY = "CapabilityPlanner"


@dataclass(frozen=True)
class CommitteeMemberDemand:
    """A planner-selected committee member projected into workforce demand.

    This is only a projection of existing Planner output.  It does not select
    a topology, admit a worker, or invoke a provider; those remain downstream
    lifecycle stages.
    """

    member_id: str
    parent_demand_id: str
    phase: str
    role: str
    provider: str
    model: str
    required_or_optional: str
    minimum_autonomy: str
    context_class: str
    mutation_intent: bool
    external_verification_required: bool
    route_authority: str = COMMITTEE_ROUTE_AUTHORITY
    schema: str = COMMITTEE_MEMBER_DEMAND_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "member_id": self.member_id,
            "parent_demand_id": self.parent_demand_id,
            "phase": self.phase,
            "role": self.role,
            "provider": self.provider,
            "model": self.model,
            "required_or_optional": self.required_or_optional,
            "minimum_autonomy": self.minimum_autonomy,
            "context_class": self.context_class,
            "mutation_intent": self.mutation_intent,
            "external_verification_required": self.external_verification_required,
            "route_authority": self.route_authority,
        }


_MEMBER_DEFAULTS: dict[str, dict[str, Any]] = {
    "proposal": {"role": "candidate_proposer", "autonomy": "L1", "context": "nexus_bounded", "mutation": True, "verify": True},
    "judge": {"role": "candidate_judge", "autonomy": "L0.5", "context": "nexus_bounded", "mutation": False, "verify": True},
    "diagnosis": {"role": "compact_diagnosis", "autonomy": "L0.5", "context": "nexus_bounded", "mutation": False, "verify": False},
    "audit": {"role": "independent_review", "autonomy": "L0.5", "context": "nexus_bounded", "mutation": False, "verify": True},
    "advisor": {"role": "bounded_advisor", "autonomy": "L0.5", "context": "nexus_bounded", "mutation": False, "verify": False},
    "delegated_retry": {"role": "candidate_retry", "autonomy": "L1", "context": "nexus_bounded", "mutation": True, "verify": True},
}


def _member_model(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("model") or value.get("model_name") or "").strip()
    return str(value or "").strip()


def _member_spec(value: Any, *, phase: str, index: int) -> tuple[dict[str, Any] | None, str | None]:
    defaults = _MEMBER_DEFAULTS[phase]
    if isinstance(value, Mapping):
        model = _member_model(value)
        if not model:
            return None, f"{phase}[{index}]:missing_model"
        role = str(value.get("role") or defaults["role"]).strip()
        provider = str(value.get("provider") or "ollama").strip()
        if not role:
            return None, f"{phase}[{index}]:missing_role"
        if not provider:
            return None, f"{phase}[{index}]:missing_provider"
        return {
            "model": model,
            "role": role,
            "provider": provider,
            "required_or_optional": str(
                value.get("required_or_optional")
                or ("required" if phase in {"proposal", "judge", "diagnosis", "audit"} else "optional")
            ),
            "minimum_autonomy": str(value.get("minimum_autonomy") or defaults["autonomy"]),
            "context_class": str(value.get("context_class") or defaults["context"]),
            "mutation_intent": bool(value.get("mutation_intent", defaults["mutation"])),
            "external_verification_required": bool(value.get("external_verification_required", defaults["verify"])),
        }, None
    model = _member_model(value)
    if not model:
        return None, f"{phase}[{index}]:missing_model"
    return {
        "model": model,
        "role": defaults["role"],
        "provider": "ollama",
        "required_or_optional": "required" if phase in {"proposal", "judge", "diagnosis", "audit"} else "optional",
        "minimum_autonomy": defaults["autonomy"],
        "context_class": defaults["context"],
        "mutation_intent": defaults["mutation"],
        "external_verification_required": defaults["verify"],
    }, None


def validate_committee_member_demands(bundle: Mapping[str, Any]) -> list[str]:
    """Validate a projected bundle without performing admission or invocation."""
    failures: list[str] = []
    if bundle.get("schema") != COMMITTEE_MEMBER_DEMANDS_SCHEMA:
        failures.append("invalid_committee_member_demands_schema")
    if bundle.get("route_authority") != COMMITTEE_ROUTE_AUTHORITY:
        failures.append("committee_member_route_authority_mismatch")
    parent = str(bundle.get("parent_demand_id") or "").strip()
    if not parent:
        failures.append("missing_parent_demand_id")
    seen: set[str] = set()
    required = ("member_id", "parent_demand_id", "phase", "role", "provider", "model", "required_or_optional", "minimum_autonomy", "context_class", "route_authority")
    for index, raw in enumerate(bundle.get("demands") or ()):
        if not isinstance(raw, Mapping):
            failures.append(f"member[{index}]:malformed")
            continue
        for key in required:
            if not str(raw.get(key) or "").strip():
                failures.append(f"member[{index}]:missing_{key}")
        member_id = str(raw.get("member_id") or "")
        if member_id in seen:
            failures.append(f"member[{index}]:duplicate_member_id")
        seen.add(member_id)
        if str(raw.get("parent_demand_id") or "") != parent:
            failures.append(f"member[{index}]:parent_demand_id_mismatch")
        if raw.get("route_authority") != COMMITTEE_ROUTE_AUTHORITY:
            failures.append(f"member[{index}]:route_authority_mismatch")
    if not bundle.get("demands"):
        failures.append("no_committee_member_demands")
    return failures


def build_committee_member_demands(
    signal_snapshot: Mapping[str, Any] | None = None,
    *,
    parent_demand_id: str = "",
    proposer_specs: Sequence[Any] | None = None,
    judge_model: Any = "",
    diagnosis_models: Sequence[Any] | None = None,
    audit_models: Sequence[Any] | None = None,
    advisor_model: Any = "",
    delegated_retry_candidate_models: Sequence[Any] | None = None,
    delegated_member_specs: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Project existing Planner committee selections into independent demands.

    Missing optional groups produce no demand.  A present malformed group is
    rejected; no environment lookup or replacement model is performed.
    """
    source = signal_snapshot if isinstance(signal_snapshot, Mapping) else {}
    parent = str(parent_demand_id or source.get("parent_demand_id") or source.get("demand_id") or "").strip()
    raw_groups: list[tuple[str, Sequence[Any] | None, bool]] = [
        ("proposal", proposer_specs if proposer_specs is not None else source.get("proposer_specs"), True),
        ("diagnosis", diagnosis_models if diagnosis_models is not None else source.get("diagnosis_models"), False),
        ("audit", audit_models if audit_models is not None else source.get("audit_models"), False),
        ("delegated_retry", delegated_retry_candidate_models if delegated_retry_candidate_models is not None else source.get("delegated_retry_candidate_models"), False),
    ]
    demands: list[dict[str, Any]] = []
    failures: list[str] = []
    if not parent:
        failures.append("missing_parent_demand_id")

    for phase, values, required in raw_groups:
        if values is None or values == []:
            if required:
                failures.append(f"missing_{phase}_specs")
            continue
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            failures.append(f"{phase}:malformed_collection")
            continue
        if phase in {"proposal", "diagnosis", "audit"} and len(values) < 2:
            failures.append(f"{phase}:requires_at_least_two_members")
            continue
        for index, value in enumerate(values):
            spec, error = _member_spec(value, phase=phase, index=index)
            if error:
                failures.append(error)
                continue
            assert spec is not None
            member_id = f"{parent}:{phase}:{index}"
            demands.append(CommitteeMemberDemand(
                member_id=member_id,
                parent_demand_id=parent,
                phase=phase,
                role=spec["role"],
                provider=spec["provider"],
                model=spec["model"],
                required_or_optional=spec["required_or_optional"],
                minimum_autonomy=spec["minimum_autonomy"],
                context_class=spec["context_class"],
                mutation_intent=spec["mutation_intent"],
                external_verification_required=spec["external_verification_required"],
            ).to_dict())

    judge = _member_model(judge_model or source.get("judge_model"))
    if not judge:
        failures.append("missing_judge_model")
    else:
        spec, error = _member_spec({"model": judge, "role": "judge"}, phase="judge", index=0)
        if error:
            failures.append(error)
        else:
            assert spec is not None
            demands.append(CommitteeMemberDemand(
                member_id=f"{parent}:judge:0", parent_demand_id=parent, phase="judge",
                role=spec["role"], provider=spec["provider"], model=spec["model"],
                required_or_optional="required", minimum_autonomy=spec["minimum_autonomy"],
                context_class=spec["context_class"], mutation_intent=False,
                external_verification_required=True,
            ).to_dict())

    advisor = _member_model(advisor_model or source.get("advisor_model"))
    if advisor:
        spec, error = _member_spec({"model": advisor, "role": "advisor"}, phase="advisor", index=0)
        if error:
            failures.append(error)
        else:
            assert spec is not None
            demands.append(CommitteeMemberDemand(
                member_id=f"{parent}:advisor:0", parent_demand_id=parent, phase="advisor",
                role=spec["role"], provider=spec["provider"], model=spec["model"],
                required_or_optional="optional", minimum_autonomy=spec["minimum_autonomy"],
                context_class=spec["context_class"], mutation_intent=False,
                external_verification_required=False,
            ).to_dict())

    if delegated_member_specs is None and "delegated_member_specs" in source:
        delegated_member_specs = source.get("delegated_member_specs")
    if delegated_member_specs is not None:
        if isinstance(delegated_member_specs, (str, bytes)) or not isinstance(delegated_member_specs, Sequence):
            failures.append("delegated_member_specs:malformed_collection")
        else:
            for index, value in enumerate(delegated_member_specs):
                if not isinstance(value, Mapping):
                    failures.append(f"delegated_member_specs[{index}]:malformed")
                    continue
                phase = str(value.get("phase") or "delegated_retry").strip() or "delegated_retry"
                if phase not in _MEMBER_DEFAULTS:
                    failures.append(f"delegated_member_specs[{index}]:unsupported_phase")
                    continue
                spec, error = _member_spec(value, phase=phase, index=index)
                if error:
                    failures.append(f"delegated_member_specs[{index}]:{error.split(':', 1)[-1]}")
                    continue
                assert spec is not None
                demands.append(CommitteeMemberDemand(
                    member_id=str(value.get("member_id") or f"{parent}:{phase}:{index}"),
                    parent_demand_id=parent, phase=phase, role=spec["role"],
                    provider=spec["provider"], model=spec["model"],
                    required_or_optional=spec["required_or_optional"],
                    minimum_autonomy=spec["minimum_autonomy"], context_class=spec["context_class"],
                    mutation_intent=spec["mutation_intent"],
                    external_verification_required=spec["external_verification_required"],
                ).to_dict())

    bundle = {
        "schema": COMMITTEE_MEMBER_DEMANDS_SCHEMA,
        "parent_demand_id": parent,
        "route_authority": COMMITTEE_ROUTE_AUTHORITY,
        "demands": demands,
        "failure_reasons": failures,
        "wiring_status": "FAIL_CLOSED" if failures else "WIRED",
    }
    failures.extend(validate_committee_member_demands(bundle))
    bundle["failure_reasons"] = sorted(set(failures))
    bundle["wiring_status"] = "FAIL_CLOSED" if bundle["failure_reasons"] else "WIRED"
    return bundle


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
    diagnosis_models: list[str] = field(default_factory=list)
    audit_models: list[str] = field(default_factory=list)
    advisor_model: str = ""
    delegated_retry_candidate_models: list[str] = field(default_factory=list)
    delegated_member_specs: list[dict[str, Any]] = field(default_factory=list)
    parent_demand_id: str = ""
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
    committee_member_demands: list[dict[str, Any]] = field(default_factory=list)
    committee_member_demand_failures: list[str] = field(default_factory=list)
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
        "committee_member_demands": result.committee_member_demands,
        "committee_member_demand_failures": result.committee_member_demand_failures,
        "committee_member_demand_wiring_status": (
            "FAIL_CLOSED" if result.committee_member_demand_failures else "WIRED"
        ),
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

    demand_bundle = build_committee_member_demands(
        parent_demand_id=request.parent_demand_id or request.task_id,
        proposer_specs=request.proposer_specs,
        judge_model=request.judge_model,
        diagnosis_models=request.diagnosis_models,
        audit_models=request.audit_models,
        advisor_model=request.advisor_model,
        delegated_retry_candidate_models=request.delegated_retry_candidate_models,
        delegated_member_specs=request.delegated_member_specs,
    )
    if demand_bundle["failure_reasons"]:
        return CommitteeRoutedToolResult(
            invoked=False,
            invocation_allowed=False,
            blocked_reason="committee_member_demand_wiring_failed",
            failure_reasons=list(demand_bundle["failure_reasons"]),
            committee_member_demands=list(demand_bundle["demands"]),
            committee_member_demand_failures=list(demand_bundle["failure_reasons"]),
            receipt_fragment={
                **gate,
                "committee_member_demands": demand_bundle["demands"],
                "committee_member_demand_failures": demand_bundle["failure_reasons"],
                "committee_member_demand_wiring_status": "FAIL_CLOSED",
                "p4_fail_closed": True,
            },
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
            committee_member_demands=list(demand_bundle["demands"]),
            receipt_fragment={
                **gate,
                "committee_member_demands": demand_bundle["demands"],
                "committee_member_demand_wiring_status": "WIRED",
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
            committee_member_demands=list(demand_bundle["demands"]),
            receipt_fragment={
                **gate,
                "committee_member_demands": demand_bundle["demands"],
                "committee_member_demand_wiring_status": "WIRED",
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
        result.committee_member_demands = list(demand_bundle["demands"])
        result.raw_candidate_count = len(raw_candidates)
        result.candidate_producer_present = True
        result.candidate_producer_name = producer_name
        result.candidate_producer_invoked = producer_invoked
        result.receipt_fragment["p4_candidate_producer_present"] = True
        result.receipt_fragment["p4_candidate_producer_name"] = producer_name
        result.receipt_fragment["p4_candidate_producer_invoked"] = True
        result.receipt_fragment["p4_raw_candidate_count"] = len(raw_candidates)
        result.receipt_fragment["committee_member_demands"] = demand_bundle["demands"]
        result.receipt_fragment["committee_member_demand_wiring_status"] = "WIRED"
        return result

    # P5-I7 / P7-A: Diversity-aware selection (env-guarded, P7 supersedes P5)
    p5_diversity_used = False
    p5_result = None
    p7_diversity_used = False
    p7_result = None
    rejected_indices = {r["index"] for r in rejections}

    # Build raw_index_map: valid_candidates[i] → raw_candidates[j]
    raw_index_map: list[int] = []
    for raw_idx in range(len(raw_candidates)):
        if raw_idx not in rejected_indices:
            raw_index_map.append(raw_idx)

    p7_enabled = os.environ.get("NEXUS_ENABLE_P7_DIVERSITY_AWARE", "0") == "1"
    p5_enabled = os.environ.get("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", "0") == "1"

    if p7_enabled:
        try:
            from nexus.services.local_heal.diversity_selector import select_with_diversity

            p7_result = select_with_diversity(valid_candidates)
            p7_diversity_used = True

            if p7_result.fail_closed or p7_result.selected_index < 0:
                _receipt = {
                    **gate,
                    "p7_diversity_aware": True,
                    "p7_selection_strategy": p7_result.selection_strategy,
                    "p7_candidate_count": p7_result.candidate_count,
                    "p7_popularity_trap_detected": p7_result.popularity_trap_detected,
                    "p7_popularity_trap_reason": p7_result.popularity_trap_reason,
                    "p7_selected_candidate_index": p7_result.selected_index,
                    "p7_selected_candidate_hash": p7_result.selected_candidate_hash,
                    "p7_score_breakdown": p7_result.score_breakdown,
                    "p7_rejected_by_diversity": p7_result.rejected_by_diversity,
                    "p7_fail_closed": p7_result.fail_closed,
                    "p7_trace_event_count": len(p7_result.trace_events) if p7_result.trace_events else 0,
                    "p7_trace_events": p7_result.trace_events,
                }
                return CommitteeRoutedToolResult(
                    invoked=True,
                    invocation_allowed=True,
                    candidate_count=len(raw_candidates),
                    canonical_candidate_count=len(valid_candidates),
                    winner_found=False,
                    solved_by_committee=False,
                    failure_reasons=[f"p7_selection_failed:{r}" for r in p7_result.failure_reasons],
                    receipt_fragment=_receipt,
                )

            winner = valid_candidates[p7_result.selected_index]

            # Promote selected_index for winner_source_model lookup
            _diversity_selected_index = p7_result.selected_index
        except ImportError:
            winner = valid_candidates[0]
    elif p5_enabled:
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
                # P5 selector failed — return fail-closed result with trace
                _receipt = {
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
                }
                # P5-V2: Merge trace events
                if p5_result.trace_events:
                    _receipt["p5_trace_event_count"] = len(p5_result.trace_events)
                    _receipt["p5_trace_events"] = p5_result.trace_events
                return CommitteeRoutedToolResult(
                    invoked=True,
                    invocation_allowed=True,
                    candidate_count=len(raw_candidates),
                    canonical_candidate_count=len(valid_candidates),
                    winner_found=False,
                    solved_by_committee=False,
                    failure_reasons=[f"p5_selection_failed:{r}" for r in p5_result.failure_reasons],
                    receipt_fragment=_receipt,
                )

            winner = valid_candidates[p5_result.selected_index]
        except ImportError:
            # Fallback: diversity_selector unavailable
            winner = valid_candidates[0]
    else:
        # P5/P7 disabled: existing behavior
        winner = valid_candidates[0]

    # Determine winner source model from raw candidates
    winner_source_model = ""
    if p7_diversity_used and p7_result is not None and not p7_result.fail_closed and p7_result.selected_index >= 0:
        raw_winner_idx = raw_index_map[p7_result.selected_index] if p7_result.selected_index < len(raw_index_map) else -1
        if 0 <= raw_winner_idx < len(raw_candidates):
            winner_source_model = str(
                raw_candidates[raw_winner_idx].get("model", "")
                or raw_candidates[raw_winner_idx].get("model_name", "")
                or ""
            )
    if not winner_source_model and p5_diversity_used and p5_result is not None and not p5_result.fail_closed and p5_result.selected_index >= 0:
        # P5-V4: use raw_index_map to find the correct raw candidate
        raw_winner_idx = raw_index_map[p5_result.selected_index] if p5_result.selected_index < len(raw_index_map) else -1
        if 0 <= raw_winner_idx < len(raw_candidates):
            winner_source_model = str(
                raw_candidates[raw_winner_idx].get("model", "")
                or raw_candidates[raw_winner_idx].get("model_name", "")
                or ""
            )
    if not winner_source_model:
        # Fallback: first non-rejected raw candidate (pre-P5 behavior)
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
        committee_member_demands=list(demand_bundle["demands"]),
        receipt_fragment={
            **gate,
            "committee_member_demands": demand_bundle["demands"],
            "committee_member_demand_wiring_status": "WIRED",
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

    # P7-A / P5-I7: Add receipt fields for the active selector
    if p7_diversity_used and p7_result is not None:
        result.receipt_fragment["p7_diversity_aware"] = True
        result.receipt_fragment["p7_selection_strategy"] = p7_result.selection_strategy
        result.receipt_fragment["p7_candidate_count"] = p7_result.candidate_count
        result.receipt_fragment["p7_popularity_trap_detected"] = p7_result.popularity_trap_detected
        result.receipt_fragment["p7_popularity_trap_reason"] = p7_result.popularity_trap_reason
        result.receipt_fragment["p7_selected_candidate_index"] = p7_result.selected_index
        result.receipt_fragment["p7_selected_candidate_hash"] = p7_result.selected_candidate_hash
        result.receipt_fragment["p7_score_breakdown"] = p7_result.score_breakdown
        result.receipt_fragment["p7_rejected_by_diversity"] = p7_result.rejected_by_diversity
        result.receipt_fragment["p7_fail_closed"] = p7_result.fail_closed
        if p7_result.trace_events:
            result.receipt_fragment["p7_trace_event_count"] = len(p7_result.trace_events)
            result.receipt_fragment["p7_trace_events"] = p7_result.trace_events
    elif p5_diversity_used and p5_result is not None:
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

        # P5-V2: Merge trace events into receipt
        if p5_result.trace_events:
            result.receipt_fragment["p5_trace_event_count"] = len(p5_result.trace_events)
            result.receipt_fragment["p5_trace_events"] = p5_result.trace_events

    return result
