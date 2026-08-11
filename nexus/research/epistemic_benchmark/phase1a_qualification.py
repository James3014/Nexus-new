from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from nexus.research.epistemic_benchmark.phase1a_contracts import (
    compute_canonical_sha256,
)

SIX_ARM_PERMUTATIONS: tuple[str, ...] = (
    "ABC",
    "ACB",
    "BAC",
    "BCA",
    "CAB",
    "CBA",
)


class RunKind(str, Enum):
    QUALIFICATION = "QUALIFICATION"
    FORMAL = "FORMAL"


class QualificationStatus(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"


class RunClassification(str, Enum):
    VALID_SUCCESS = "VALID_SUCCESS"
    VALID_FAILURE = "VALID_FAILURE"
    INFRA_INVALID = "INFRA_INVALID"
    TREATMENT_INVALID = "TREATMENT_INVALID"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"


@dataclass(frozen=True)
class Phase1AFrozenManifest:
    phase1a_contract_hash: str
    repository_source_snapshots: Mapping[str, str]
    qualification_task_ids: tuple[str, ...]
    formal_task_ids: tuple[str, ...]
    arm_semantics_hash: str
    treatment_fingerprint_policy_hash: str
    planner_route_policy_hash: str
    online_prompt_policy_hash: str
    final_verifier_contract_hash: str
    quality_gate_contract_hash: str
    deterministic_pipeline_hash: str
    evidence_observation_contract_hash: str
    provider_safe_projection_contract_hash: str
    consumption_proof_contract_hash: str
    settlement_contract_hash: str
    trajectory_schema_hash: str
    action_normalization_rule_hash: str
    recomputation_formula_hash: str
    invalid_run_taxonomy_hash: str
    online_provider: str
    online_model: str
    local_provider: str
    local_model: str
    accounting_policy_hash: str
    pairing_rule_hash: str
    execution_order_rule_id: str
    execution_order_seed: int
    meaningful_improvement_thresholds: Mapping[str, float]
    report_schema_verifier_hash: str
    required_issue29_evidence_identity: str
    manifest_version: str
    manifest_sha256: str = field(init=False)
    _frozen_body_json: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        hash_fields = (
            "phase1a_contract_hash",
            "arm_semantics_hash",
            "treatment_fingerprint_policy_hash",
            "planner_route_policy_hash",
            "online_prompt_policy_hash",
            "final_verifier_contract_hash",
            "quality_gate_contract_hash",
            "deterministic_pipeline_hash",
            "evidence_observation_contract_hash",
            "provider_safe_projection_contract_hash",
            "consumption_proof_contract_hash",
            "settlement_contract_hash",
            "trajectory_schema_hash",
            "action_normalization_rule_hash",
            "recomputation_formula_hash",
            "invalid_run_taxonomy_hash",
            "accounting_policy_hash",
            "pairing_rule_hash",
            "report_schema_verifier_hash",
            "required_issue29_evidence_identity",
        )
        for name in hash_fields:
            _require_sha256(name, getattr(self, name))

        snapshots = _validate_string_mapping(
            "repository_source_snapshots",
            self.repository_source_snapshots,
        )
        thresholds = _validate_thresholds(self.meaningful_improvement_thresholds)
        qualification_ids = _validate_task_ids(
            "qualification_task_ids",
            self.qualification_task_ids,
        )
        formal_ids = _validate_task_ids("formal_task_ids", self.formal_task_ids)
        if set(qualification_ids) & set(formal_ids):
            raise ValueError("qualification/formal task identities must be disjoint")

        _require_exact_identity("online_provider", self.online_provider)
        _require_exact_identity("online_model", self.online_model)
        _require_exact_identity("local_provider", self.local_provider)
        _require_exact_identity("local_model", self.local_model)
        _require_text("execution_order_rule_id", self.execution_order_rule_id)
        _require_nonnegative_int("execution_order_seed", self.execution_order_seed)
        _require_text("manifest_version", self.manifest_version)

        object.__setattr__(
            self,
            "repository_source_snapshots",
            MappingProxyType(snapshots),
        )
        object.__setattr__(
            self,
            "meaningful_improvement_thresholds",
            MappingProxyType(thresholds),
        )
        object.__setattr__(self, "qualification_task_ids", qualification_ids)
        object.__setattr__(self, "formal_task_ids", formal_ids)

        body = self._manifest_body()
        manifest_hash = _stable_hash(body)
        object.__setattr__(
            self,
            "_frozen_body_json",
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
        object.__setattr__(self, "manifest_sha256", manifest_hash)

    def _manifest_body(self) -> dict[str, Any]:
        return {
            "phase1a_contract_hash": self.phase1a_contract_hash,
            "repository_source_snapshots": dict(self.repository_source_snapshots),
            "qualification_task_ids": list(self.qualification_task_ids),
            "formal_task_ids": list(self.formal_task_ids),
            "arm_semantics_hash": self.arm_semantics_hash,
            "treatment_fingerprint_policy_hash": self.treatment_fingerprint_policy_hash,
            "planner_route_policy_hash": self.planner_route_policy_hash,
            "online_prompt_policy_hash": self.online_prompt_policy_hash,
            "final_verifier_contract_hash": self.final_verifier_contract_hash,
            "quality_gate_contract_hash": self.quality_gate_contract_hash,
            "deterministic_pipeline_hash": self.deterministic_pipeline_hash,
            "evidence_observation_contract_hash": self.evidence_observation_contract_hash,
            "provider_safe_projection_contract_hash": self.provider_safe_projection_contract_hash,
            "consumption_proof_contract_hash": self.consumption_proof_contract_hash,
            "settlement_contract_hash": self.settlement_contract_hash,
            "trajectory_schema_hash": self.trajectory_schema_hash,
            "action_normalization_rule_hash": self.action_normalization_rule_hash,
            "recomputation_formula_hash": self.recomputation_formula_hash,
            "invalid_run_taxonomy_hash": self.invalid_run_taxonomy_hash,
            "online_provider": self.online_provider,
            "online_model": self.online_model,
            "local_provider": self.local_provider,
            "local_model": self.local_model,
            "accounting_policy_hash": self.accounting_policy_hash,
            "pairing_rule_hash": self.pairing_rule_hash,
            "execution_order_rule_id": self.execution_order_rule_id,
            "execution_order_seed": self.execution_order_seed,
            "meaningful_improvement_thresholds": dict(self.meaningful_improvement_thresholds),
            "report_schema_verifier_hash": self.report_schema_verifier_hash,
            "required_issue29_evidence_identity": self.required_issue29_evidence_identity,
            "manifest_version": self.manifest_version,
        }

    def to_dict(self) -> dict[str, Any]:
        body = json.loads(self._frozen_body_json)
        body["manifest_sha256"] = self.manifest_sha256
        return body


@dataclass(frozen=True)
class ManifestCompatibility:
    compatible_same_cohort: bool
    reason: str
    left_manifest_sha256: str
    right_manifest_sha256: str


def compare_frozen_manifests(
    left: Phase1AFrozenManifest,
    right: Phase1AFrozenManifest,
) -> ManifestCompatibility:
    if left.manifest_sha256 == right.manifest_sha256:
        return ManifestCompatibility(
            compatible_same_cohort=True,
            reason="SAME_FROZEN_MANIFEST",
            left_manifest_sha256=left.manifest_sha256,
            right_manifest_sha256=right.manifest_sha256,
        )
    return ManifestCompatibility(
        compatible_same_cohort=False,
        reason="NEW_MANIFEST_VERSION_REQUIRED",
        left_manifest_sha256=left.manifest_sha256,
        right_manifest_sha256=right.manifest_sha256,
    )


@dataclass(frozen=True)
class OrderAssignment:
    task_id: str
    permutation: str


def assign_counterbalanced_orders(
    formal_task_ids: tuple[str, ...],
    seed: int,
) -> tuple[OrderAssignment, ...]:
    task_ids = _validate_task_ids("formal_task_ids", formal_task_ids)
    _require_nonnegative_int("seed", seed)
    if not task_ids:
        return ()

    ordered = sorted(
        task_ids,
        key=lambda task_id: (
            hashlib.sha256(f"{seed}:{task_id}".encode()).hexdigest(),
            task_id,
        ),
    )
    offset = int(hashlib.sha256(f"offset:{seed}".encode()).hexdigest(), 16) % len(
        SIX_ARM_PERMUTATIONS
    )
    assignments = tuple(
        OrderAssignment(
            task_id=task_id,
            permutation=SIX_ARM_PERMUTATIONS[(offset + index) % len(SIX_ARM_PERMUTATIONS)],
        )
        for index, task_id in enumerate(ordered)
    )
    counts = Counter(item.permutation for item in assignments)
    populated = [counts[permutation] for permutation in SIX_ARM_PERMUTATIONS]
    if max(populated) - min(populated) > 1:
        raise AssertionError("counterbalanced assignment exceeded one-count imbalance")
    return assignments


@dataclass(frozen=True)
class RunValidityEvidence:
    semantic_success: bool
    provider_runtime_ok: bool = True
    fixture_ok: bool = True
    required_telemetry_complete: bool = True
    treatment_identity_ok: bool = True
    complete_triplet: bool = True
    forbidden_local_call_in_b: bool = False
    source_integrity_ok: bool = True
    report_integrity_ok: bool = True
    receipt_integrity_ok: bool = True
    manifest_identity_ok: bool = True

    def __post_init__(self) -> None:
        for name in (
            "semantic_success",
            "provider_runtime_ok",
            "fixture_ok",
            "required_telemetry_complete",
            "treatment_identity_ok",
            "complete_triplet",
            "forbidden_local_call_in_b",
            "source_integrity_ok",
            "report_integrity_ok",
            "receipt_integrity_ok",
            "manifest_identity_ok",
        ):
            _require_boolean(name, getattr(self, name))


def classify_run(evidence: RunValidityEvidence) -> RunClassification:
    integrity_ok = (
        evidence.source_integrity_ok
        and evidence.report_integrity_ok
        and evidence.receipt_integrity_ok
        and evidence.manifest_identity_ok
    )
    if not integrity_ok:
        return RunClassification.INTEGRITY_INVALID
    treatment_ok = (
        evidence.treatment_identity_ok
        and evidence.complete_triplet
        and not evidence.forbidden_local_call_in_b
    )
    if not treatment_ok:
        return RunClassification.TREATMENT_INVALID
    infra_ok = (
        evidence.provider_runtime_ok
        and evidence.fixture_ok
        and evidence.required_telemetry_complete
    )
    if not infra_ok:
        return RunClassification.INFRA_INVALID
    if evidence.semantic_success:
        return RunClassification.VALID_SUCCESS
    return RunClassification.VALID_FAILURE


@dataclass(frozen=True)
class Phase1ARunRow:
    task_id: str
    run_kind: RunKind
    classification: RunClassification
    metrics: Mapping[str, float | int | None]

    def __post_init__(self) -> None:
        _require_text("task_id", self.task_id)
        if not isinstance(self.run_kind, RunKind):
            raise ValueError("run_kind must be a RunKind")
        if not isinstance(self.classification, RunClassification):
            raise ValueError("classification must be a RunClassification")
        if not isinstance(self.metrics, Mapping):
            raise ValueError("metrics must be a mapping")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))


