"""Evidence-only final reduction for bounded verified-repair claims.

This module consumes receipts and already-produced gate results.  It never
executes a verifier, applies a patch, or changes routing/claim authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

VERIFIED_REPAIR_SCHEMA = "nexus.local_heal.verified_repair.v1"
CALIBRATION_SCHEMA = "nexus.local_heal.verified_repair_calibration.v1"
FINAL_STATES = ("VERIFIED_REPAIR", "PARTIALLY_VERIFIED")
KNOWN_WRONG_CASES = (
    "no_op",
    "compile_only_wrong",
    "overfit",
    "boundary_wrong",
    "regression_inducing",
)

_CALIBRATION_CASES = (
    ("correct", True),
    ("no_op", False),
    ("compile_only_wrong", False),
    ("overfit", False),
    ("boundary_wrong", False),
    ("regression_inducing", False),
)
CALIBRATION_MANIFEST: dict[str, Any] = {
    "schema": CALIBRATION_SCHEMA,
    "version": 1,
    "cases": [{"case": name, "expected_accept": expected} for name, expected in _CALIBRATION_CASES],
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


CALIBRATION_MANIFEST_HASH = hashlib.sha256(_canonical_json(CALIBRATION_MANIFEST)).hexdigest()


def _bool(data: Mapping[str, Any], *names: str) -> bool:
    return any(data.get(name) is True for name in names)


def _text(data: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = data.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _refs(data: Mapping[str, Any]) -> tuple[tuple[str, ...], list[str]]:
    raw = data.get("upstream_receipt_refs", data.get("evidence_refs", ()))
    if not isinstance(raw, (list, tuple)):
        return (), ["upstream_receipt_refs_invalid_type"]

    refs: list[str] = []
    reasons: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            reasons.append("upstream_receipt_ref_invalid")
            continue
        refs.append(value.strip())
    if len(refs) != len(set(refs)):
        reasons.append("upstream_receipt_refs_duplicate")
    return tuple(refs), reasons


def _case_reasons(case: str, data: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    patch_applied = _bool(data, "patch_applied", "candidate_patch_applied")
    compile_passed = _bool(data, "compile_passed", "compile_only_passed")
    hidden_passed = _bool(data, "hidden_verifier_passed", "verifier_passed")
    regression_passed = _bool(data, "regression_passed", "affected_suite_passed")
    behavioral_passed = _bool(data, "behavioral_verifier_passed", "semantic_verifier_passed")
    mutation_passed = _bool(data, "mutation_assurance_passed")
    if case == "correct":
        if not patch_applied:
            reasons.append("patch_not_applied")
        if not compile_passed:
            reasons.append("compile_evidence_missing")
        if not hidden_passed:
            reasons.append("hidden_verifier_not_passed")
        if not behavioral_passed:
            reasons.append("behavioral_verifier_not_passed")
        if not regression_passed:
            reasons.append("regression_not_passed")
        if not mutation_passed:
            reasons.append("mutation_assurance_not_passed")
        if not _text(data, "patch_sha", "candidate_patch_sha"):
            reasons.append("patch_evidence_missing")
        if not _text(data, "base_sha") or not _text(data, "candidate_sha"):
            reasons.append("base_candidate_binding_missing")
        elif _text(data, "base_sha") == _text(data, "candidate_sha"):
            reasons.append("base_candidate_binding_invalid")
    elif case == "no_op":
        if patch_applied or _text(data, "patch_sha", "candidate_patch_sha"):
            reasons.append("no_op_case_claimed_patch")
        reasons.append("no_op_rejected")
    elif case == "compile_only_wrong":
        reasons.append("compile_only_rejected")
    elif case == "overfit":
        if regression_passed:
            reasons.append("overfit_regression_claimed_pass")
        reasons.append("overfit_rejected")
    elif case == "boundary_wrong":
        if _bool(data, "boundary_checks_passed"):
            reasons.append("boundary_case_claimed_pass")
        reasons.append("boundary_wrong_rejected")
    elif case == "regression_inducing":
        if regression_passed:
            reasons.append("regression_case_claimed_pass")
        reasons.append("regression_inducing_rejected")
    else:
        reasons.append("calibration_case_unknown")
    return reasons


def reduce_verified_repair(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Reduce existing evidence to a bounded, non-public repair outcome.

    Missing or malformed evidence is rejected.  This function intentionally
    does not invoke subprocesses, import a verifier, or infer success from a
    human-readable report.
    """
    data = dict(evidence) if isinstance(evidence, Mapping) else {}
    case = _text(data, "calibration_case", "case")
    refs, ref_reasons = _refs(data)
    reasons = [*_case_reasons(case, data), *ref_reasons]
    if not refs:
        reasons.append("upstream_receipt_refs_missing")
    if data.get("public_claim_allowed") is True:
        reasons.append("public_claim_allowed_tamper")
    if _text(data, "calibration_manifest_hash") not in ("", CALIBRATION_MANIFEST_HASH):
        reasons.append("calibration_manifest_hash_mismatch")
    accepted = not reasons
    return {
        "schema": VERIFIED_REPAIR_SCHEMA,
        "calibration_manifest_hash": CALIBRATION_MANIFEST_HASH,
        "calibration_case": case,
        "status": "VERIFIED_REPAIR" if accepted else "PARTIALLY_VERIFIED",
        "accepted": accepted,
        "reasons": sorted(set(reasons)),
        "upstream_receipt_refs": list(refs),
        "public_claim_allowed": False,
    }


def run_fixed_calibration(
    cases: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Evaluate the fixed six-case calibration without executing anything."""
    supplied = cases if isinstance(cases, Mapping) else {}
    outcomes: list[dict[str, Any]] = []
    false_green_cases: list[str] = []
    for case, expected_accept in _CALIBRATION_CASES:
        evidence = (
            dict(supplied.get(case, {})) if isinstance(supplied.get(case, {}), Mapping) else {}
        )
        evidence["calibration_case"] = case
        outcome = reduce_verified_repair(evidence)
        actual_accept = bool(outcome["accepted"])
        if not expected_accept and actual_accept:
            false_green_cases.append(case)
        outcomes.append(
            {
                "case": case,
                "expected_accept": expected_accept,
                "accepted": actual_accept,
                "status": outcome["status"],
                "reasons": outcome["reasons"],
            }
        )
    wrong_count = len(KNOWN_WRONG_CASES)
    return {
        "schema": CALIBRATION_SCHEMA,
        "manifest_hash": CALIBRATION_MANIFEST_HASH,
        "outcomes": outcomes,
        "false_green_count": len(false_green_cases),
        "false_green_rate": len(false_green_cases) / wrong_count,
        "false_green_cases": false_green_cases,
        "known_wrong_count": wrong_count,
        "all_known_wrong_rejected": not false_green_cases,
        "correct_repair_accepted": outcomes[0]["accepted"],
        "public_claim_allowed": False,
    }


# Descriptive aliases keep the reducer usable by callers that name the stage
# rather than the evidence contract.
final_reducer = reduce_verified_repair
calibrate_verified_repair = run_fixed_calibration
