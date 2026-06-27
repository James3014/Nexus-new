from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping

HYBRID_ROUTE_DECISION_SCHEMA = "nexus.hybrid_route_decision.v1"


class RouteMode(str, Enum):
    CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY = "cloud_assisted_by_local_trace_only"
    CLOUD_ASSISTED_BY_LOCAL_COMPACT_CONTEXT = "cloud_assisted_by_local_compact_context"
    CLOUD_FIRST_LOCAL_GUARD_ADVISORY = "cloud_first_local_guard_advisory"
    CLOUD_FIRST_LOCAL_GUARD_FAIL_CLOSED = "cloud_first_local_guard_fail_closed"
    LOCAL_FIRST_CLOUD_FALLBACK = "local_first_cloud_fallback"
    LOCAL_ONLY_PLANNED = "local_only_planned"
    LOCAL_ONLY_BLOCKED = "local_only_blocked"
    LOCAL_ONLY_EXECUTED = "local_only_executed"


class VerifierResult(str, Enum):
    NOT_RUN = "not_run"
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"


class Authority(str, Enum):
    TRACE_ONLY = "trace_only"
    ADVISORY_ONLY = "advisory_only"
    FAIL_CLOSED = "fail_closed"
    CANDIDATE_ONLY = "candidate_only"
    INTERNAL_ONLY = "internal_only"


