"""Candidate Adapter Interface and Simulated Adapter for Provider Adoption Experiments.

Defines the contract for candidate model adapters and provides a simulated
adapter for deterministic unit and regression testing.
"""

from __future__ import annotations

from nexus.calibration.provider_adoption.capability import (
    ALL_CAPABILITY_IDS,
    CapabilityProbeResult,
    CapabilityStatus,
)
from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    EvidenceLevel,
)
from nexus.calibration.provider_adoption.failure import (
    FailureClass,
    FailureObservationItem,
)
from nexus.calibration.provider_adoption.identity import (
    PhysicalIdentity,
    inspect_physical_host_identity,
)


def get_adapter_evidence_ceiling(adapter: CandidateAdapter | None) -> EvidenceLevel:
    """Extract maximum supportable evidence level ceiling from an adapter.

    Conservative fail-closed default: SIMULATED (never defaults to PHYSICAL).
    Hard-caps all SimulatedCandidateAdapter instances and subclasses to SIMULATED.
    """
    if adapter is None:
        return EvidenceLevel.SIMULATED
    raw = getattr(adapter, "max_evidence_level", None)
    if raw is None:
        raw = getattr(adapter, "get_max_evidence_level", None)
    if callable(raw):
        try:
            raw = raw()
        except Exception:
            raw = EvidenceLevel.SIMULATED

    level: EvidenceLevel
    if isinstance(raw, str):
        try:
            level = EvidenceLevel(raw)
        except ValueError:
            level = EvidenceLevel.SIMULATED
    elif isinstance(raw, EvidenceLevel):
        level = raw
    else:
        level = EvidenceLevel.SIMULATED

    # Invariant: ALL SimulatedCandidateAdapter instances and subclasses
    # use simulated execution semantics and MUST NEVER support evidence above SIMULATED.
    if isinstance(adapter, SimulatedCandidateAdapter):
        if level == EvidenceLevel.PHYSICAL:
            level = EvidenceLevel.SIMULATED

    return level


class CandidateAdapter:
    """Universal interface for candidate model adapters."""

    max_evidence_level: EvidenceLevel = EvidenceLevel.SIMULATED

    def is_environment_blocked(self) -> tuple[bool, str]:
        """Check if environment prevents execution."""
        return False, ""

    def inspect_identity(self) -> PhysicalIdentity:
        """Inspect physical host and candidate executable identity."""
        raise NotImplementedError

    def probe_capability(self, capability_id: str) -> CapabilityProbeResult:
        """Execute a physical probe for the given capability."""
        raise NotImplementedError

    def execute_case(self, case: CohortCase) -> tuple[str, bool, str | None, int]:
        """Execute a single cohort case.

        Returns: (output_text, schema_valid, failure_class, latency_ms)
        """
        raise NotImplementedError

    def inject_fault(self, failure_class: FailureClass) -> FailureObservationItem:
        """Execute physical fault injection or test error handling."""
        raise NotImplementedError


