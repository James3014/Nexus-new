from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from nexus.contracts.optimization_report import ClaimClass, ProviderTokenCleanliness


CLAIM_EVIDENCE_READ_MODEL_SCHEMA = "nexus.claim_evidence_read_model.v1"
PASS_STATUSES = {"PASS", "SUCCESS", "VERIFIED"}


@dataclass(frozen=True)
class ClaimEvidenceGate:
    name: str
    status: str
    evidence_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "receipt_refs": list(self.receipt_refs),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class ClaimEvidenceReadModel:
    claim_class: ClaimClass
    gates: tuple[ClaimEvidenceGate, ...]
    evidence_bundle_refs: tuple[str, ...]
    receipt_refs: tuple[str, ...]
    provider_token_cleanliness: ProviderTokenCleanliness
    source_records: tuple[Mapping[str, Any], ...] = ()
    status: str = "PASS"
    sealed_evidence_required: bool = False
    schema: str = CLAIM_EVIDENCE_READ_MODEL_SCHEMA
    blockers: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema": self.schema,
            "status": self.status,
            "claim_class": self.claim_class.value,
            "provider_token_cleanliness": self.provider_token_cleanliness.value,
            "sealed_evidence_required": self.sealed_evidence_required,
            "evidence_bundle_refs": list(self.evidence_bundle_refs),
            "receipt_refs": list(self.receipt_refs),
            "records": [dict(record) for record in self.source_records],
            "gates": [gate.to_dict() for gate in self.gates],
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
            "claim_boundary": [
                "Claim evidence read models summarize evidence only.",
                "They do not mutate runtime policy or unlock public benchmarks.",
            ],
            "blockers": list(self.blockers),
        }
        payload["blockers"] = validate_claim_evidence_read_model(payload)
        payload["status"] = "PASS" if not payload["blockers"] else "RETURN"
        return payload


def build_claim_evidence_read_model(
    *,
    claim_class: ClaimClass | str,
    records: list[Mapping[str, Any]],
    evidence_bundle_refs: list[str] | tuple[str, ...] = (),
    receipt_refs: list[str] | tuple[str, ...] = (),
    sealed_evidence_required: bool = False,
) -> dict[str, Any]:
    claim = _claim_class(claim_class)
    gates = _gates_from_records(records)
    provider_cleanliness = _provider_token_cleanliness(records)
    model = ClaimEvidenceReadModel(
        claim_class=claim,
        gates=tuple(gates),
        evidence_bundle_refs=tuple(str(item) for item in evidence_bundle_refs if str(item).strip()),
        receipt_refs=tuple(str(item) for item in receipt_refs if str(item).strip()),
        provider_token_cleanliness=provider_cleanliness,
        source_records=tuple(records),
        sealed_evidence_required=bool(sealed_evidence_required),
    )
    return model.to_dict()