@dataclass(frozen=True)
class HybridRouteDecision:
    route_mode: RouteMode = RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY
    public_claim_allowed: bool = False
    production_ready: bool = False
    adapter_output_is_route_truth: bool = False
    route_truth_source: str = "CapabilityPlanner"
    local_guard: dict[str, Any] = field(default_factory=dict)
    behavior_changed: bool = False
    authority: Authority = Authority.TRACE_ONLY
    cloud_model_called: bool = False
    local_model_called: bool = False
    candidate_output_isolated: bool = True
    selected_candidate_hash: str = ""
    applied_patch_hash: str = ""
    selected_candidate_hash_matches_applied: bool = False
    verifier_result: VerifierResult = VerifierResult.NOT_RUN
    evidence_refs: tuple[str, ...] = ()
    fallback_block_reason: str = ""
    blockers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = HYBRID_ROUTE_DECISION_SCHEMA

    def __post_init__(self) -> None:
        blockers = validate_hybrid_route_decision(self.to_dict())
        if blockers:
            raise ValueError(";".join(blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "route_mode": self.route_mode.value if hasattr(self.route_mode, "value") else str(self.route_mode),
            "public_claim_allowed": self.public_claim_allowed,
            "production_ready": self.production_ready,
            "adapter_output_is_route_truth": self.adapter_output_is_route_truth,
            "route_truth_source": self.route_truth_source,
            "local_guard": dict(self.local_guard),
            "behavior_changed": self.behavior_changed,
            "authority": self.authority.value if hasattr(self.authority, "value") else str(self.authority),
            "cloud_model_called": self.cloud_model_called,
            "local_model_called": self.local_model_called,
            "candidate_output_isolated": self.candidate_output_isolated,
            "selected_candidate_hash": self.selected_candidate_hash,
            "applied_patch_hash": self.applied_patch_hash,
            "selected_candidate_hash_matches_applied": self.selected_candidate_hash_matches_applied,
            "verifier_result": self.verifier_result.value if hasattr(self.verifier_result, "value") else str(self.verifier_result),
            "evidence_refs": list(self.evidence_refs),
            "fallback_block_reason": self.fallback_block_reason,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
        }


def hybrid_route_decision_from_payload(payload: Mapping[str, Any]) -> HybridRouteDecision:
    return HybridRouteDecision(
        route_mode=_coerce_enum(payload.get("route_mode", RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY.value), RouteMode, "route_mode"),
        public_claim_allowed=bool(payload.get("public_claim_allowed", False)),
        production_ready=bool(payload.get("production_ready", False)),
        adapter_output_is_route_truth=bool(payload.get("adapter_output_is_route_truth", False)),
        route_truth_source=str(payload.get("route_truth_source", "CapabilityPlanner")),
        local_guard=dict(payload.get("local_guard", {}) or {}),
        behavior_changed=bool(payload.get("behavior_changed", False)),
        authority=_coerce_enum(payload.get("authority", Authority.TRACE_ONLY.value), Authority, "authority"),
        cloud_model_called=bool(payload.get("cloud_model_called", False)),
        local_model_called=bool(payload.get("local_model_called", False)),
        candidate_output_isolated=bool(payload.get("candidate_output_isolated", True)),
        selected_candidate_hash=str(payload.get("selected_candidate_hash", "") or ""),
        applied_patch_hash=str(payload.get("applied_patch_hash", "") or ""),
        selected_candidate_hash_matches_applied=bool(payload.get("selected_candidate_hash_matches_applied", False)),
        verifier_result=_coerce_enum(payload.get("verifier_result", VerifierResult.NOT_RUN.value), VerifierResult, "verifier_result"),
        evidence_refs=tuple(str(item) for item in payload.get("evidence_refs", []) or []),
        fallback_block_reason=str(payload.get("fallback_block_reason", "") or ""),
        blockers=tuple(str(item) for item in payload.get("blockers", []) or []),
        metadata=dict(payload.get("metadata", {}) or {}),
        schema=str(payload.get("schema", HYBRID_ROUTE_DECISION_SCHEMA)),
    )


def build_hybrid_route_decision(
    *,
    route_mode: RouteMode | str = RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY,
    public_claim_allowed: bool = False,
    production_ready: bool = False,
    adapter_output_is_route_truth: bool = False,
    route_truth_source: str = "CapabilityPlanner",
    local_guard: dict[str, Any] | None = None,
    behavior_changed: bool = False,
    authority: Authority | str = Authority.TRACE_ONLY,
    cloud_model_called: bool = False,
    local_model_called: bool = False,
    candidate_output_isolated: bool = True,
    selected_candidate_hash: str = "",
    applied_patch_hash: str = "",
    selected_candidate_hash_matches_applied: bool = False,
    verifier_result: VerifierResult | str = VerifierResult.NOT_RUN,
    evidence_refs: list[str] | tuple[str, ...] = (),
    fallback_block_reason: str = "",
    blockers: list[str] | tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    decision = HybridRouteDecision(
        route_mode=_coerce_enum(route_mode, RouteMode, "route_mode"),
        public_claim_allowed=public_claim_allowed,
        production_ready=production_ready,
        adapter_output_is_route_truth=adapter_output_is_route_truth,
        route_truth_source=route_truth_source,
        local_guard=dict(local_guard or {}),
        behavior_changed=behavior_changed,
        authority=_coerce_enum(authority, Authority, "authority"),
        cloud_model_called=cloud_model_called,
        local_model_called=local_model_called,
        candidate_output_isolated=candidate_output_isolated,
        selected_candidate_hash=selected_candidate_hash,
        applied_patch_hash=applied_patch_hash,
        selected_candidate_hash_matches_applied=selected_candidate_hash_matches_applied,
        verifier_result=_coerce_enum(verifier_result, VerifierResult, "verifier_result"),
        evidence_refs=tuple(evidence_refs),
        fallback_block_reason=fallback_block_reason,
        blockers=tuple(blockers),
        metadata=dict(metadata or {}),
    )
    return decision.to_dict()


def validate_hybrid_route_decision(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []

    schema = payload.get("schema")
    if schema != HYBRID_ROUTE_DECISION_SCHEMA:
        blockers.append("invalid_schema")

    route_truth_source = payload.get("route_truth_source")
    if route_truth_source != "CapabilityPlanner":
        blockers.append("invalid_route_truth_source")

    if bool(payload.get("public_claim_allowed", False)):
        blockers.append("public_claim_allowed_must_be_false")
    if bool(payload.get("production_ready", False)):
        blockers.append("production_ready_must_be_false")
    if bool(payload.get("adapter_output_is_route_truth", False)):
        blockers.append("adapter_output_is_route_truth_must_be_false")

    route_mode = _enum_value(payload.get("route_mode"), RouteMode, "route_mode", blockers)
    verifier_result = _enum_value(payload.get("verifier_result"), VerifierResult, "verifier_result", blockers)
    authority = _enum_value(payload.get("authority"), Authority, "authority", blockers)

    if route_mode == RouteMode.LOCAL_ONLY_EXECUTED:
        if not bool(payload.get("local_model_called", False)):
            blockers.append("local_only_executed_requires_local_model_called")
        if verifier_result != VerifierResult.PASS:
            blockers.append("local_only_executed_requires_verifier_pass")
        evidence_refs = payload.get("evidence_refs", [])
        if not isinstance(evidence_refs, list) or not any(str(item).strip() for item in evidence_refs):
            blockers.append("local_only_executed_requires_evidence_refs")
        if not bool(payload.get("candidate_output_isolated", True)):
            blockers.append("local_only_executed_requires_candidate_output_isolated")
        if not str(payload.get("selected_candidate_hash") or "").strip():
            blockers.append("local_only_executed_requires_selected_candidate_hash")
        if not str(payload.get("applied_patch_hash") or "").strip():
            blockers.append("local_only_executed_requires_applied_patch_hash")
        if not bool(payload.get("selected_candidate_hash_matches_applied", False)):
            blockers.append("local_only_executed_requires_hash_match")

    elif route_mode == RouteMode.CLOUD_ASSISTED_BY_LOCAL_TRACE_ONLY:
        if authority != Authority.TRACE_ONLY:
            blockers.append("trace_only_requires_trace_only_authority")
        if bool(payload.get("behavior_changed", False)):
            blockers.append("trace_only_requires_behavior_unchanged")

    elif route_mode == RouteMode.CLOUD_FIRST_LOCAL_GUARD_ADVISORY:
        if authority != Authority.ADVISORY_ONLY:
            blockers.append("advisory_requires_advisory_only_authority")
        if bool(payload.get("behavior_changed", False)):
            blockers.append("advisory_requires_behavior_unchanged")

    return sorted(set(blockers))


def _enum_value(raw: Any, enum_cls: type[Enum], field_name: str, blockers: list[str]) -> Enum | None:
    try:
        return _coerce_enum(raw, enum_cls, field_name)
    except ValueError:
        blockers.append(f"invalid_{field_name}")
        return None


def _coerce_enum(raw: Any, enum_cls: type[Enum], field_name: str | None = None) -> Enum:
    if isinstance(raw, enum_cls):
        return raw
    try:
        return enum_cls(str(raw))
    except ValueError as e:
        if field_name:
            raise ValueError(f"invalid_{field_name}") from e
        raise e
