from __future__ import annotations

from dataclasses import asdict, dataclass, field


NO_VERIFIED_CANDIDATE = "NO_VERIFIED_CANDIDATE"


@dataclass(frozen=True)
class S2TCandidate:
    candidate_id: str
    source: str
    content_ref: str
    claimed_outcome: str = ""
    static_score: float = 0.0
    selector_score: float = 0.0
    verifier_result: str = "not_run"
    evidence_refs: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id is required")
        if self.verifier_result not in {"pass", "fail", "not_run"}:
            raise ValueError("verifier_result must be pass, fail, or not_run")
        if not 0.0 <= float(self.static_score) <= 1.0:
            raise ValueError("static_score must be between 0.0 and 1.0")
        if not 0.0 <= float(self.selector_score) <= 1.0:
            raise ValueError("selector_score must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "S2TCandidate":
        allowed = set(cls.__dataclass_fields__)
        extra = set(payload) - allowed
        if extra:
            raise ValueError(f"unknown S2TCandidate fields: {sorted(extra)}")
        return cls(**payload)  # type: ignore[arg-type]


@dataclass(frozen=True)
class S2TSelectionDecision:
    selected_candidate_id: str
    gate_passed: bool
    reason_codes: list[str] = field(default_factory=list)
    selected_score: float = 0.0
    score_components: dict[str, float] = field(default_factory=dict)
    second_pass_required: bool = False


class S2TSelector:
    """Deterministic baseline selector for S2T shadow and strict modes."""

    def __init__(self, *, tie_threshold: float = 0.05) -> None:
        self.tie_threshold = max(0.0, float(tie_threshold or 0.0))

    def select(self, candidates: list[S2TCandidate]) -> S2TSelectionDecision:
        if not candidates:
            return S2TSelectionDecision(
                selected_candidate_id=NO_VERIFIED_CANDIDATE,
                gate_passed=False,
                reason_codes=["empty_candidate_set"],
            )

        reason_codes: list[str] = []
        if any(candidate.verifier_result == "fail" for candidate in candidates):
            reason_codes.append("verifier_failed_candidate_excluded")

        verified = [candidate for candidate in candidates if candidate.verifier_result == "pass"]
        if not verified:
            return S2TSelectionDecision(
                selected_candidate_id=NO_VERIFIED_CANDIDATE,
                gate_passed=False,
                reason_codes=reason_codes + ["no_verified_candidate"],
            )

        ranked = sorted(
            verified,
            key=lambda candidate: (
                candidate.selector_score,
                bool(candidate.evidence_refs),
                -len(candidate.risk_flags),
                candidate.static_score,
            ),
            reverse=True,
        )
        selected = ranked[0]
        if selected.evidence_refs:
            reason_codes.append("has_empirical_test_evidence")
        if "missing_test_evidence" not in selected.risk_flags:
            reason_codes.append("lower_claim_risk")
        second_pass_required = len(ranked) > 1 and (ranked[0].selector_score - ranked[1].selector_score) <= self.tie_threshold
        if second_pass_required:
            reason_codes.append("second_pass_required")
        return S2TSelectionDecision(
            selected_candidate_id=selected.candidate_id,
            gate_passed=True,
            reason_codes=reason_codes,
            selected_score=selected.selector_score,
            score_components=self._score_components(selected),
            second_pass_required=second_pass_required,
        )

    @staticmethod
    def _score_components(candidate: S2TCandidate) -> dict[str, float]:
        return {
            "selector_score": round(float(candidate.selector_score), 4),
            "static_score": round(float(candidate.static_score), 4),
            "empirical_evidence_present": 1.0 if candidate.evidence_refs else 0.0,
            "claim_risk_penalty": round(min(1.0, len(candidate.risk_flags) * 0.25), 4),
        }


@dataclass(frozen=True)
class S2TStrictGateResult:
    gate_passed: bool
    failure_reason: str = ""


class S2TStrictGate:
    """Fail-closed gate for claim and delivery-sensitive S2T decisions."""

    def evaluate(
        self,
        *,
        risk_tier: str,
        decision: S2TSelectionDecision,
        verifier_result: str,
        verifier_evidence_ref: str = "",
    ) -> S2TStrictGateResult:
        if not decision.gate_passed or decision.selected_candidate_id == NO_VERIFIED_CANDIDATE:
            return S2TStrictGateResult(False, "no_verified_candidate")
        if verifier_result != "pass":
            return S2TStrictGateResult(False, "verifier_not_passed")
        if risk_tier == "public_claim" and not verifier_evidence_ref.strip():
            return S2TStrictGateResult(False, "public_claim_requires_gate_evidence")
        return S2TStrictGateResult(True)


@dataclass(frozen=True)
class S2TAdoptionMetrics:
    eligible_rows: int
    selector_override_verified_rate: float
    original_top1_verified_rate: float
    trust_mismatch_delta: float
    public_claim_precision_delta: float
    heldout_win_rate: float


@dataclass(frozen=True)
class S2TAdoptionDecision:
    status: str
    reason_codes: list[str] = field(default_factory=list)

    @classmethod
    def from_metrics(cls, metrics: S2TAdoptionMetrics) -> "S2TAdoptionDecision":
        reasons: list[str] = []
        if metrics.eligible_rows < 30:
            reasons.append("insufficient_shadow_rows")
        if metrics.selector_override_verified_rate <= metrics.original_top1_verified_rate:
            reasons.append("no_override_lift")
        if metrics.trust_mismatch_delta > 0:
            reasons.append("trust_mismatch_regression")
        if metrics.public_claim_precision_delta < 0:
            reasons.append("public_claim_precision_regression")
        if metrics.heldout_win_rate <= 0.5:
            reasons.append("heldout_not_better_than_rule_selector")
        if reasons:
            return cls(status="shadow_only", reason_codes=reasons)
        return cls(status="strict_opt_in", reason_codes=["adoption_gate_passed"])
