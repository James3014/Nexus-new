from __future__ import annotations

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
    survived = [row for row in rows if str(row.get("assurance_status") or "") == "SURVIVED_BLIND_SPOT"]
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


def mutation_assurance_required(*, risk_score: int = 0, public_claim: bool = False, high_risk: bool = False) -> bool:
    return bool(public_claim and (high_risk or int(risk_score or 0) >= 70))


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
