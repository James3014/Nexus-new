from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DeterministicMutant:
    mutant_id: str
    concern: str
    description: str
    mutant_diff: str
    expected_detector: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DETERMINISTIC_MUTANTS: tuple[DeterministicMutant, ...] = (
    DeterministicMutant(
        mutant_id="claim_always_true",
        concern="claim_integrity",
        description="Completion claim is forced true without evidence.",
        mutant_diff="- claim_verified = evidence_present\n+ claim_verified = True",
        expected_detector="claim_gate",
    ),
    DeterministicMutant(
        mutant_id="delivery_ignores_evidence",
        concern="delivery_integrity",
        description="Delivery gate passes even when evidence is absent.",
        mutant_diff="- delivery_gate_passed = bool(evidence_refs)\n+ delivery_gate_passed = True",
        expected_detector="delivery_gate",
    ),
    DeterministicMutant(
        mutant_id="policy_deny_to_allow",
        concern="governance_safety",
        description="Policy deny branch is inverted into allow.",
        mutant_diff="- return deny(reason)\n+ return allow(reason)",
        expected_detector="mempalace_gate",
    ),
    DeterministicMutant(
        mutant_id="assertion_removed",
        concern="test_strength",
        description="Critical assertion is removed from a test.",
        mutant_diff="- assert invariant_holds(result)\n+ result",
        expected_detector="jit_validation",
    ),
    DeterministicMutant(
        mutant_id="boundary_condition_flip",
        concern="behavior_boundary",
        description="Inclusive boundary is flipped to exclusive.",
        mutant_diff="- value >= limit\n+ value > limit",
        expected_detector="acceptance_check",
    ),
    DeterministicMutant(
        mutant_id="public_safe_forced_true",
        concern="public_claim_safety",
        description="Receipt public safety is forced true despite gate failure.",
        mutant_diff="- public_claim_safe = gate_passed and evidence_present\n+ public_claim_safe = True",
        expected_detector="capability_receipt_policy",
    ),
)

_MAX_MUTATION_RECORDS = 1_000
_ISSUE16_TARGET = next(
    mutant for mutant in DETERMINISTIC_MUTANTS if mutant.mutant_id == "public_safe_forced_true"
)
_MUTATION_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "concern",
        "mutant_id",
        "mutant_diff",
        "original_passed",
        "mutant_failed",
        "equivalent_suspected",
        "killed",
        "assurance_status",
        "evidence_refs",
    }
)
_MUTATION_RECORD_BASE_FIELDS = _MUTATION_RECORD_FIELDS - {"evidence_refs"}


