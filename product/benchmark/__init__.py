"""Deterministic false-completion benchmark with immutable execution specs."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from fractions import Fraction
from types import MappingProxyType
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
    active: set[int] = set()

    def enc(v: Any) -> Any:
        if v is None or type(v) in (bool, int, str):
            return v
        if type(v) is float:
            if not math.isfinite(v):
                raise ValueError("non-finite")
            return v
        if isinstance(v, Mapping):
            if any(type(k) is not str for k in v):
                raise TypeError("mapping key")
            if id(v) in active:
                raise ValueError("cycle")
            active.add(id(v))
            try:
                return {k: enc(v[k]) for k in sorted(v)}
            finally:
                active.remove(id(v))
        if isinstance(v, (list, tuple)):
            if id(v) in active:
                raise ValueError("cycle")
            active.add(id(v))
            try:
                return [enc(x) for x in v]
            finally:
                active.remove(id(v))
        raise TypeError(type(v).__name__)

    return json.dumps(
        enc(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


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
class CaseDefinition:
    case_id: str
    hostile: bool
    expected: CaseOutcome
    operation: str
    params: Mapping[str, Any]


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
    false_completion_rate: float | None
    detection_rate: float | None
    trust_mismatch_count: int
    trust_mismatch_rate: float | None
    public_claim_gate: str
    claim_ceiling: tuple[str, ...]
    cases: tuple[BenchmarkCaseResult, ...]
    report_hash: str

    def payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        p = {
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
            "cases": [x.to_dict() for x in self.cases],
        }
        if include_hash:
            p["report_hash"] = self.report_hash
        return p

    def canonical_json(self) -> str:
        return _canonical(self.payload())


def _input(
    *, observations=None, change_paths=("src/a.py",), **flags: bool | None
) -> CertificationInput:
    c = AcceptanceContract(
        "bench-contract", _hash("requirements"), ("unit", "lint"), ("src/a.py",), "FORBID"
    )
    ch = ChangeSet("bench-change", "source", "target", _hash("diff"), tuple(change_paths))
    plan = VerificationPlan("bench-plan", c.hash, ch.hash, ("unit", "lint"))
    observations = observations or (
        Observation("unit", "artifact-unit", _hash("unit"), ObservationStatus.PASS),
        Observation("lint", "artifact-lint", _hash("lint"), ObservationStatus.PASS),
    )
    return CertificationInput(
        c,
        ch,
        plan,
        EvidenceBundle("bench-evidence", c.hash, ch.hash, plan.hash, tuple(observations)),
        **flags,
    )


def _direct(**kw: Any) -> CaseOutcome:
    r = certify(_input(**kw))
    return CaseOutcome(
        "CERTIFICATION",
        r.verification.status.value,
        r.verification.integrity.value,
        r.disposition.value,
    )


def _legacy(status: str, **extra: Any) -> CaseOutcome:
    r = certify_changeset(
        {"schema": "nexus.changeset_certification.v1", "version": 1, "status": status, **extra}
    )
    return CaseOutcome(
        "CERTIFICATION",
        r.verification_result.status.value,
        r.verification_result.integrity.value,
        r.status.value,
    )


def _reject(kind: str) -> CaseOutcome:
    try:
        if kind == "traversal":
            AcceptanceContract("x", _hash("r"), ("unit",), ("../escape",), "FORBID")
        elif kind == "status":
            Observation("unit", "a", _hash("a"), cast(Any, "PASS"))
        else:
            CertificationInput(**cast(Any, _input().__dict__ | {"disposition": "CERTIFIED"}))
    except (TypeError, ValueError):
        return CaseOutcome("INPUT_REJECTED")
    return CaseOutcome("CERTIFICATION", disposition="INPUT_ACCEPTED")


def _receipt(kind: str) -> CaseOutcome:
    s = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    r = certify(s)
    q = r.receipt
    if kind in ("tamper", "disposition"):
        q = replace(q, disposition=CertificationDisposition.REJECTED)
    elif kind == "verification":
        q = replace(
            q,
            verification=reduce_verification(
                IntegrityStatus.VALID, (ObservationStatus.FAIL,), ("VERIFIER_FAILED",)
            ),
        )
    elif kind == "policy":
        q = replace(q, policy=CertificationPolicy(False, True, True, True))
    elif kind == "prerequisite":
        q = replace(q, policy=CertificationPolicy(True, None, True, True))
    elif kind == "claimed_hash":
        q = replace(q, claimed_receipt_hash=_hash("tampered-receipt"))
    return CaseOutcome("RECEIPT_INVALID" if not validate_receipt(q, s) else "CERTIFICATION")


def _special(kind: str) -> CaseOutcome:
    s = _input(
        policy_accepted=True, authority_present=True, approval_present=True, signing_present=True
    )
    s = replace(
        s,
        evidence=replace(
            s.evidence,
            **(
                {"change_set_hash": _hash("different-change-set")}
                if kind == "stale"
                else {"claimed_bundle_hash": _hash("tampered-evidence")}
            ),
        ),
    )
    r = certify(s)
    return CaseOutcome(
        "CERTIFICATION",
        r.verification.status.value,
        r.verification.integrity.value,
        r.disposition.value,
    )


def _expected(v: str) -> CaseOutcome:
    if v in ("INPUT_REJECTED", "RECEIPT_INVALID"):
        return CaseOutcome(v)
    sc, d = v.split(":")
    a = sc.split("|")
    return CaseOutcome(
        "CERTIFICATION",
        a[0],
        a[1] if len(a) > 1 else ("VALID" if a[0] != "UNVERIFIABLE" else "MISSING"),
        d,
    )


def _p(**x: Any) -> tuple[tuple[str, Any], ...]:
    return tuple(x.items())


_CASE_SPEC_LITERAL = (
    (
        "direct_happy_certified",
        False,
        "VERIFIED:CERTIFIED",
        "direct",
        _p(
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_verifier_fail",
        True,
        "FAILED_VERIFICATION:REJECTED",
        "direct",
        _p(
            observations="fail",
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_missing_required_verifier",
        True,
        "UNVERIFIABLE:BLOCKED",
        "direct",
        _p(
            observations="missing",
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_scope_escape",
        True,
        "FAILED_VERIFICATION:REJECTED",
        "direct",
        _p(
            change_paths=("src/secret.py",),
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_duplicate_verifier",
        True,
        "UNVERIFIABLE|DUPLICATE:REJECTED",
        "direct",
        _p(
            observations="duplicate_verifier",
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_duplicate_artifact",
        True,
        "UNVERIFIABLE|DUPLICATE:REJECTED",
        "direct",
        _p(
            observations="duplicate_artifact",
            policy_accepted=True,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_policy_false",
        True,
        "VERIFIED:REJECTED",
        "direct",
        _p(
            policy_accepted=False,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
    (
        "direct_policy_missing",
        True,
        "VERIFIED:BLOCKED",
        "direct",
        _p(
            policy_accepted=None,
            authority_present=True,
            approval_present=True,
            signing_present=True,
        ),
    ),
)
for f in ("authority_present", "approval_present", "signing_present"):
    _CASE_SPEC_LITERAL += (
        (
            f"direct_missing_{f}",
            True,
            "VERIFIED:BLOCKED",
            "direct",
            _p(
                policy_accepted=True,
                authority_present=None if f == "authority_present" else True,
                approval_present=None if f == "approval_present" else True,
                signing_present=None if f == "signing_present" else True,
            ),
        ),
    )
_CASE_SPEC_LITERAL += (
    (
        "legacy_v1_raw_pass",
        True,
        "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
        "legacy",
        _p(status="PASS"),
    ),
    (
        "legacy_v1_raw_fail",
        True,
        "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
        "legacy",
        _p(status="FAIL"),
    ),
    (
        "legacy_caller_reason_cannot_override_fail",
        True,
        "UNVERIFIABLE|LEGACY_NON_CERTIFIABLE:BLOCKED",
        "legacy",
        _p(status="FAIL", disposition="CERTIFIED", reasons=[]),
    ),
    ("traversal_path_input_rejected", True, "INPUT_REJECTED", "reject", _p(kind="traversal")),
    ("malformed_status_input_rejected", True, "INPUT_REJECTED", "reject", _p(kind="status")),
    (
        "caller_claimed_disposition_rejected",
        True,
        "INPUT_REJECTED",
        "reject",
        _p(kind="disposition"),
    ),
    ("receipt_tamper_rejected", True, "RECEIPT_INVALID", "receipt", _p(kind="tamper")),
    (
        "stale_change_set_hash_mismatch",
        True,
        "UNVERIFIABLE|STALE:BLOCKED",
        "special",
        _p(kind="stale"),
    ),
    (
        "tampered_evidence_claimed_hash",
        True,
        "UNVERIFIABLE|TAMPERED:REJECTED",
        "special",
        _p(kind="tampered"),
    ),
)
for k in ("verification", "disposition", "policy", "prerequisite", "claimed_hash"):
    _CASE_SPEC_LITERAL += (
        (f"receipt_{k}_tamper_rejected", True, "RECEIPT_INVALID", "receipt", _p(kind=k)),
    )


def _spec_jsonable(v: Any) -> Any:
    if isinstance(v, CaseOutcome):
        return v.to_dict()
    if isinstance(v, Mapping):
        return {k: _spec_jsonable(x) for k, x in v.items()}
    if isinstance(v, (tuple, list)):
        return [_spec_jsonable(x) for x in v]
    return v


def _freeze(v: Any) -> Any:
    if isinstance(v, Mapping):
        return MappingProxyType({k: _freeze(x) for k, x in v.items()})
    if isinstance(v, tuple):
        return tuple(_freeze(x) for x in v)
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def _make_specs() -> tuple[CaseDefinition, ...]:
    return tuple(
        CaseDefinition(i, h, _expected(e), op, MappingProxyType(dict(_freeze(p))))
        for i, h, e, op, p in _CASE_SPEC_LITERAL
    )


_AUTHORITATIVE_SPEC = _make_specs()
EXPECTED_CASE_IDS = tuple(x.case_id for x in _AUTHORITATIVE_SPEC)
CASE_SPEC = tuple(
    (x.case_id, x.hostile, x.expected, x.operation, x.params) for x in _AUTHORITATIVE_SPEC
)
CASES = _AUTHORITATIVE_SPEC
TASK_SET_HASH = "sha256:afa32ac1ed78076e9d00c16b707a94ba025bc64cae7f028a06cba7cfcd08703b"


def _make_dispatch() -> Callable[[str, Mapping[str, Any]], CaseOutcome]:
    def dispatch(op: str, p: Mapping[str, Any]) -> CaseOutcome:
        q = dict(p)
        if op == "direct":
            o = q.get("observations")
            if o == "fail":
                q["observations"] = (
                    Observation("unit", "artifact-unit", _hash("unit"), ObservationStatus.FAIL),
                    Observation("lint", "artifact-lint", _hash("lint"), ObservationStatus.PASS),
                )
            elif o == "missing":
                q["observations"] = (Observation("unit", "u", _hash("u"), ObservationStatus.PASS),)
            elif o == "duplicate_verifier":
                q["observations"] = (
                    Observation("unit", "u", _hash("u"), ObservationStatus.PASS),
                    Observation("unit", "l", _hash("l"), ObservationStatus.PASS),
                )
            elif o == "duplicate_artifact":
                q["observations"] = (
                    Observation("unit", "same", _hash("u"), ObservationStatus.PASS),
                    Observation("lint", "same", _hash("l"), ObservationStatus.PASS),
                )
            return _direct(**q)
        if op == "legacy":
            return _legacy(**q)
        if op == "reject":
            return _reject(**q)
        if op == "receipt":
            return _receipt(**q)
        return _special(q["kind"])

    return dispatch


def _false(c: CaseDefinition, a: CaseOutcome) -> bool:
    return c.hostile and a.outcome_kind == "CERTIFICATION" and a.disposition == "CERTIFIED"


def _run(
    spec: tuple[CaseDefinition, ...], dispatch: Callable[[str, Mapping[str, Any]], CaseOutcome]
) -> tuple[BenchmarkCaseResult, ...]:
    out = []
    for c in spec:
        try:
            a = dispatch(c.operation, c.params)
            out.append(
                BenchmarkCaseResult(
                    c.case_id, c.expected, a, c.hostile and a == c.expected and not _false(c, a)
                )
            )
        except Exception as e:
            out.append(
                BenchmarkCaseResult(
                    c.case_id,
                    c.expected,
                    CaseOutcome("INFRA_INVALID"),
                    False,
                    True,
                    type(e).__name__,
                )
            )
    return tuple(out)


def _rate(n: int, d: int) -> float | None:
    return round(float(Fraction(n, d)), 12) if d else None


def _shape(p: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    def exact(path: str, value: Any, typ: type, nullable: bool = False) -> None:
        if nullable and value is None:
            return
        if type(value) is not typ:
            errors.append(path)

    for k in (
        "schema",
        "benchmark_id",
        "task_set_hash",
        "protocol_version",
        "implementation_schema",
        "public_claim_gate",
    ):
        exact(k, p[k], str)
    exact("case_ids", p["case_ids"], list)
    exact("claim_ceiling", p["claim_ceiling"], list)
    for k in (
        "eligible_count",
        "infra_invalid_count",
        "hostile_case_count",
        "detected_count",
        "false_completion_count",
        "trust_mismatch_count",
    ):
        if type(p[k]) is not int or p[k] < 0:
            errors.append(k)
    for k in ("false_completion_rate", "detection_rate", "trust_mismatch_rate"):
        if p[k] is not None and (type(p[k]) is not float or not math.isfinite(p[k])):
            errors.append(k)
    exact("cases", p["cases"], list)
    if type(p["cases"]) is list:
        ck = {"case_id", "expected", "actual", "detected", "infra_invalid", "error"}
        ok = {"outcome_kind", "verification_status", "evidence_condition", "disposition"}
        for i, c in enumerate(p["cases"]):
            path = f"cases[{i}]"
            if type(c) is not dict:
                errors.append(path)
                continue
            for k in c:
                if k not in ck:
                    errors.append(f"{path}.{k}")
            for k in ck:
                if k not in c:
                    errors.append(f"{path}.{k}")
            if "case_id" in c:
                exact(f"{path}.case_id", c["case_id"], str)
            if "detected" in c:
                exact(f"{path}.detected", c["detected"], bool)
            if "infra_invalid" in c:
                exact(f"{path}.infra_invalid", c["infra_invalid"], bool)
            if "error" in c:
                exact(f"{path}.error", c["error"], str, True)
            for name in ("expected", "actual"):
                q = c.get(name)
                qp = f"{path}.{name}"
                if type(q) is not dict:
                    errors.append(qp)
                    continue
                for k in q:
                    if k not in ok:
                        errors.append(f"{qp}.{k}")
                for k in ok:
                    if k not in q:
                        errors.append(f"{qp}.{k}")
                if "outcome_kind" in q:
                    exact(f"{qp}.outcome_kind", q["outcome_kind"], str)
                for k in ("verification_status", "evidence_condition", "disposition"):
                    if k in q:
                        exact(f"{qp}.{k}", q[k], str, True)
    return errors


def _build(
    spec: tuple[CaseDefinition, ...], res: tuple[BenchmarkCaseResult, ...]
) -> FalseCompletionReport:
    good = tuple(r for r in res if not r.infra_invalid)
    hostile = sum(c.hostile for c, r in zip(spec, res) if not r.infra_invalid)
    false = sum(_false(c, r.actual) for c, r in zip(spec, res) if not r.infra_invalid)
    detected = sum(r.detected for r in good)
    mismatch = sum(r.actual != r.expected for r in good)
    p = {
        "schema": BENCHMARK_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "task_set_hash": TASK_SET_HASH,
        "protocol_version": PUBLIC_PROTOCOL_VERSION,
        "implementation_schema": IMPLEMENTATION_SCHEMA,
        "case_ids": [r.case_id for r in res],
        "eligible_count": len(good),
        "infra_invalid_count": len(res) - len(good),
        "hostile_case_count": hostile,
        "detected_count": detected,
        "false_completion_count": false,
        "false_completion_rate": _rate(false, hostile),
        "detection_rate": _rate(detected, hostile),
        "trust_mismatch_count": mismatch,
        "trust_mismatch_rate": _rate(mismatch, len(good)),
        "public_claim_gate": PUBLIC_CLAIM_GATE,
        "claim_ceiling": list(CLAIM_CEILING),
        "cases": [r.to_dict() for r in res],
    }
    return FalseCompletionReport(
        **{k: v for k, v in p.items() if k not in ("case_ids", "claim_ceiling", "cases")},
        case_ids=tuple(p["case_ids"]),
        claim_ceiling=CLAIM_CEILING,
        cases=res,
        report_hash=_digest(p),
    )


def _make_public_api() -> tuple[
    Callable[[], FalseCompletionReport],
    Callable[[FalseCompletionReport | Mapping[str, Any]], tuple[str, ...]],
]:
    run_spec, verify_spec = _make_specs(), _make_specs()
    run_dispatch, verify_dispatch = _make_dispatch(), _make_dispatch()
    task_hash = TASK_SET_HASH
    false_predicate, rate, digest, shape = _false, _rate, _digest, _shape

    def execute(spec, dispatch):
        rows = []
        for case in spec:
            try:
                actual = dispatch(case.operation, case.params)
                rows.append(
                    BenchmarkCaseResult(
                        case.case_id,
                        case.expected,
                        actual,
                        case.hostile
                        and actual == case.expected
                        and not false_predicate(case, actual),
                    )
                )
            except Exception as exc:
                rows.append(
                    BenchmarkCaseResult(
                        case.case_id,
                        case.expected,
                        CaseOutcome("INFRA_INVALID"),
                        False,
                        True,
                        type(exc).__name__,
                    )
                )
        return tuple(rows)

    def aggregate(spec, rows):
        eligible = tuple(r for r in rows if not r.infra_invalid)
        hostile = sum(c.hostile for c, r in zip(spec, rows) if not r.infra_invalid)
        false = sum(false_predicate(c, r.actual) for c, r in zip(spec, rows) if not r.infra_invalid)
        detected = sum(r.detected for r in eligible)
        mismatch = sum(r.actual != r.expected for r in eligible)
        payload = {
            "schema": BENCHMARK_SCHEMA,
            "benchmark_id": BENCHMARK_ID,
            "task_set_hash": task_hash,
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "case_ids": [r.case_id for r in rows],
            "eligible_count": len(eligible),
            "infra_invalid_count": len(rows) - len(eligible),
            "hostile_case_count": hostile,
            "detected_count": detected,
            "false_completion_count": false,
            "false_completion_rate": rate(false, hostile),
            "detection_rate": rate(detected, hostile),
            "trust_mismatch_count": mismatch,
            "trust_mismatch_rate": rate(mismatch, len(eligible)),
            "public_claim_gate": PUBLIC_CLAIM_GATE,
            "claim_ceiling": list(CLAIM_CEILING),
            "cases": [r.to_dict() for r in rows],
        }
        return FalseCompletionReport(
            **{k: v for k, v in payload.items() if k not in ("case_ids", "claim_ceiling", "cases")},
            case_ids=tuple(payload["case_ids"]),
            claim_ceiling=CLAIM_CEILING,
            cases=rows,
            report_hash=digest(payload),
        )

    def produce():
        return aggregate(run_spec, execute(run_spec, run_dispatch))

    def check(report):
        try:
            payload = (
                report.payload() if isinstance(report, FalseCompletionReport) else dict(report)
            )
            required = {
                "schema",
                "benchmark_id",
                "task_set_hash",
                "protocol_version",
                "implementation_schema",
                "case_ids",
                "eligible_count",
                "infra_invalid_count",
                "hostile_case_count",
                "detected_count",
                "false_completion_count",
                "false_completion_rate",
                "detection_rate",
                "trust_mismatch_count",
                "trust_mismatch_rate",
                "public_claim_gate",
                "claim_ceiling",
                "cases",
                "report_hash",
            }
            errors = [k for k in payload if k not in required] + [
                k for k in required if k not in payload
            ]
            if errors:
                return tuple(dict.fromkeys(errors))
            errors.extend(shape(payload))
            if errors:
                return tuple(dict.fromkeys(errors))
            if payload["report_hash"] != digest(
                {k: v for k, v in payload.items() if k != "report_hash"}
            ):
                errors.append("report_hash")
            # Independent verifier execution and aggregation; producer helpers are not used.
            rows = []
            for case in verify_spec:
                try:
                    actual = verify_dispatch(case.operation, case.params)
                    rows.append(
                        BenchmarkCaseResult(
                            case.case_id,
                            case.expected,
                            actual,
                            case.hostile
                            and actual == case.expected
                            and not false_predicate(case, actual),
                        )
                    )
                except Exception as exc:
                    rows.append(
                        BenchmarkCaseResult(
                            case.case_id,
                            case.expected,
                            CaseOutcome("INFRA_INVALID"),
                            False,
                            True,
                            type(exc).__name__,
                        )
                    )
            eligible = tuple(r for r in rows if not r.infra_invalid)
            hostile = sum(c.hostile for c, r in zip(verify_spec, rows) if not r.infra_invalid)
            false = sum(
                false_predicate(c, r.actual)
                for c, r in zip(verify_spec, rows)
                if not r.infra_invalid
            )
            detected = sum(r.detected for r in eligible)
            mismatch = sum(r.actual != r.expected for r in eligible)
            expected = {
                "schema": BENCHMARK_SCHEMA,
                "benchmark_id": BENCHMARK_ID,
                "task_set_hash": task_hash,
                "protocol_version": PUBLIC_PROTOCOL_VERSION,
                "implementation_schema": IMPLEMENTATION_SCHEMA,
                "case_ids": [r.case_id for r in rows],
                "eligible_count": len(eligible),
                "infra_invalid_count": len(rows) - len(eligible),
                "hostile_case_count": hostile,
                "detected_count": detected,
                "false_completion_count": false,
                "false_completion_rate": rate(false, hostile),
                "detection_rate": rate(detected, hostile),
                "trust_mismatch_count": mismatch,
                "trust_mismatch_rate": rate(mismatch, len(eligible)),
                "public_claim_gate": PUBLIC_CLAIM_GATE,
                "claim_ceiling": list(CLAIM_CEILING),
                "cases": [r.to_dict() for r in rows],
            }
            for key, value in expected.items():
                if payload[key] != value:
                    errors.append(key)
            return tuple(dict.fromkeys(errors))
        except Exception:
            return ("malformed_report",)

    return produce, check


run_benchmark, verify_report = _make_public_api()
__all__ = [
    "BENCHMARK_SCHEMA",
    "BENCHMARK_ID",
    "TASK_SET_HASH",
    "EXPECTED_CASE_IDS",
    "CASE_SPEC",
    "CASES",
    "CaseDefinition",
    "BenchmarkCaseResult",
    "FalseCompletionReport",
    "run_benchmark",
    "verify_report",
]