def select_formal_effect_rows(
    manifest: Phase1AFrozenManifest,
    rows: tuple[Phase1ARunRow, ...],
) -> tuple[Phase1ARunRow, ...]:
    qualification_ids = set(manifest.qualification_task_ids)
    formal_ids = set(manifest.formal_task_ids)
    selected: list[Phase1ARunRow] = []
    for row in rows:
        if row.run_kind == RunKind.QUALIFICATION:
            if row.task_id not in qualification_ids:
                raise ValueError("qualification row task identity is outside qualification corpus")
            continue
        if row.task_id not in formal_ids:
            raise ValueError("formal row task identity is outside formal corpus")
        if row.classification in (
            RunClassification.VALID_SUCCESS,
            RunClassification.VALID_FAILURE,
        ):
            selected.append(row)
    return tuple(selected)


@dataclass(frozen=True)
class QualificationResult:
    status: QualificationStatus
    qualification_task_ids: tuple[str, ...]
    readiness_evidence_refs: tuple[str, ...]
    measurement_noise_summary: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.status, QualificationStatus):
            raise ValueError("status must be a QualificationStatus")
        object.__setattr__(
            self,
            "qualification_task_ids",
            _validate_task_ids("qualification_task_ids", self.qualification_task_ids),
        )
        _require_text_tuple("readiness_evidence_refs", self.readiness_evidence_refs)
        noise: dict[str, float] = {}
        if not isinstance(self.measurement_noise_summary, Mapping):
            raise ValueError("measurement_noise_summary must be a mapping")
        for key, value in self.measurement_noise_summary.items():
            _require_text("measurement_noise_key", key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError("measurement noise values must be numeric")
            numeric = float(value)
            if not math.isfinite(numeric) or numeric < 0:
                raise ValueError("measurement noise values must be finite and non-negative")
            noise[key] = numeric
        object.__setattr__(self, "measurement_noise_summary", MappingProxyType(noise))

    @property
    def formal_effect_allowed(self) -> bool:
        return False


@dataclass(frozen=True)
class Issue29PrerequisiteEvidence:
    evidence_identity: str
    acceptance_receipt_sha256: str
    verified_source_revision: str
    independently_accepted: bool

    def __post_init__(self) -> None:
        _require_sha256("evidence_identity", self.evidence_identity)
        _require_sha256("acceptance_receipt_sha256", self.acceptance_receipt_sha256)
        _require_text("verified_source_revision", self.verified_source_revision)
        if self.independently_accepted is not True:
            raise ValueError("Issue #29 evidence must be independently accepted")


@dataclass(frozen=True)
class PreformalReadiness:
    preformal_ready: bool
    reasons: tuple[str, ...]
    g5_authorized: bool = False


def evaluate_preformal_readiness(
    manifest: Phase1AFrozenManifest,
    *,
    issue29_evidence: Issue29PrerequisiteEvidence | None,
    current_report_schema_verifier_hash: str | None,
) -> PreformalReadiness:
    reasons: list[str] = []
    if issue29_evidence is None:
        reasons.append("ISSUE29_EVIDENCE_MISSING")
    elif not isinstance(issue29_evidence, Issue29PrerequisiteEvidence):
        raise ValueError("Issue #29 prerequisite requires identity-bound evidence")
    elif issue29_evidence.evidence_identity != manifest.required_issue29_evidence_identity:
        reasons.append("ISSUE29_EVIDENCE_IDENTITY_MISMATCH")

    if current_report_schema_verifier_hash is None:
        reasons.append("REPORT_SCHEMA_VERIFIER_EVIDENCE_MISSING")
    else:
        _require_sha256(
            "current_report_schema_verifier_hash",
            current_report_schema_verifier_hash,
        )
        if current_report_schema_verifier_hash != manifest.report_schema_verifier_hash:
            reasons.append("REPORT_SCHEMA_VERIFIER_IDENTITY_MISMATCH")

    return PreformalReadiness(
        preformal_ready=not reasons,
        reasons=tuple(reasons) if reasons else ("PREFORMAL_PREREQUISITES_SATISFIED",),
        g5_authorized=False,
    )


def _validate_task_ids(name: str, values: Any) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    if not values:
        raise ValueError(f"{name} must be non-empty")
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        _require_text(name, value)
        if value in seen:
            raise ValueError(f"{name} contains duplicate task identity")
        seen.add(value)
        normalized.append(value)
    return tuple(sorted(normalized))


def _validate_string_mapping(name: str, values: Any) -> dict[str, str]:
    if not isinstance(values, Mapping) or not values:
        raise ValueError(f"{name} must be a non-empty mapping")
    copied: dict[str, str] = {}
    for key, value in values.items():
        _require_text(f"{name}.key", key)
        _require_text(f"{name}[{key}]", value)
        copied[str(key)] = str(value)
    _stable_hash(copied)
    return copy.deepcopy(copied)


def _validate_thresholds(values: Any) -> dict[str, float]:
    if not isinstance(values, Mapping) or not values:
        raise ValueError("meaningful_improvement_thresholds must be explicit and non-empty")
    normalized: dict[str, float] = {}
    for key, value in values.items():
        _require_text("meaningful_improvement_threshold_key", key)
        if key.lower().startswith("vap_") or "legacy" in key.lower():
            raise ValueError("legacy VAP threshold identity cannot be inherited")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("meaningful improvement threshold values must be numeric")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError("meaningful improvement thresholds must be finite")
        normalized[key] = numeric
    _stable_hash(normalized)
    return normalized


def _require_exact_identity(name: str, value: Any) -> None:
    _require_text(name, value)
    lowered = value.lower()
    if lowered in {"default", "latest", "auto", "unknown"}:
        raise ValueError(f"{name} must be an exact bound identity")
    if any(char.isspace() for char in value) or "(" in value or ")" in value:
        raise ValueError(f"{name} must be an exact machine identity, not a display label")


def _require_text(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_text_tuple(name: str, values: Any) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple")
    for value in values:
        _require_text(name, value)


def _require_sha256(name: str, value: Any) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest") from exc
    if value.lower() != value:
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _require_nonnegative_int(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_boolean(name: str, value: Any) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")


def _stable_hash(payload: Any) -> str:
    try:
        return compute_canonical_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "decision-bearing manifest input contains an unordered or invalid value"
        ) from exc
