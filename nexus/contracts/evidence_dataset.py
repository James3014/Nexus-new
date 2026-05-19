from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping

from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness


EVIDENCE_DATASET_RECORD_SCHEMA = "nexus_evidence_dataset_record.v1"
EVIDENCE_DATASET_MANIFEST_SCHEMA = "nexus_evidence_dataset_manifest.v1"
PHASES = ("S", "P", "X", "D", "R", "A", "C")


@dataclass(frozen=True)
class EvidenceDatasetRecord:
    record_id: str
    source_path: str
    source_schema: str
    task_id: str
    capability: str
    skill_id: str
    route_id: str
    claim_class: ClaimClass
    provider_token_cleanliness: ProviderTokenCleanliness
    delivery_status: str
    trust_status: str
    capability_outcome: str
    skill_effect_status: str
    evidence_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    phase_wall_sec: Mapping[str, float | None] = field(default_factory=dict)
    token_counts: Mapping[str, int | None] = field(default_factory=dict)
    gate_status: Mapping[str, str] = field(default_factory=dict)
    evidence_seal_status: str = "NOT_APPLICABLE"
    evidence_hash_status: str = "NOT_APPLICABLE"
    partial_telemetry_detected: bool = False
    blockers: tuple[str, ...] = ()
    schema: str = EVIDENCE_DATASET_RECORD_SCHEMA

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "claim_class", _claim_class(self.claim_class))
        except ValueError as exc:
            raise ValueError("invalid_claim_class") from exc
        try:
            object.__setattr__(
                self,
                "provider_token_cleanliness",
                _provider_token_cleanliness_value(self.provider_token_cleanliness),
            )
        except ValueError as exc:
            raise ValueError("invalid_provider_token_cleanliness") from exc
        blockers = validate_evidence_dataset_record(self.to_dict())
        if blockers:
            raise ValueError(";".join(blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "record_id": self.record_id,
            "source_path": self.source_path,
            "source_schema": self.source_schema,
            "task_id": self.task_id,
            "capability": self.capability,
            "skill_id": self.skill_id,
            "route_id": self.route_id,
            "claim_class": self.claim_class.value,
            "provider_token_cleanliness": self.provider_token_cleanliness.value,
            "delivery_status": self.delivery_status,
            "trust_status": self.trust_status,
            "capability_outcome": self.capability_outcome,
            "skill_effect_status": self.skill_effect_status,
            "evidence_refs": list(self.evidence_refs),
            "receipt_refs": list(self.receipt_refs),
            "phase_wall_sec": dict(self.phase_wall_sec),
            "token_counts": dict(self.token_counts),
            "gate_status": dict(self.gate_status),
            "evidence_seal_status": self.evidence_seal_status,
            "evidence_hash_status": self.evidence_hash_status,
            "partial_telemetry_detected": self.partial_telemetry_detected,
            "blockers": list(self.blockers),
        }


def evidence_record_from_sf_smoke_case(
    case: Mapping[str, Any],
    *,
    source_path: str,
    source_schema: str = "nexus.sf_current_overlay_runtime_smoke.v1",
) -> EvidenceDatasetRecord:
    capability = str(case.get("capability") or "")
    skill_id = str(case.get("expected_skill") or "")
    chain = case.get("runtime_final_receipt_chain", {})
    chain = chain if isinstance(chain, Mapping) else {}
    blockers = [str(item) for item in case.get("blocking_skill_mount_violations", []) or []]
    status = str(case.get("status") or "UNKNOWN").upper()
    chain_complete = all(
        bool(chain.get(key))
        for key in ("selected", "injected", "used", "evidence_present", "gate_passed", "outcome_contributed")
    )
    if not chain_complete:
        blockers.append("runtime_receipt_chain_incomplete")
    capability_outcome = "contributed" if chain_complete and status == "PASS" else "not_confirmed"
    skill_effect_status = "receipt_confirmed" if chain_complete and status == "PASS" else "not_confirmed"
    refs = [source_path]
    receipt_refs = [f"runtime_final_receipt_chain:{capability}:{skill_id}"]
    evidence_seal_status = str(case.get("evidence_seal_status") or "NOT_APPLICABLE").upper()
    evidence_hash_status = str(case.get("evidence_hash_status") or "NOT_APPLICABLE").upper()
    if bool(case.get("partial_telemetry_detected", False)):
        blockers.append("partial_telemetry_detected")
    return EvidenceDatasetRecord(
        record_id=_stable_record_id(source_path, capability, skill_id, status),
        source_path=source_path,
        source_schema=source_schema,
        task_id=capability,
        capability=capability,
        skill_id=skill_id,
        route_id=capability,
        claim_class=ClaimClass.RUNTIME_APPLY_REVIEW,
        provider_token_cleanliness=ProviderTokenCleanliness.NOT_APPLICABLE,
        delivery_status=status,
        trust_status="PASS" if not blockers else "RETURN",
        capability_outcome=capability_outcome,
        skill_effect_status=skill_effect_status,
        evidence_refs=tuple(refs),
        receipt_refs=tuple(receipt_refs),
        gate_status={
            "selected": _pass_return(chain.get("selected")),
            "injected": _pass_return(chain.get("injected")),
            "used": _pass_return(chain.get("used")),
            "evidence_present": _pass_return(chain.get("evidence_present")),
            "gate_passed": _pass_return(chain.get("gate_passed")),
            "outcome_contributed": _pass_return(chain.get("outcome_contributed")),
        },
        evidence_seal_status=evidence_seal_status,
        evidence_hash_status=evidence_hash_status,
        partial_telemetry_detected=bool(case.get("partial_telemetry_detected", False)),
        blockers=tuple(sorted(set(blockers))),
    )


def evidence_record_from_benchmark_row(
    row: Mapping[str, Any],
    *,
    source_path: str,
    claim_class: ClaimClass | str = ClaimClass.INTERNAL_DIAGNOSTIC,
) -> EvidenceDatasetRecord:
    task_id = str(row.get("task_id") or row.get("benchmark_id") or "unknown")
    capability = str(row.get("capability") or row.get("expected_capability") or row.get("route_capability") or "unknown")
    skill_id = str(row.get("skill_id") or row.get("expected_skill") or row.get("skill") or "")
    provider_cleanliness = _provider_token_cleanliness(row)
    evidence_refs = _refs(row, ("evidence_record_file", "evidence_bundle_file", "report_file"), fallback=source_path)
    receipt_refs = _refs(row, ("receipt_file", "runtime_receipt_file", "route_receipt_file"))
    if not receipt_refs and (row.get("capability_receipts") or row.get("capability_receipts_json")):
        receipt_refs.append(f"capability_receipts:{task_id}")
    blockers = [str(item) for item in row.get("data_contract_violation_reasons", []) or []]
    blockers.extend(str(item) for item in row.get("blockers", []) or [])
    evidence_seal_status = str(row.get("evidence_seal_status") or "NOT_APPLICABLE").upper()
    evidence_hash_status = str(row.get("evidence_hash_status") or "NOT_APPLICABLE").upper()
    if bool(row.get("partial_telemetry_detected", False)):
        blockers.append("partial_telemetry_detected")
    status = str(row.get("status") or row.get("rubric_status") or "UNKNOWN").upper()
    delivery_status = status
    trust_status = "RETURN" if bool(row.get("trust_mismatch", False)) else "PASS"
    capability_outcome = "verified" if status in {"SUCCESS", "PASS"} and trust_status == "PASS" else "not_verified"
    skill_effect_status = "not_applicable" if not skill_id else ("candidate_effective" if capability_outcome == "verified" else "not_confirmed")
    return EvidenceDatasetRecord(
        record_id=_stable_record_id(source_path, task_id, capability, skill_id, status),
        source_path=source_path,
        source_schema=str(row.get("schema") or row.get("schema_version") or "benchmark_row"),
        task_id=task_id,
        capability=capability,
        skill_id=skill_id,
        route_id=str(row.get("route_id") or row.get("route") or capability),
        claim_class=_claim_class(claim_class),
        provider_token_cleanliness=provider_cleanliness,
        delivery_status=delivery_status,
        trust_status=trust_status,
        capability_outcome=capability_outcome,
        skill_effect_status=skill_effect_status,
        evidence_refs=tuple(evidence_refs),
        receipt_refs=tuple(receipt_refs),
        phase_wall_sec=_phase_wall_from_row(row),
        token_counts={
            "total": _int_or_none(row.get("total_tokens") or row.get("totaltokens")),
            "prompt": _int_or_none(row.get("prompt_tokens")),
            "completion": _int_or_none(row.get("completion_tokens")),
            "model_calls": _int_or_none(row.get("model_calls") or row.get("modelcalls")),
        },
        gate_status={
            "delivery": delivery_status,
            "trust": trust_status,
            "provider_token": provider_cleanliness.value,
            "evidence_seal": evidence_seal_status,
            "evidence_hash": evidence_hash_status,
        },
        evidence_seal_status=evidence_seal_status,
        evidence_hash_status=evidence_hash_status,
        partial_telemetry_detected=bool(row.get("partial_telemetry_detected", False)),
        blockers=tuple(sorted(set(item for item in blockers if item))),
    )


def build_evidence_dataset_manifest(
    records: list[EvidenceDatasetRecord],
    *,
    source_path: str,
    claim_class: ClaimClass | str,
) -> dict[str, Any]:
    payload_rows = [record.to_dict() for record in records]
    claim = _claim_class(claim_class)
    return {
        "schema": EVIDENCE_DATASET_MANIFEST_SCHEMA,
        "source_path": source_path,
        "claim_class": claim.value,
        "record_count": len(payload_rows),
        "provider_token_cleanliness_counts": _count(row["provider_token_cleanliness"] for row in payload_rows),
        "capability_outcome_counts": _count(row["capability_outcome"] for row in payload_rows),
        "skill_effect_status_counts": _count(row["skill_effect_status"] for row in payload_rows),
        "blocker_count": sum(1 for row in payload_rows if row["blockers"]),
        "public_benchmark_allowed": False,
        "runtime_update_allowed": claim == ClaimClass.RUNTIME_APPLY_REVIEW and all(not row["blockers"] for row in payload_rows),
        "rows": payload_rows,
    }


def validate_evidence_dataset_record(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key in ("record_id", "source_path", "task_id", "capability", "claim_class", "provider_token_cleanliness"):
        if not str(payload.get(key) or "").strip():
            blockers.append(f"missing_{key}")
    try:
        _claim_class(payload.get("claim_class"))
    except ValueError:
        blockers.append("invalid_claim_class")
    try:
        _provider_token_cleanliness_value(payload.get("provider_token_cleanliness"))
    except ValueError:
        blockers.append("invalid_provider_token_cleanliness")
    if payload.get("claim_class") == ClaimClass.PUBLIC_READY.value and not payload.get("evidence_refs"):
        blockers.append("public_ready_requires_evidence_refs")
    if bool(payload.get("partial_telemetry_detected", False)):
        blockers.append("partial_telemetry_detected")
    if payload.get("claim_class") == ClaimClass.PUBLIC_READY.value:
        if str(payload.get("evidence_seal_status") or "").upper() != "PASS":
            blockers.append("public_ready_requires_evidence_seal")
        if str(payload.get("evidence_hash_status") or "").upper() != "PASS":
            blockers.append("public_ready_requires_evidence_hash")
    return sorted(set(blockers))


def _provider_token_cleanliness(row: Mapping[str, Any]) -> ProviderTokenCleanliness:
    model_calls = _int_or_none(row.get("model_calls") or row.get("modelcalls")) or 0
    if model_calls <= 0:
        return ProviderTokenCleanliness.NOT_APPLICABLE
    if bool(row.get("provider_token_measured", False)):
        return ProviderTokenCleanliness.MEASURED
    source = str(row.get("raw_provider_token_source") or row.get("provider_token_source") or "").lower()
    if source == "estimated":
        return ProviderTokenCleanliness.ESTIMATED
    return ProviderTokenCleanliness.MISSING


def _claim_class(value: ClaimClass | str | Any) -> ClaimClass:
    if isinstance(value, ClaimClass):
        return value
    return ClaimClass(str(value))


def _provider_token_cleanliness_value(value: ProviderTokenCleanliness | str | Any) -> ProviderTokenCleanliness:
    if isinstance(value, ProviderTokenCleanliness):
        return value
    return ProviderTokenCleanliness(str(value))


def _phase_wall_from_row(row: Mapping[str, Any]) -> dict[str, float | None]:
    return {phase: _float_or_none(row.get(f"phase_wall_{phase.lower()}_sec")) for phase in PHASES}


def _refs(row: Mapping[str, Any], keys: tuple[str, ...], *, fallback: str = "") -> list[str]:
    refs: list[str] = []
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value and value not in refs:
            refs.append(value)
    if fallback and fallback not in refs:
        refs.append(fallback)
    return refs


def _stable_record_id(*parts: str) -> str:
    digest = hashlib.sha256("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"evidence:{digest}"


def _pass_return(value: Any) -> str:
    return "PASS" if bool(value) else "RETURN"


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
