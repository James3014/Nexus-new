"""Deterministic, provider-neutral false-completion benchmark."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Callable, Mapping, cast

from product.adapters.changeset_certification_v2 import certify_changeset
from product.certification import CertificationDisposition, CertificationPolicy
from product.evidence import (
    AcceptanceContract,
    ChangeSet,
    EvidenceBundle,
    IntegrityStatus,
    Observation,
    ObservationStatus,
    VerificationPlan,
    _hash,
)
from product.kernel import CertificationInput, certify, validate_receipt
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.verification import reduce_verification

BENCHMARK_SCHEMA = "nexus.false_completion_benchmark.v1"
BENCHMARK_ID = "false-completion-fixed-local-v1"
CLAIM_CEILING = (
    "NO_MERGE_AUTHORIZATION",
    "NO_DEPLOYMENT_TRUTH",
    "NO_OUTCOME_TRUTH",
    "NO_PRODUCTION_READINESS",
    "NO_PUBLIC_PROTOCOL_STABILITY",
)
PUBLIC_CLAIM_GATE = "FAIL_CLOSED_EXPERIMENTAL"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class CaseOutcome:
    outcome_kind: str
    verification_status: str | None = None
    evidence_condition: str | None = None
    disposition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome_kind": self.outcome_kind,
            "verification_status": self.verification_status,
            "evidence_condition": self.evidence_condition,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class BenchmarkCaseResult:
    case_id: str
    expected: CaseOutcome
    actual: CaseOutcome
    detected: bool
    infra_invalid: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "expected": self.expected.to_dict(),
            "actual": self.actual.to_dict(),
            "detected": self.detected,
            "infra_invalid": self.infra_invalid,
            "error": self.error,
        }

    @property
    def canonical_hash(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class FalseCompletionReport:
    schema: str
    benchmark_id: str
    task_set_hash: str
    protocol_version: str
    implementation_schema: str
    case_ids: tuple[str, ...]
    eligible_count: int
    infra_invalid_count: int
    hostile_case_count: int
    detected_count: int
    false_completion_count: int
    false_completion_rate: float
    detection_rate: float
    trust_mismatch_count: int
    trust_mismatch_rate: float
    public_claim_gate: str
    claim_ceiling: tuple[str, ...]
    cases: tuple[BenchmarkCaseResult, ...]
    report_hash: str

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        result = {
            "schema": self.schema,
            "benchmark_id": self.benchmark_id,
            "task_set_hash": self.task_set_hash,
            "protocol_version": self.protocol_version,
            "implementation_schema": self.implementation_schema,
            "case_ids": list(self.case_ids),
            "eligible_count": self.eligible_count,
            "infra_invalid_count": self.infra_invalid_count,
            "hostile_case_count": self.hostile_case_count,
            "detected_count": self.detected_count,
            "false_completion_count": self.false_completion_count,
            "false_completion_rate": self.false_completion_rate,
            "detection_rate": self.detection_rate,
            "trust_mismatch_count": self.trust_mismatch_count,
            "trust_mismatch_rate": self.trust_mismatch_rate,
            "public_claim_gate": self.public_claim_gate,
            "claim_ceiling": list(self.claim_ceiling),
            "cases": [case.to_dict() for case in self.cases],
        }
        if include_hash:
            result["report_hash"] = self.report_hash
        return result

    def canonical_json(self) -> str:
        return _canonical(self.payload())


@dataclass(frozen=True)
class _Case:
    case_id: str
    expected: Any
    hostile: bool
    run: Callable[[], CaseOutcome]

    def __post_init__(self) -> None:
        if isinstance(self.expected, str):
            object.__setattr__(self, "expected", _expected(self.expected))


def _input(
    *, observations=None, change_paths=("src/a.py",), **flags: bool | None
) -> CertificationInput:
    contract = AcceptanceContract(
        "bench-contract", _hash("requirements"), ("unit", "lint"), ("src/a.py",), "FORBID"
    )
    change = ChangeSet("bench-change", "source", "target", _hash("diff"), tuple(change_paths))
    plan = VerificationPlan("bench-plan", contract.hash, change.hash, ("unit", "lint"))
    observations = observations or (
        Observation("unit", "artifact-unit", _hash("unit"), ObservationStatus.PASS),
        Observation("lint", "artifact-lint", _hash("lint"), ObservationStatus.PASS),
    )
    evidence = EvidenceBundle(
        "bench-evidence", contract.hash, change.hash, plan.hash, tuple(observations)
    )
    return CertificationInput(contract, change, plan, evidence, **flags)


def _direct(*_ignored: Any, **kwargs: Any) -> CaseOutcome:
    result = certify(_input(**kwargs))
    return CaseOutcome(
        "CERTIFICATION",
        result.verification.status.value,
        result.verification.integrity.value,
        result.disposition.value,
    )


def _legacy(status: str, **extra: Any) -> CaseOutcome:
    payload = {
        "schema": "nexus.changeset_certification.v1",
        "version": 1,
        "status": status,
        **extra,
    }
    result = certify_changeset(payload)
    return CaseOutcome(
        "CERTIFICATION",
        result.verification_result.status.value,
        result.verification_result.integrity.value,
        result.status.value,
    )


def _rejected(call: Callable[[], Any]) -> CaseOutcome:
    try:
        call()
    except (TypeError, ValueError):
        return CaseOutcome("INPUT_REJECTED")
    return CaseOutcome("CERTIFICATION", disposition="INPUT_ACCEPTED")


def _expected(value: str) -> CaseOutcome:
    if value == "INPUT_REJECTED":
        return CaseOutcome("INPUT_REJECTED")
    if value == "RECEIPT_INVALID":
        return CaseOutcome("RECEIPT_INVALID")
    status_and_condition, disposition = value.split(":")
    parts = status_and_condition.split("|")
    status = parts[0]
    condition = parts[1] if len(parts) > 1 else ("VALID" if status != "UNVERIFIABLE" else "MISSING")
    return CaseOutcome("CERTIFICATION", status, condition, disposition)


def _cases() -> tuple[_Case, ...]:
    fail = (
        Observation("unit", "artifact-unit", _hash("unit"), ObservationStatus.FAIL),
        Observation("lint", "artifact-lint", _hash("lint"), ObservationStatus.PASS),
    )
    duplicate_verifier = (
        Observation("unit", "u", _hash("u"), ObservationStatus.PASS),
        Observation("unit", "l", _hash("l"), ObservationStatus.PASS),
    )
    duplicate_artifact = (
        Observation("unit", "same", _hash("u"), ObservationStatus.PASS),
        Observation("lint", "same", _hash("l"), ObservationStatus.PASS),
    )
    cases: list[_Case] = [
        _Case(
            "direct_happy_certified",
            "VERIFIED:CERTIFIED",
            False,
            lambda: _direct(
                "",
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_verifier_fail",
            "FAILED_VERIFICATION:REJECTED",
            True,
            lambda: _direct(
                "",
                observations=fail,
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_missing_required_verifier",
            "UNVERIFIABLE:BLOCKED",
            True,
            lambda: _direct(
                "",
                observations=(Observation("unit", "u", _hash("u"), ObservationStatus.PASS),),
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_scope_escape",
            "FAILED_VERIFICATION:REJECTED",
            True,
            lambda: _direct(
                "",
                change_paths=("src/secret.py",),
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_duplicate_verifier",
            "UNVERIFIABLE|DUPLICATE:REJECTED",
            True,
            lambda: _direct(
                "",
                observations=duplicate_verifier,
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_duplicate_artifact",
            "UNVERIFIABLE|DUPLICATE:REJECTED",
            True,
            lambda: _direct(
                "",
                observations=duplicate_artifact,
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_policy_false",
            "VERIFIED:REJECTED",
            True,
            lambda: _direct(
                "",
                policy_accepted=False,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "direct_policy_missing",
            "VERIFIED:BLOCKED",
            True,
            lambda: _direct(
                "",
                policy_accepted=None,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
    ]
    for flag in ("authority_present", "approval_present", "signing_present"):
        flags: dict[str, bool | None] = {
            "policy_accepted": True,
            "authority_present": True,
            "approval_present": True,
            "signing_present": True,
        }
        flags[flag] = None
        cases.append(
            _Case(
                f"direct_missing_{flag}",
                "VERIFIED:BLOCKED",
                True,
                lambda flags=flags: _direct("", **flags),
            )
        )
    cases += [
        _Case(
            "legacy_v1_raw_pass",
            "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
            True,
            lambda: _legacy("PASS"),
        ),
        _Case(
            "legacy_v1_raw_fail",
            "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
            True,
            lambda: _legacy("FAIL"),
        ),
        _Case(
            "legacy_caller_reason_cannot_override_fail",
            "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
            True,
            lambda: _legacy("FAIL", disposition="CERTIFIED", reasons=[]),
        ),
        _Case(
            "traversal_path_input_rejected",
            "INPUT_REJECTED",
            True,
            lambda: _rejected(
                lambda: AcceptanceContract("x", _hash("r"), ("unit",), ("../escape",), "FORBID")
            ),
        ),
        _Case(
            "malformed_status_input_rejected",
            "INPUT_REJECTED",
            True,
            lambda: _rejected(lambda: Observation("unit", "a", _hash("a"), cast(Any, "PASS"))),
        ),
        _Case(
            "caller_claimed_disposition_rejected",
            "INPUT_REJECTED",
            True,
            lambda: _rejected(
                lambda: CertificationInput(
                    **cast(Any, _input().__dict__ | {"disposition": "CERTIFIED"})
                )
            ),
        ),
        _Case("receipt_tamper_rejected", "RECEIPT_INVALID", True, lambda: _receipt_tamper()),
        _Case(
            "stale_exact_evidence",
            "UNVERIFIABLE:BLOCKED",
            True,
            lambda: _direct(
                "",
                observations=(
                    Observation("unit", "artifact-unit", _hash("unit"), ObservationStatus.PASS),
                ),
                policy_accepted=True,
                authority_present=True,
                approval_present=True,
                signing_present=True,
            ),
        ),
        _Case(
            "receipt_factual_tamper_rejected",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_tamper(factual=True),
        ),
        _Case(
            "stale_change_set_hash_mismatch",
            CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "STALE", "BLOCKED"),
            True,
            lambda: _stale_change_set(),
        ),
        _Case(
            "tampered_evidence_claimed_hash",
            CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "TAMPERED", "REJECTED"),
            True,
            lambda: _direct_with_evidence_claim("tampered-evidence"),
        ),
        _Case(
            "receipt_alternate_reducer_verification",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_variant("verification"),
        ),
        _Case(
            "receipt_disposition_tamper_rejected",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_variant("disposition"),
        ),
        _Case(
            "receipt_policy_tamper_rejected",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_variant("policy"),
        ),
        _Case(
            "receipt_prerequisite_tamper_rejected",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_variant("prerequisite"),
        ),
        _Case(
            "receipt_claimed_hash_tamper_rejected",
            "RECEIPT_INVALID",
            True,
            lambda: _receipt_variant("claimed_hash"),
        ),
    ]
    return tuple(cases)


def _receipt_tamper(*, factual: bool = False) -> CaseOutcome:
    source = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    result = certify(source)
    receipt = (
        replace(result.receipt, disposition=CertificationDisposition.REJECTED)
        if not factual
        else replace(result.receipt, policy=CertificationPolicy(False, True, True, True))
    )
    return CaseOutcome(
        "RECEIPT_INVALID" if not validate_receipt(receipt, source) else "CERTIFICATION"
    )


def _direct_with_evidence_claim(claim: str) -> CaseOutcome:
    source = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    tampered = replace(source.evidence, claimed_bundle_hash=_hash(claim))
    return _direct_input(replace(source, evidence=tampered))


def _stale_change_set() -> CaseOutcome:
    source = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    stale = replace(source.evidence, change_set_hash=_hash("different-change-set"))
    return _direct_input(replace(source, evidence=stale))


def _direct_input(source: CertificationInput) -> CaseOutcome:
    result = certify(source)
    return CaseOutcome(
        "CERTIFICATION",
        result.verification.status.value,
        result.verification.integrity.value,
        result.disposition.value,
    )


def _receipt_variant(kind: str) -> CaseOutcome:
    source = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    result = certify(source)
    receipt = result.receipt
    if kind == "verification":
        receipt = replace(
            receipt,
            verification=reduce_verification(
                IntegrityStatus.VALID, (ObservationStatus.FAIL,), ("VERIFIER_FAILED",)
            ),
        )
    elif kind == "disposition":
        receipt = replace(receipt, disposition=CertificationDisposition.REJECTED)
    elif kind == "policy":
        receipt = replace(receipt, policy=CertificationPolicy(False, True, True, True))
    elif kind == "prerequisite":
        receipt = replace(receipt, policy=CertificationPolicy(True, None, True, True))
    elif kind == "claimed_hash":
        receipt = replace(receipt, claimed_receipt_hash=_hash("tampered-receipt"))
    else:
        raise ValueError(kind)
    return CaseOutcome(
        "RECEIPT_INVALID" if not validate_receipt(receipt, source) else "CERTIFICATION"
    )


CASES = _cases()

EXPECTED_CASE_IDS = (
    "direct_happy_certified",
    "direct_verifier_fail",
    "direct_missing_required_verifier",
    "direct_scope_escape",
    "direct_duplicate_verifier",
    "direct_duplicate_artifact",
    "direct_policy_false",
    "direct_policy_missing",
    "direct_missing_authority_present",
    "direct_missing_approval_present",
    "direct_missing_signing_present",
    "legacy_v1_raw_pass",
    "legacy_v1_raw_fail",
    "legacy_caller_reason_cannot_override_fail",
    "traversal_path_input_rejected",
    "malformed_status_input_rejected",
    "caller_claimed_disposition_rejected",
    "receipt_tamper_rejected",
    "stale_exact_evidence",
    "receipt_factual_tamper_rejected",
    "stale_change_set_hash_mismatch",
    "tampered_evidence_claimed_hash",
    "receipt_alternate_reducer_verification",
    "receipt_disposition_tamper_rejected",
    "receipt_policy_tamper_rejected",
    "receipt_prerequisite_tamper_rejected",
    "receipt_claimed_hash_tamper_rejected",
)
CASE_SPEC = (
    (
        "direct_happy_certified",
        False,
        CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "CERTIFIED"),
    ),
    (
        "direct_verifier_fail",
        True,
        CaseOutcome("CERTIFICATION", "FAILED_VERIFICATION", "VALID", "REJECTED"),
    ),
    (
        "direct_missing_required_verifier",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "MISSING", "BLOCKED"),
    ),
    (
        "direct_scope_escape",
        True,
        CaseOutcome("CERTIFICATION", "FAILED_VERIFICATION", "VALID", "REJECTED"),
    ),
    (
        "direct_duplicate_verifier",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "DUPLICATE", "REJECTED"),
    ),
    (
        "direct_duplicate_artifact",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "DUPLICATE", "REJECTED"),
    ),
    ("direct_policy_false", True, CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "REJECTED")),
    ("direct_policy_missing", True, CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "BLOCKED")),
    (
        "direct_missing_authority_present",
        True,
        CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "BLOCKED"),
    ),
    (
        "direct_missing_approval_present",
        True,
        CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "BLOCKED"),
    ),
    (
        "direct_missing_signing_present",
        True,
        CaseOutcome("CERTIFICATION", "VERIFIED", "VALID", "BLOCKED"),
    ),
    (
        "legacy_v1_raw_pass",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "LEGACY_NON_CERTIFIABLE", "BLOCKED"),
    ),
    (
        "legacy_v1_raw_fail",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "LEGACY_NON_CERTIFIABLE", "BLOCKED"),
    ),
    (
        "legacy_caller_reason_cannot_override_fail",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "LEGACY_NON_CERTIFIABLE", "BLOCKED"),
    ),
    ("traversal_path_input_rejected", True, CaseOutcome("INPUT_REJECTED")),
    ("malformed_status_input_rejected", True, CaseOutcome("INPUT_REJECTED")),
    ("caller_claimed_disposition_rejected", True, CaseOutcome("INPUT_REJECTED")),
    ("receipt_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
    (
        "stale_exact_evidence",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "MISSING", "BLOCKED"),
    ),
    ("receipt_factual_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
    (
        "stale_change_set_hash_mismatch",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "STALE", "BLOCKED"),
    ),
    (
        "tampered_evidence_claimed_hash",
        True,
        CaseOutcome("CERTIFICATION", "UNVERIFIABLE", "TAMPERED", "REJECTED"),
    ),
    ("receipt_alternate_reducer_verification", True, CaseOutcome("RECEIPT_INVALID")),
    ("receipt_disposition_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
    ("receipt_policy_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
    ("receipt_prerequisite_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
    ("receipt_claimed_hash_tamper_rejected", True, CaseOutcome("RECEIPT_INVALID")),
)


def _spec_jsonable(value: Any) -> Any:
    if isinstance(value, CaseOutcome):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_spec_jsonable(item) for item in value]
    return value


TASK_SET_HASH = "sha256:b6b8081e3c597d1283f1425f94ab484e2e6432c742ea0a899ea23a862dd93d79"
if tuple((case.case_id, case.hostile, case.expected) for case in CASES) != CASE_SPEC:
    raise RuntimeError("CASE_SPEC does not match CASES")
if tuple(case.case_id for case in CASES) != EXPECTED_CASE_IDS:
    raise RuntimeError("EXPECTED_CASE_IDS does not match CASES")
if _digest(_spec_jsonable(CASE_SPEC)) != TASK_SET_HASH:
    raise RuntimeError("TASK_SET_HASH does not match CASE_SPEC")


def _rate(numerator: int, denominator: int) -> float:
    return round(float(Fraction(numerator, denominator)) if denominator else 0.0, 12)


def run_benchmark() -> FalseCompletionReport:
    results = []
    for case in CASES:
        try:
            actual = case.run()
            detected = (
                case.hostile and actual == case.expected and actual.disposition != "CERTIFIED"
            )
            results.append(
                BenchmarkCaseResult(
                    case.case_id, cast(CaseOutcome, case.expected), actual, detected
                )
            )
        except Exception as exc:  # bounded classification; exceptions never escape runner
            results.append(
                BenchmarkCaseResult(
                    case.case_id,
                    cast(CaseOutcome, case.expected),
                    CaseOutcome("INFRA_INVALID"),
                    False,
                    True,
                    type(exc).__name__,
                )
            )
    eligible = tuple(result for result in results if not result.infra_invalid)
    hostile = sum(
        case.hostile
        for case in CASES
        if not next(r for r in results if r.case_id == case.case_id).infra_invalid
    )
    detected = sum(result.detected for result in eligible)
    false_completion = sum(
        result.actual.outcome_kind == "CERTIFICATION" and result.actual.disposition == "CERTIFIED"
        for result in eligible
        if next(case for case in CASES if case.case_id == result.case_id).hostile
    )
    mismatches = sum(result.actual != result.expected for result in eligible)
    payload = {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "task_set_hash": TASK_SET_HASH,
        "protocol_version": PUBLIC_PROTOCOL_VERSION,
        "implementation_schema": IMPLEMENTATION_SCHEMA,
        "case_ids": [result.case_id for result in results],
        "eligible_count": len(eligible),
        "infra_invalid_count": len(results) - len(eligible),
        "hostile_case_count": hostile,
        "detected_count": detected,
        "false_completion_count": false_completion,
        "false_completion_rate": _rate(false_completion, len(eligible)),
        "detection_rate": _rate(detected, hostile),
        "trust_mismatch_count": mismatches,
        "trust_mismatch_rate": _rate(mismatches, len(eligible)),
        "public_claim_gate": PUBLIC_CLAIM_GATE,
        "claim_ceiling": list(CLAIM_CEILING),
        "cases": [result.to_dict() for result in results],
    }
    return FalseCompletionReport(
        **{
            key: value
            for key, value in payload.items()
            if key not in {"cases", "case_ids", "claim_ceiling"}
        },
        case_ids=tuple(result.case_id for result in results),
        claim_ceiling=CLAIM_CEILING,
        cases=tuple(results),
        report_hash=_digest(payload),
    )


def verify_report(report: FalseCompletionReport | Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        payload = report.payload() if isinstance(report, FalseCompletionReport) else dict(report)
        if payload.get("report_hash") != _digest(
            {k: v for k, v in payload.items() if k != "report_hash"}
        ):
            errors.append("report_hash")
        expected_ids = list(EXPECTED_CASE_IDS)
        if payload.get("task_set_hash") != TASK_SET_HASH:
            errors.append("task_set_hash")
        fixed = {
            "schema": BENCHMARK_SCHEMA,
            "benchmark_id": BENCHMARK_ID,
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "public_claim_gate": PUBLIC_CLAIM_GATE,
            "claim_ceiling": list(CLAIM_CEILING),
        }
        for key, value in fixed.items():
            if payload.get(key) != value:
                errors.append(key)
        if payload.get("case_ids") != expected_ids:
            errors.append("case_ids")

        # This is deliberately a separate execution path from run_benchmark.
        recomputed: list[BenchmarkCaseResult] = []
        for case in CASES:
            try:
                actual = case.run()
                detected = (
                    case.hostile and actual == case.expected and actual.disposition != "CERTIFIED"
                )
                recomputed.append(
                    BenchmarkCaseResult(case.case_id, case.expected, actual, detected)
                )
            except Exception as exc:
                recomputed.append(
                    BenchmarkCaseResult(
                        case.case_id,
                        case.expected,
                        CaseOutcome("INFRA_INVALID"),
                        False,
                        True,
                        type(exc).__name__,
                    )
                )
        expected_cases = [result.to_dict() for result in recomputed]
        actual_cases = payload.get("cases")
        if not isinstance(actual_cases, list) or len(actual_cases) != len(expected_cases):
            errors.append("cases")
        else:
            for index, (actual, expected) in enumerate(zip(actual_cases, expected_cases)):
                if not isinstance(actual, dict):
                    errors.append(f"cases[{index}]")
                    continue
                for field in ("case_id", "detected", "infra_invalid", "error"):
                    if actual.get(field) != expected[field]:
                        errors.append(f"cases[{index}].{field}")
                for outcome_name in ("expected", "actual"):
                    got, want = actual.get(outcome_name), expected[outcome_name]
                    if not isinstance(got, dict):
                        errors.append(f"cases[{index}].{outcome_name}")
                        continue
                    for field in (
                        "outcome_kind",
                        "verification_status",
                        "evidence_condition",
                        "disposition",
                    ):
                        if got.get(field) != want.get(field):
                            errors.append(f"cases[{index}].{outcome_name}.{field}")

        eligible = [r for r in recomputed if not r.infra_invalid]
        hostile = sum(
            case.hostile for case, result in zip(CASES, recomputed) if not result.infra_invalid
        )
        detected = sum(r.detected for r in eligible)
        false_completion = sum(
            case.hostile and r.actual.disposition == "CERTIFIED"
            for case, r in zip(CASES, recomputed)
            if not r.infra_invalid
        )
        mismatches = sum(r.actual != r.expected for r in eligible)
        counts = {
            "eligible_count": len(eligible),
            "infra_invalid_count": len(recomputed) - len(eligible),
            "hostile_case_count": hostile,
            "detected_count": detected,
            "false_completion_count": false_completion,
            "false_completion_rate": _rate(false_completion, len(eligible)),
            "detection_rate": _rate(detected, hostile),
            "trust_mismatch_count": mismatches,
            "trust_mismatch_rate": _rate(mismatches, len(eligible)),
        }
        for key, value in counts.items():
            if payload.get(key) != value:
                errors.append(key)
    except (TypeError, ValueError, AttributeError, KeyError):
        return ("malformed_report",)
    return tuple(dict.fromkeys(errors))


__all__ = [
    "BENCHMARK_SCHEMA",
    "BENCHMARK_ID",
    "TASK_SET_HASH",
    "EXPECTED_CASE_IDS",
    "CASE_SPEC",
    "CASES",
    "BenchmarkCaseResult",
    "FalseCompletionReport",
    "run_benchmark",
    "verify_report",
]