def _bounded_mapping_records(records: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(records, (str, bytes, bytearray, Mapping)):
        return [], ["records_invalid_type"]
    try:
        iterator = iter(records)
    except Exception:
        return [], ["records_invalid_type"]

    rows: list[dict[str, Any]] = []
    failures: set[str] = set()
    try:
        for index, row in enumerate(iterator):
            if index >= _MAX_MUTATION_RECORDS:
                return [], ["records_not_finite_or_too_large"]
            if not isinstance(row, Mapping):
                failures.add("mutation_record_invalid_type")
                continue
            try:
                rows.append(dict(row))
            except Exception:
                failures.add("mutation_record_invalid_type")
    except Exception:
        return [], ["records_iteration_failed"]
    return rows, sorted(failures)


def _issue16_target_record_failure(record: Mapping[str, Any]) -> str | None:
    if not _MUTATION_RECORD_BASE_FIELDS.issubset(record):
        return "mutation_record_schema_invalid"
    if (
        record.get("schema_version") != "nexus_mutation_assurance.v1"
        or type(record.get("concern")) is not str
        or record.get("concern") != _ISSUE16_TARGET.concern
        or type(record.get("mutant_id")) is not str
        or record.get("mutant_id") != _ISSUE16_TARGET.mutant_id
        or type(record.get("mutant_diff")) is not str
        or record.get("mutant_diff") != _ISSUE16_TARGET.mutant_diff
        or type(record.get("assurance_status")) is not str
        or any(
            type(record.get(field)) is not bool
            for field in (
                "original_passed",
                "mutant_failed",
                "equivalent_suspected",
                "killed",
            )
        )
    ):
        return "mutation_record_schema_invalid"

    if "evidence_refs" not in record:
        return "evidence_refs_missing"
    if type(record["evidence_refs"]) not in (list, tuple):
        return "evidence_refs_invalid_type"
    if not record["evidence_refs"]:
        return "evidence_refs_empty"
    if any(type(item) is str and not item.strip() for item in record["evidence_refs"]):
        return "evidence_ref_blank"
    if any(
        type(item) is not str or item != item.strip() or not item.isprintable()
        for item in record["evidence_refs"]
    ):
        return "evidence_ref_malformed"
    if len(set(record["evidence_refs"])) != len(record["evidence_refs"]):
        return "evidence_ref_duplicate"

    original_passed = record["original_passed"]
    mutant_failed = record["mutant_failed"]
    equivalent_suspected = record["equivalent_suspected"]
    expected_killed = original_passed and mutant_failed and not equivalent_suspected
    if equivalent_suspected:
        expected_status = "EQUIVALENT_SUSPECTED"
    elif expected_killed:
        expected_status = "KILLED"
    elif original_passed and not mutant_failed:
        expected_status = "SURVIVED_BLIND_SPOT"
    else:
        expected_status = "INVALID_ORIGINAL_FAILURE"
    if record["killed"] is not expected_killed or record["assurance_status"] != expected_status:
        return "mutation_record_semantics_invalid"
    return None


def _canonical_record_sort_key(record: Mapping[str, Any]) -> tuple[str, ...]:
    return (
        str(record.get("concern") or ""),
        str(record.get("mutant_id") or ""),
        str(record.get("assurance_status") or ""),
        str(record.get("mutant_diff") or ""),
        repr(record.get("evidence_refs")),
    )


def _normalize_issue16_risk_inputs(
    risk_inputs: Any,
) -> tuple[dict[str, Any], bool, bool]:
    if not isinstance(risk_inputs, Mapping):
        return {"risk_score": 0, "public_claim": False, "high_risk": False}, False, True
    try:
        inputs = dict(risk_inputs)
    except Exception:
        return {"risk_score": 0, "public_claim": False, "high_risk": False}, False, True

    risk_score = inputs.get("risk_score", 0)
    public_claim = inputs.get("public_claim", False)
    explicit_high_risk = inputs.get("high_risk", False)
    invalid = (
        ("risk_score" in inputs and (type(risk_score) is not int or not 0 <= risk_score <= 100))
        or ("public_claim" in inputs and type(public_claim) is not bool)
        or ("high_risk" in inputs and type(explicit_high_risk) is not bool)
    )
    if invalid:
        return {"risk_score": 0, "public_claim": False, "high_risk": False}, False, True

    high_risk = explicit_high_risk or risk_score >= 70
    triggered = public_claim or high_risk
    qualifying_low_risk = "risk_score" in inputs and "public_claim" in inputs
    if not triggered and not qualifying_low_risk:
        invalid = True
    return (
        {
            "risk_score": risk_score,
            "public_claim": public_claim,
            "high_risk": high_risk,
        },
        triggered,
        invalid,
    )


def deterministic_mutants_for_concern(concern: str | None = None) -> list[dict[str, Any]]:
    wanted = str(concern or "").strip()
    mutants = DETERMINISTIC_MUTANTS
    if wanted:
        mutants = tuple(item for item in mutants if item.concern == wanted)
    return [item.to_dict() for item in mutants]


def build_mutation_assurance_record(
    *,
    concern: str,
    mutant_id: str,
    original_passed: bool,
    mutant_failed: bool,
    mutant_diff: str = "",
    equivalent_suspected: bool = False,
    evidence_refs: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    killed = bool(original_passed and mutant_failed and not equivalent_suspected)
    if equivalent_suspected:
        status = "EQUIVALENT_SUSPECTED"
    elif killed:
        status = "KILLED"
    elif original_passed and not mutant_failed:
        status = "SURVIVED_BLIND_SPOT"
    else:
        status = "INVALID_ORIGINAL_FAILURE"
    return {
        "schema_version": "nexus_mutation_assurance.v1",
        "concern": str(concern),
        "mutant_id": str(mutant_id),
        "mutant_diff": str(mutant_diff),
        "original_passed": bool(original_passed),
        "mutant_failed": bool(mutant_failed),
        "equivalent_suspected": bool(equivalent_suspected),
        "killed": killed,
        "assurance_status": status,
        "evidence_refs": [str(item) for item in evidence_refs if str(item).strip()],
    }


def evaluate_mutation_assurance(records: Any, *, required: bool = False) -> dict[str, Any]:
    rows = [row for row in (records or []) if isinstance(row, dict)]
    killed = [row for row in rows if bool(row.get("killed"))]
    survived = [
        row for row in rows if str(row.get("assurance_status") or "") == "SURVIVED_BLIND_SPOT"
    ]
    equivalent = [row for row in rows if bool(row.get("equivalent_suspected"))]
    failures: list[str] = []
    if required and not rows:
        failures.append("mutation_assurance_missing")
    if required and rows and not killed:
        failures.append("no_mutant_killed")
    if survived:
        failures.append("survived_mutants_present")
    status = "PASS" if not failures else "FAIL"
    return {
        "schema_version": "nexus_mutation_assurance_gate.v1",
        "required": bool(required),
        "status": status,
        "passed": status == "PASS",
        "row_count": len(rows),
        "killed_count": len(killed),
        "survived_count": len(survived),
        "equivalent_suspected_count": len(equivalent),
        "failures": failures,
        "survived_mutant_ids": [str(row.get("mutant_id") or "") for row in survived],
        "killed_mutant_ids": [str(row.get("mutant_id") or "") for row in killed],
    }


def mutation_assurance_required(
    *, risk_score: int = 0, public_claim: bool = False, high_risk: bool = False
) -> bool:
    return bool(public_claim and (high_risk or int(risk_score or 0) >= 70))


def evaluate_issue16_mutation_assurance(
    *, risk_inputs: Any = None, records: Any = None
) -> dict[str, Any]:
    """Evaluate the bounded, risk-triggered mutation challenge for Issue #16."""
    normalized_inputs, risk_triggered, risk_inputs_invalid = _normalize_issue16_risk_inputs(
        risk_inputs
    )
    rows, collection_failures = _bounded_mapping_records(records)
    submitted_targeted_records = [
        row
        for row in rows
        if row.get("mutant_id") == _ISSUE16_TARGET.mutant_id
        or row.get("concern") == _ISSUE16_TARGET.concern
    ]
    record_failures = {
        failure
        for row in submitted_targeted_records
        if (failure := _issue16_target_record_failure(row)) is not None
    }
    canonical_identity_count = sum(
        row.get("mutant_id") == _ISSUE16_TARGET.mutant_id
        and row.get("concern") == _ISSUE16_TARGET.concern
        for row in submitted_targeted_records
    )
    duplicate_target_present = canonical_identity_count > 1
    targeted_records = sorted(
        [row for row in submitted_targeted_records if _issue16_target_record_failure(row) is None],
        key=_canonical_record_sort_key,
    )
    if duplicate_target_present:
        targeted_records = []

    required = bool(
        risk_triggered
        or risk_inputs_invalid
        or collection_failures
        or record_failures
        or duplicate_target_present
    )
    target_ids = [_ISSUE16_TARGET.mutant_id] if required else []

    if not required:
        return {
            "schema_version": "nexus_issue16_mutation_assurance.v1",
            "risk_inputs": normalized_inputs,
            "decision": "NOT_REQUIRED",
            "reason": "low_risk_internal_change",
            "targeted_mutant_ids": [],
            "targeted_records": [],
            "required": False,
            "status": "NOT_REQUIRED",
            "passed": False,
            "row_count": 0,
            "killed_count": 0,
            "survived_count": 0,
            "equivalent_suspected_count": 0,
            "failures": [],
        }

    gate = evaluate_mutation_assurance(targeted_records, required=True)
    failures = [*gate["failures"], *collection_failures]
    if risk_inputs_invalid:
        failures.append("risk_inputs_invalid")
    failures.extend(record_failures)
    if duplicate_target_present:
        failures.append("duplicate_target_identity")
    return {
        "schema_version": "nexus_issue16_mutation_assurance.v1",
        "risk_inputs": normalized_inputs,
        "decision": "REQUIRED",
        "reason": (
            "invalid_risk_inputs"
            if risk_inputs_invalid
            else "invalid_mutation_records"
            if collection_failures or record_failures or duplicate_target_present
            else "public_claim_or_high_risk"
        ),
        "targeted_mutant_ids": target_ids,
        "targeted_records": targeted_records,
        "required": True,
        **{
            key: gate[key]
            for key in (
                "row_count",
                "killed_count",
                "survived_count",
                "equivalent_suspected_count",
            )
        },
        "status": "FAIL" if failures else "PASS",
        "passed": not failures,
        "failures": sorted(set(failures)),
    }


def build_shadow_mutation_report(records: Any, *, concern: str = "") -> dict[str, Any]:
    """Report mutation blind spots without changing runtime release decisions."""
    rows = [row for row in (records or []) if isinstance(row, dict)]
    if concern:
        rows = [row for row in rows if str(row.get("concern") or "") == str(concern)]
    gate = evaluate_mutation_assurance(rows, required=False)
    blindspots = [
        {
            "mutant_id": str(row.get("mutant_id") or ""),
            "concern": str(row.get("concern") or ""),
            "expected_detector": str(row.get("expected_detector") or ""),
        }
        for row in rows
        if str(row.get("assurance_status") or "") == "SURVIVED_BLIND_SPOT"
    ]
    return {
        "schema_version": "nexus_shadow_mutation_report.v1",
        "mode": "shadow_only_no_release_block",
        "concern": str(concern or ""),
        "row_count": len(rows),
        "killed_count": gate["killed_count"],
        "survived_count": gate["survived_count"],
        "logic_blindspot_candidates": blindspots,
        "release_blocked": False,
        "recommended_action": "promote_targeted_tests" if blindspots else "keep_monitoring",
    }