class SimulatedCandidateAdapter(CandidateAdapter):
    """Deterministic simulated adapter for testing the experiment lifecycle."""

    max_evidence_level: EvidenceLevel = EvidenceLevel.SIMULATED

    def __init__(
        self,
        *,
        provider_id: str = "simulated",
        model_id: str = "sim-v1",
        transport: str = "in_memory",
        supported_capabilities: set[str] | None = None,
        case_responses: dict[str, str] | None = None,
        fail_case_ids: set[str] | None = None,
        timeout_case_ids: set[str] | None = None,
        environment_blocked: bool = False,
        environment_blocker_reason: str = "",
        offline_verified: bool | None = None,
        exercised_faults: dict[FailureClass, bool] | None = None,
        default_latency_ms: int = 15,
        max_evidence_level: EvidenceLevel | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model_id = model_id
        self.transport = transport
        self.supported_capabilities = supported_capabilities or set(ALL_CAPABILITY_IDS)
        self.case_responses = case_responses or {}
        self.fail_case_ids = fail_case_ids or set()
        self.timeout_case_ids = timeout_case_ids or set()
        self.environment_blocked = environment_blocked
        self.environment_blocker_reason = environment_blocker_reason
        self.offline_verified = offline_verified
        self.exercised_faults = exercised_faults or {}
        self.default_latency_ms = default_latency_ms
        if max_evidence_level is not None:
            if max_evidence_level == EvidenceLevel.PHYSICAL and isinstance(
                self, SimulatedCandidateAdapter
            ):
                raise ValueError(
                    "SimulatedCandidateAdapter maximum supportable evidence level is SIMULATED. "
                    "Simulated evidence must never claim PHYSICAL ceiling."
                )
            self.max_evidence_level = max_evidence_level

    def is_environment_blocked(self) -> tuple[bool, str]:
        return self.environment_blocked, self.environment_blocker_reason

    def inspect_identity(self) -> PhysicalIdentity:
        net_dep = (
            "NONE"
            if self.offline_verified is True
            else ("ONLINE_REQUIRED" if self.offline_verified is False else "UNKNOWN")
        )
        return inspect_physical_host_identity(
            provider_id=self.provider_id,
            model_id=self.model_id,
            transport=self.transport,
            runtime_executable="simulated_runtime",
            runtime_version="1.0.0",
            adapter_generation="v1",
            model_generation="sim-gen-1",
            timestamp="2026-09-27T00:00:00Z",
            offline_verified=self.offline_verified,
            network_dependency_observed=net_dep,
        )

    def probe_capability(self, capability_id: str) -> CapabilityProbeResult:
        if self.environment_blocked:
            return CapabilityProbeResult(
                capability_id=capability_id,
                status=CapabilityStatus.BLOCKED,
                physical_evidence=f"Environment blocked: {self.environment_blocker_reason}",
                exit_code=1,
                latency_ms=0,
                error_message=self.environment_blocker_reason,
            )

        if capability_id in self.supported_capabilities:
            return CapabilityProbeResult(
                capability_id=capability_id,
                status=CapabilityStatus.SUPPORTED,
                physical_evidence="Simulated physical probe passed validation.",
                exit_code=0,
                latency_ms=self.default_latency_ms,
                raw_output="simulated_probe_success",
            )
        return CapabilityProbeResult(
            capability_id=capability_id,
            status=CapabilityStatus.UNSUPPORTED,
            physical_evidence="Simulated probe returned unsupported.",
            exit_code=0,
            latency_ms=self.default_latency_ms,
            error_message="capability_not_supported",
        )

    def execute_case(self, case: CohortCase) -> tuple[str, bool, str | None, int]:
        if case.case_id in self.timeout_case_ids:
            return "", False, FailureClass.PROVIDER_TIMEOUT.value, self.default_latency_ms * 10

        if case.case_id in self.fail_case_ids:
            return (
                "unexpected_output",
                False,
                FailureClass.INVALID_RESPONSE.value,
                self.default_latency_ms,
            )

        # Default success
        resp = self.case_responses.get(case.case_id, case.ground_truth)
        return resp, True, None, self.default_latency_ms

    def inject_fault(self, failure_class: FailureClass) -> FailureObservationItem:
        if failure_class in self.exercised_faults:
            fc = self.exercised_faults[failure_class]
            return FailureObservationItem(
                failure_class=failure_class,
                exercised=True,
                observed_fail_closed=fc,
                observed_retry_behavior="ISOLATE_AND_ABORT" if fc else "UNCONTROLLED_CRASH",
                evidence_notes="Simulated fault injection observed.",
            )
        return FailureObservationItem(
            failure_class=failure_class,
            exercised=False,
            observed_fail_closed=None,
            observed_retry_behavior="NOT_EVALUATED",
            evidence_notes="Fault injection not exercised.",
        )