def validate_claim_evidence_read_model(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    try:
        claim = _claim_class(payload.get("claim_class"))
    except ValueError:
        blockers.append("invalid_claim_class")
        claim = None
    try:
        token_cleanliness = _provider_token_cleanliness_value(
            payload.get("provider_token_cleanliness", ProviderTokenCleanliness.NOT_APPLICABLE.value)
        )
    except ValueError:
        blockers.append("invalid_provider_token_cleanliness")
        token_cleanliness = None

    gates = payload.get("gates", [])
    if not isinstance(gates, list) or not gates:
        blockers.append("missing_gates")
        gates = []
    for gate in gates:
        gate = gate if isinstance(gate, Mapping) else {}
        name = str(gate.get("name") or "unknown")
        status = str(gate.get("status") or "").upper()
        if status not in PASS_STATUSES:
            blockers.append(f"{name}:gate_not_pass")
        if gate.get("blockers"):
            blockers.append(f"{name}:gate_has_blockers")

    evidence_refs = _non_empty_strings(payload.get("evidence_bundle_refs", []))
    receipt_refs = _non_empty_strings(payload.get("receipt_refs", []))
    if claim in {ClaimClass.RUNTIME_APPLY_REVIEW, ClaimClass.PUBLIC_READY} and not evidence_refs:
        blockers.append("missing_evidence_bundle_refs")
    if claim in {ClaimClass.RUNTIME_APPLY_REVIEW, ClaimClass.PUBLIC_READY} and not receipt_refs:
        blockers.append("missing_receipt_refs")
    if claim == ClaimClass.PUBLIC_READY and token_cleanliness not in {
        ProviderTokenCleanliness.MEASURED,
        ProviderTokenCleanliness.NOT_APPLICABLE,
    }:
        blockers.append("public_ready_requires_measured_or_not_applicable_tokens")
    if bool(payload.get("sealed_evidence_required", False)):
        for gate in _sealed_evidence_gates(payload):
            blockers.append(gate)
    if bool(payload.get("runtime_update_allowed", False)):
        blockers.append("read_model_must_not_update_runtime")
    if bool(payload.get("public_benchmark_allowed", False)):
        blockers.append("read_model_must_not_unlock_public_benchmark")
    return sorted(set(blockers))


def _sealed_evidence_gates(payload: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        blockers.append("sealed_evidence_requires_records")
        return blockers
    for index, record in enumerate(records):
        record = record if isinstance(record, Mapping) else {}
        if str(record.get("evidence_seal_status") or "").upper() != "PASS":
            blockers.append(f"record_{index}:evidence_seal_not_pass")
        if str(record.get("evidence_hash_status") or "").upper() != "PASS":
            blockers.append(f"record_{index}:evidence_hash_not_pass")
    return blockers


def _gates_from_records(records: list[Mapping[str, Any]]) -> list[ClaimEvidenceGate]:
    if not records:
        return [ClaimEvidenceGate("record_presence", "RETURN", blockers=("missing_records",))]

    delivery_statuses: list[str] = []
    trust_statuses: list[str] = []
    artifact_refs: list[str] = []
    receipt_refs: list[str] = []
    blockers: list[str] = []
    for record in records:
        delivery_statuses.append(str(record.get("delivery_status") or "UNKNOWN").upper())
        trust_statuses.append(str(record.get("trust_status") or "UNKNOWN").upper())
        artifact_refs.extend(_non_empty_strings(record.get("evidence_refs", [])))
        receipt_refs.extend(_non_empty_strings(record.get("receipt_refs", [])))
        blockers.extend(_non_empty_strings(record.get("blockers", [])))

    delivery_ok = all(status in PASS_STATUSES for status in delivery_statuses)
    trust_ok = all(status in PASS_STATUSES for status in trust_statuses)
    artifact_ok = bool(artifact_refs)
    receipt_ok = bool(receipt_refs)
    claim_ok = delivery_ok and trust_ok and artifact_ok and receipt_ok and not blockers
    return [
        ClaimEvidenceGate("delivery", "PASS" if delivery_ok else "RETURN"),
        ClaimEvidenceGate("trust", "PASS" if trust_ok else "RETURN"),
        ClaimEvidenceGate("artifact", "PASS" if artifact_ok else "RETURN", evidence_refs=tuple(sorted(set(artifact_refs)))),
        ClaimEvidenceGate("receipt", "PASS" if receipt_ok else "RETURN", receipt_refs=tuple(sorted(set(receipt_refs)))),
        ClaimEvidenceGate("claim", "PASS" if claim_ok else "RETURN", blockers=tuple(sorted(set(blockers)))),
    ]


def _provider_token_cleanliness(records: list[Mapping[str, Any]]) -> ProviderTokenCleanliness:
    values = {
        _provider_token_cleanliness_value(record.get("provider_token_cleanliness", ProviderTokenCleanliness.NOT_APPLICABLE.value))
        for record in records
    }
    if not values:
        return ProviderTokenCleanliness.NOT_APPLICABLE
    if len(values) == 1:
        return next(iter(values))
    clean_values = values - {ProviderTokenCleanliness.NOT_APPLICABLE}
    if len(clean_values) == 1:
        return next(iter(clean_values))
    return ProviderTokenCleanliness.MIXED


def _non_empty_strings(raw: Any) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list | tuple):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _claim_class(value: ClaimClass | str | Any) -> ClaimClass:
    if isinstance(value, ClaimClass):
        return value
    return ClaimClass(str(value))


def _provider_token_cleanliness_value(value: ProviderTokenCleanliness | str | Any) -> ProviderTokenCleanliness:
    if isinstance(value, ProviderTokenCleanliness):
        return value
    return ProviderTokenCleanliness(str(value))
