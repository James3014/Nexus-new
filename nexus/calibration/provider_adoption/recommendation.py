"""G6 Promotion and Admission Recommendation module for Provider Adoption Experiments.

Schema: nexus.provider_experiment.recommendation.v1
Generates an advisory promotion recommendation bounded by contract claim ceiling
and aligned with Nexus Workforce Admission vocabulary.

Strict Invariants:
1. Verdict is ALWAYS 'ADMISSION_RECOMMENDATION_ONLY_NO_AUTHORITY_GRANTED'.
2. The experiment framework has ZERO authority to admit workers, route traffic, or grant permissions.
3. Recommended autonomy level is strictly clamped by the contract's claim_ceiling.
4. Uses canonical Nexus Autonomy levels (L0, L0.25, L0.5, L1, L2, L2+, L3) and
   workforce states (EXPERIMENT_ONLY, LOCAL_CONDITIONAL, REGISTERED_CONDITIONAL, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from nexus.calibration.provider_adoption.capability import (
    CapabilityMatrix,
    CapabilityProbeResult,
    CapabilityStatus,
)
from nexus.calibration.provider_adoption.contracts import (
    MetricsConfig,
    PassThresholds,
)
from nexus.contracts.workforce_admission import parse_autonomy_rank

RECOMMENDATION_SCHEMA = "nexus.provider_experiment.recommendation.v1"
FIXED_VERDICT = "ADMISSION_RECOMMENDATION_ONLY_NO_AUTHORITY_GRANTED"
AUTHORITY_DISCLAIMER = (
    "This recommendation is strictly non-authoritative evidence for the Owner and "
    "Workforce Admission authority. It grants no permissions, changes no routing tables, "
    "and does not constitute production admission."
)

ROLE_CAPABILITY_REQUIREMENTS: dict[str, str] = {
    "classification": "CAP-004",
    "extraction": "CAP-005",
    "simple_extraction": "CAP-005",
    "read_only_schema_candidate": "CAP-002",
}


@dataclass(frozen=True)
class AdmissionRecommendation:
    schema: str
    experiment_id: str
    candidate_provider_id: str
    candidate_model_id: str
    verdict: str
    recommended_state: str
    recommended_autonomy: str
    recommended_roles: tuple[str, ...]
    claim_ceiling: str
    clamped_by_ceiling: bool
    reasons: tuple[str, ...]
    required_controls: tuple[str, ...]
    authority_disclaimer: str = AUTHORITY_DISCLAIMER
    blocker_category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "experiment_id": self.experiment_id,
            "candidate_provider_id": self.candidate_provider_id,
            "candidate_model_id": self.candidate_model_id,
            "verdict": self.verdict,
            "recommended_state": self.recommended_state,
            "recommended_autonomy": self.recommended_autonomy,
            "recommended_roles": list(self.recommended_roles),
            "claim_ceiling": self.claim_ceiling,
            "clamped_by_ceiling": self.clamped_by_ceiling,
            "reasons": list(self.reasons),
            "required_controls": list(self.required_controls),
            "authority_disclaimer": self.authority_disclaimer,
            "blocker_category": self.blocker_category,
        }


def build_admission_recommendation(
    *,
    experiment_id: str,
    candidate_provider_id: str,
    candidate_model_id: str,
    claim_ceiling: str,
    accuracy: float,
    format_compliance: float,
    error_rate: float,
    offline_verified: bool,
    latency_p95_ms: int,
    semantic_correctness: float = 1.0,
    latency_p50_ms: int = 0,
    throughput_rps: float | None = None,
    pass_thresholds: PassThresholds | None = None,
    metrics_config: MetricsConfig | None = None,
    environment_blocked: bool = False,
    blocker_reason: str = "",
    blocker_category: str | None = None,
    capability_matrix: CapabilityMatrix | dict[str, CapabilityProbeResult] | None = None,
    allowed_capabilities: Sequence[str] | None = None,
) -> AdmissionRecommendation:
    """Build advisory recommendation clamped by ceiling and governed by contract thresholds."""
    reasons: list[str] = []
    controls: list[str] = [
        "NO_AUTONOMOUS_MUTATION",
        "NO_PROCESS_SPAWNING",
        "NO_NETWORK_ACCESS",
        "DETERMINISTIC_VERIFIER_REQUIRED",
    ]

    effective_category = blocker_category
    if effective_category is None and environment_blocked:
        effective_category = "ENVIRONMENT"

    if effective_category is not None:
        normalized_cat = (
            "DATA/COHORT"
            if effective_category in ("DATA/COHORT", "DATA_COHORT")
            else effective_category
        )
        if normalized_cat == "ENVIRONMENT":
            cat_reason = f"Candidate blocked by environment: {blocker_reason}"
        elif normalized_cat == "DATA/COHORT":
            cat_reason = f"Candidate blocked by dataset/cohort: {blocker_reason}"
        elif normalized_cat == "EVALUATION_STOP":
            cat_reason = f"Candidate stopped by evaluation condition: {blocker_reason}"
        else:
            cat_reason = f"Candidate blocked by {normalized_cat}: {blocker_reason}"

        return AdmissionRecommendation(
            schema=RECOMMENDATION_SCHEMA,
            experiment_id=experiment_id,
            candidate_provider_id=candidate_provider_id,
            candidate_model_id=candidate_model_id,
            verdict=FIXED_VERDICT,
            recommended_state="REGISTERED_BLOCKED",
            recommended_autonomy="L0",
            recommended_roles=(),
            claim_ceiling=claim_ceiling,
            clamped_by_ceiling=False,
            reasons=(cat_reason,),
            required_controls=tuple(controls),
            blocker_category=normalized_cat,
        )

    # 1. Enforce contract pass thresholds and operational metrics limits
    failed_thresholds: list[str] = []
    if pass_thresholds is not None:
        if accuracy < pass_thresholds.accuracy_min:
            failed_thresholds.append(
                f"Accuracy ({accuracy:.2f}) failed contract minimum threshold ({pass_thresholds.accuracy_min:.2f})."
            )
        if format_compliance < pass_thresholds.format_compliance_min:
            failed_thresholds.append(
                f"Format compliance rate ({format_compliance:.2f}) failed contract minimum threshold ({pass_thresholds.format_compliance_min:.2f})."
            )
        if semantic_correctness < pass_thresholds.semantic_correctness_min:
            failed_thresholds.append(
                f"Semantic correctness rate ({semantic_correctness:.2f}) failed contract minimum threshold ({pass_thresholds.semantic_correctness_min:.2f})."
            )

    if metrics_config is not None:
        if error_rate > metrics_config.max_error_rate:
            failed_thresholds.append(
                f"Error rate ({error_rate:.2f}) exceeded contract maximum ({metrics_config.max_error_rate:.2f})."
            )
        if latency_p50_ms > metrics_config.latency_p50_max_ms:
            failed_thresholds.append(
                f"P50 latency ({latency_p50_ms} ms) exceeded contract limit ({metrics_config.latency_p50_max_ms} ms)."
            )
        if latency_p95_ms > metrics_config.latency_p95_max_ms:
            failed_thresholds.append(
                f"P95 latency ({latency_p95_ms} ms) exceeded contract limit ({metrics_config.latency_p95_max_ms} ms)."
            )
        if throughput_rps is not None and throughput_rps < metrics_config.min_throughput_rps:
            failed_thresholds.append(
                f"Throughput ({throughput_rps:.2f} rps) failed contract minimum threshold ({metrics_config.min_throughput_rps:.2f} rps)."
            )

    if failed_thresholds:
        preliminary_autonomy = "L0"
        preliminary_state = "REGISTERED_BLOCKED"
        preliminary_roles = ()
        reasons.extend(failed_thresholds)
        reasons.append("Contract pass thresholds or metrics limits breached; candidate blocked.")
    else:
        # 2. Evaluate preliminary autonomy based on quality tiers
        if accuracy >= 0.95 and format_compliance >= 0.98 and error_rate <= 0.02:
            preliminary_autonomy = "L1"
            preliminary_state = (
                "LOCAL_CONDITIONAL" if offline_verified else "REGISTERED_CONDITIONAL"
            )
            preliminary_roles = (
                "classification",
                "extraction",
                "simple_extraction",
                "read_only_schema_candidate",
                "bounded_experiment",
            )
            reasons.append("Passed contract thresholds and achieved L1 qualification standards.")
        elif accuracy >= 0.80 and format_compliance >= 0.90 and error_rate <= 0.05:
            preliminary_autonomy = "L0.5"
            preliminary_state = "LOCAL_CONDITIONAL" if offline_verified else "EXPERIMENT_ONLY"
            preliminary_roles = (
                "simple_extraction",
                "read_only_schema_candidate",
                "bounded_experiment",
            )
            reasons.append("Passed contract thresholds and achieved L0.5 qualification standards.")
        elif accuracy >= 0.60:
            preliminary_autonomy = "L0.25"
            preliminary_state = "EXPERIMENT_ONLY"
            preliminary_roles = ("explicit_experiment_only",)
            reasons.append("Passed contract thresholds; restricted to explicit experiments only.")
        else:
            preliminary_autonomy = "L0"
            preliminary_state = "REGISTERED_BLOCKED"
            preliminary_roles = ()
            reasons.append("Quality below acceptable threshold; recommended state is BLOCKED.")

    # 3. Enforce capability evidence constraints (Invariant D12: quality != capability)
    probes: dict[str, CapabilityProbeResult] | None = None
    if isinstance(capability_matrix, CapabilityMatrix):
        probes = capability_matrix.probes
    elif isinstance(capability_matrix, dict):
        probes = capability_matrix

    if allowed_capabilities is not None or probes is not None:
        unsupported_caps: list[str] = []
        if allowed_capabilities is not None:
            for cap_id in allowed_capabilities:
                probe = probes.get(cap_id) if probes is not None else None
                if probe is None or probe.status != CapabilityStatus.SUPPORTED:
                    unsupported_caps.append(cap_id)

        if unsupported_caps:
            sorted_unsupported = sorted(unsupported_caps)
            reasons.append(
                f"Required allowed capabilities not supported or not evaluated: {', '.join(sorted_unsupported)}."
            )
            if preliminary_state != "REGISTERED_BLOCKED":
                if parse_autonomy_rank(preliminary_autonomy) > parse_autonomy_rank("L0.25"):
                    preliminary_autonomy = "L0.25"
                    preliminary_state = "EXPERIMENT_ONLY"
                    reasons.append(
                        "Preliminary autonomy capped at L0.25 / EXPERIMENT_ONLY due to unsupported or not-evaluated required capabilities."
                    )

        # Filter recommended roles: do not recommend a role unless its capability is SUPPORTED
        if probes is not None:
            filtered_roles: list[str] = []
            for role in preliminary_roles:
                req_cap = ROLE_CAPABILITY_REQUIREMENTS.get(role)
                if req_cap is not None:
                    probe = probes.get(req_cap)
                    if probe is not None and probe.status == CapabilityStatus.SUPPORTED:
                        filtered_roles.append(role)
                else:
                    # Roles without capability requirement (e.g. bounded_experiment, explicit_experiment_only)
                    filtered_roles.append(role)
            preliminary_roles = tuple(filtered_roles)

    # Clamp by contract claim ceiling
    ceiling_rank = parse_autonomy_rank(claim_ceiling)
    prelim_rank = parse_autonomy_rank(preliminary_autonomy)

    clamped = False
    final_autonomy = preliminary_autonomy
    if prelim_rank > ceiling_rank:
        final_autonomy = claim_ceiling
        clamped = True
        reasons.append(
            f"Preliminary autonomy {preliminary_autonomy} clamped to contract ceiling {claim_ceiling}."
        )

    return AdmissionRecommendation(
        schema=RECOMMENDATION_SCHEMA,
        experiment_id=experiment_id,
        candidate_provider_id=candidate_provider_id,
        candidate_model_id=candidate_model_id,
        verdict=FIXED_VERDICT,
        recommended_state=preliminary_state,
        recommended_autonomy=final_autonomy,
        recommended_roles=preliminary_roles,
        claim_ceiling=claim_ceiling,
        clamped_by_ceiling=clamped,
        reasons=tuple(reasons),
        required_controls=tuple(controls),
    )
