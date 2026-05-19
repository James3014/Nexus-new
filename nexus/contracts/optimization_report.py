from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


OPTIMIZATION_REPORT_CONTRACT_SCHEMA = "nexus_optimization_report_contract.v1"


class ClaimClass(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    INTERNAL_DIAGNOSTIC = "INTERNAL_DIAGNOSTIC"
    SF_DISCOVERY = "SF_DISCOVERY"
    RUNTIME_APPLY_REVIEW = "RUNTIME_APPLY_REVIEW"
    PUBLIC_READY = "PUBLIC_READY"


class RetentionClass(str, Enum):
    KEEP_TRACKED_SOURCE = "keep_tracked_source"
    KEEP_CURRENT_EVIDENCE = "keep_current_evidence"
    PINNED_BY_CATALOG = "pinned_by_catalog"
    ARCHIVE_CANDIDATE = "archive_candidate"
    TRANSIENT_RECEIPT_ROOT = "transient_receipt_root"
    DELETE_CANDIDATE = "delete_candidate"


class ProviderTokenCleanliness(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    MEASURED = "measured"
    ESTIMATED = "estimated"
    MISSING = "missing"
    MIXED = "mixed"


@dataclass(frozen=True)
class OptimizationReportContract:
    claim_class: ClaimClass
    retention_class: RetentionClass
    claim_boundary: tuple[str, ...]
    evidence_paths: tuple[str, ...] = ()
    runtime_update_allowed: bool = False
    public_benchmark_allowed: bool = False
    provider_token_cleanliness: ProviderTokenCleanliness = ProviderTokenCleanliness.NOT_APPLICABLE
    status: str = "PASS"
    blockers: tuple[str, ...] = ()
    schema: str = OPTIMIZATION_REPORT_CONTRACT_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        blockers = validate_optimization_report_contract(self.to_dict())
        if blockers:
            raise ValueError(";".join(blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "status": self.status,
            "claim_class": self.claim_class.value,
            "retention_class": self.retention_class.value,
            "claim_boundary": list(self.claim_boundary),
            "evidence_paths": list(self.evidence_paths),
            "runtime_update_allowed": self.runtime_update_allowed,
            "public_benchmark_allowed": self.public_benchmark_allowed,
            "provider_token_cleanliness": self.provider_token_cleanliness.value,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
        }


def optimization_report_contract_from_payload(payload: Mapping[str, Any]) -> OptimizationReportContract:
    return OptimizationReportContract(
        claim_class=_coerce_enum(payload.get("claim_class", ""), ClaimClass),
        retention_class=_coerce_enum(payload.get("retention_class", ""), RetentionClass),
        claim_boundary=tuple(str(item) for item in payload.get("claim_boundary", []) or []),
        evidence_paths=tuple(str(item) for item in payload.get("evidence_paths", []) or []),
        runtime_update_allowed=bool(payload.get("runtime_update_allowed", False)),
        public_benchmark_allowed=bool(payload.get("public_benchmark_allowed", False)),
        provider_token_cleanliness=_coerce_enum(
            payload.get("provider_token_cleanliness", ProviderTokenCleanliness.NOT_APPLICABLE.value),
            ProviderTokenCleanliness,
        ),
        status=str(payload.get("status", "PASS")),
        blockers=tuple(str(item) for item in payload.get("blockers", []) or []),
        metadata=dict(payload.get("metadata", {}) or {}),
        schema=str(payload.get("schema", OPTIMIZATION_REPORT_CONTRACT_SCHEMA)),
    )


def build_optimization_report_contract(
    *,
    claim_class: ClaimClass | str,
    retention_class: RetentionClass | str,
    claim_boundary: list[str] | tuple[str, ...],
    evidence_paths: list[str] | tuple[str, ...] = (),
    runtime_update_allowed: bool = False,
    public_benchmark_allowed: bool = False,
    provider_token_cleanliness: ProviderTokenCleanliness | str = ProviderTokenCleanliness.NOT_APPLICABLE,
    status: str = "PASS",
    blockers: list[str] | tuple[str, ...] = (),
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = OptimizationReportContract(
        claim_class=_coerce_enum(claim_class, ClaimClass),
        retention_class=_coerce_enum(retention_class, RetentionClass),
        claim_boundary=tuple(str(item) for item in claim_boundary),
        evidence_paths=tuple(str(item) for item in evidence_paths),
        runtime_update_allowed=runtime_update_allowed,
        public_benchmark_allowed=public_benchmark_allowed,
        provider_token_cleanliness=_coerce_enum(provider_token_cleanliness, ProviderTokenCleanliness),
        status=status,
        blockers=tuple(str(item) for item in blockers),
        metadata=dict(metadata or {}),
    )
    return contract.to_dict()


def validate_optimization_report_contract(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []

    claim_class = _enum_value(payload.get("claim_class"), ClaimClass, "claim_class", blockers)
    retention_class = _enum_value(payload.get("retention_class"), RetentionClass, "retention_class", blockers)
    provider_token_cleanliness = _enum_value(
        payload.get("provider_token_cleanliness", ProviderTokenCleanliness.NOT_APPLICABLE.value),
        ProviderTokenCleanliness,
        "provider_token_cleanliness",
        blockers,
    )

    claim_boundary = payload.get("claim_boundary")
    if not isinstance(claim_boundary, list) or not any(str(item).strip() for item in claim_boundary):
        blockers.append("missing_claim_boundary")

    evidence_paths = payload.get("evidence_paths", [])
    if evidence_paths is None:
        evidence_paths = []
    if not isinstance(evidence_paths, list):
        blockers.append("invalid_evidence_paths")
        evidence_paths = []
    non_empty_evidence_paths = [str(item).strip() for item in evidence_paths if str(item).strip()]

    runtime_update_allowed = bool(payload.get("runtime_update_allowed", False))
    public_benchmark_allowed = bool(payload.get("public_benchmark_allowed", False))

    if retention_class == RetentionClass.DELETE_CANDIDATE:
        blockers.append("delete_candidate_requires_explicit_separate_command")
    if claim_class in {ClaimClass.SF_DISCOVERY, ClaimClass.RUNTIME_APPLY_REVIEW, ClaimClass.PUBLIC_READY}:
        if not non_empty_evidence_paths:
            blockers.append("missing_evidence_paths")
    if runtime_update_allowed and claim_class != ClaimClass.RUNTIME_APPLY_REVIEW:
        blockers.append("runtime_update_requires_runtime_apply_review_claim_class")
    if public_benchmark_allowed and claim_class != ClaimClass.PUBLIC_READY:
        blockers.append("public_benchmark_requires_public_ready_claim_class")
    if claim_class == ClaimClass.PUBLIC_READY:
        if provider_token_cleanliness not in {
            ProviderTokenCleanliness.MEASURED,
            ProviderTokenCleanliness.NOT_APPLICABLE,
        }:
            blockers.append("public_ready_requires_measured_or_not_applicable_tokens")
        if not non_empty_evidence_paths:
            blockers.append("public_ready_requires_evidence_paths")
    if claim_class == ClaimClass.SF_DISCOVERY and runtime_update_allowed:
        blockers.append("sf_discovery_must_not_update_runtime")
    if claim_class == ClaimClass.PLAN_ONLY and (runtime_update_allowed or public_benchmark_allowed):
        blockers.append("plan_only_must_not_unlock_runtime_or_public_benchmark")

    return sorted(set(blockers))


def report_contract_readout(payload: Mapping[str, Any]) -> dict[str, Any]:
    blockers = validate_optimization_report_contract(payload)
    return {
        "schema": OPTIMIZATION_REPORT_CONTRACT_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "blockers": blockers,
        "claim_class": str(payload.get("claim_class", "")),
        "retention_class": str(payload.get("retention_class", "")),
        "runtime_update_allowed": bool(payload.get("runtime_update_allowed", False)),
        "public_benchmark_allowed": bool(payload.get("public_benchmark_allowed", False)),
    }


def _enum_value(raw: Any, enum_cls: type[Enum], field_name: str, blockers: list[str]) -> Enum | None:
    try:
        return _coerce_enum(raw, enum_cls)
    except ValueError:
        blockers.append(f"invalid_{field_name}")
        return None


def _coerce_enum(raw: Any, enum_cls: type[Enum]) -> Enum:
    if isinstance(raw, enum_cls):
        return raw
    return enum_cls(str(raw))
