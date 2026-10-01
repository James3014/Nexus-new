"""Strict, immutable observation-only Completion Path telemetry contracts."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Annotated, Any, Literal, Mapping, Sequence, Union

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

SCHEMA = "nexus.completion_path_telemetry.v1"

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")

NOT_OBSERVED = "NOT_OBSERVED"
NotObservedLiteral = Literal["NOT_OBSERVED"]
FrictionValue = Union[StrictInt, NotObservedLiteral]
MilestoneValue = Union[AwareDatetime, NotObservedLiteral]


class ObservabilityStatus(str, Enum):
    NOT_OBSERVED = "NOT_OBSERVED"
    OBSERVED = "OBSERVED"


def _validate_evidence_ref(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("MALFORMED_EVIDENCE_REF")
    stripped = v.strip()
    ref = stripped[7:] if stripped.startswith("sha256:") else stripped
    if not SHA64.fullmatch(ref):
        raise ValueError("MALFORMED_EVIDENCE_REF")
    return stripped


def _validate_git_sha(v: str, field_name: str = "git_sha") -> str:
    if not isinstance(v, str) or not SHA40.fullmatch(v):
        raise ValueError(f"MALFORMED_{field_name.upper()}")
    return v


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


class _TelemetryFrozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MilestoneType(str, Enum):
    READY = "READY"
    CANDIDATE_READY = "CANDIDATE_READY"
    VERIFIED = "VERIFIED"
    PR_READY = "PR_READY"
    MERGED = "MERGED"
    RECONCILED = "RECONCILED"
    CLOSED = "CLOSED"


MILESTONE_ORDER: dict[MilestoneType, int] = {
    MilestoneType.READY: 1,
    MilestoneType.CANDIDATE_READY: 2,
    MilestoneType.VERIFIED: 3,
    MilestoneType.PR_READY: 4,
    MilestoneType.MERGED: 5,
    MilestoneType.RECONCILED: 6,
    MilestoneType.CLOSED: 7,
}


class FrictionType(str, Enum):
    UNNECESSARY_OWNER_INTERRUPT = "UNNECESSARY_OWNER_INTERRUPT"
    UNNECESSARY_FULL_REBIND = "UNNECESSARY_FULL_REBIND"
    DUPLICATE_VERIFICATION = "DUPLICATE_VERIFICATION"
    BLOCKED_LANE_GLOBAL_STOP = "BLOCKED_LANE_GLOBAL_STOP"


class ExternalOwnerGateType(str, Enum):
    PLATFORM = "PLATFORM"
    SECRET = "SECRET"
    OAUTH = "OAUTH"
    PRODUCTION = "PRODUCTION"


class RebindDimension(str, Enum):
    """Dimensions whose fresh evidence is proven affected and may be rechecked."""

    SOURCE_IDENTITY_DRIFT = "SOURCE_IDENTITY_DRIFT"
    SEMANTIC_OVERLAP = "SEMANTIC_OVERLAP"
    TEST_IMPACT = "TEST_IMPACT"
    AUTHORITY_DRIFT = "AUTHORITY_DRIFT"
    TRANSPORT_DRIFT = "TRANSPORT_DRIFT"


class BaseTelemetryEvent(_TelemetryFrozen):
    issue_id: StrictStr
    timestamp: AwareDatetime
    evidence_ref: StrictStr

    @field_validator("issue_id")
    @classmethod
    def _validate_issue_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ISSUE_ID_REQUIRED")
        return v.strip()

    @field_validator("evidence_ref")
    @classmethod
    def _validate_ref(cls, v: str) -> str:
        return _validate_evidence_ref(v)


class MilestoneEvent(BaseTelemetryEvent):
    event_type: Literal["MILESTONE"] = "MILESTONE"
    milestone: MilestoneType
    candidate_id: StrictStr | None = None
    repository: StrictStr | None = None
    pr_number: StrictInt | None = None
    candidate_head: StrictStr | None = None
    integration_head: StrictStr | None = None
    integration_generation: StrictInt | None = Field(default=None, ge=1)
    integration_base_sha: StrictStr | None = None
    merge_commit_sha: StrictStr | None = None
    current_main_sha: StrictStr | None = None

    @field_validator(
        "candidate_head",
        "integration_head",
        "integration_base_sha",
        "merge_commit_sha",
        "current_main_sha",
    )
    @classmethod
    def _validate_shas(cls, v: str | None, info: Any) -> str | None:
        if v is not None:
            return _validate_git_sha(v, info.field_name)
        return v

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("CANDIDATE_ID_REQUIRED")
        return v.strip() if v is not None else None

    @field_validator("repository")
    @classmethod
    def _validate_repo(cls, v: str | None) -> str | None:
        if v is not None and not REPO_PATTERN.fullmatch(v):
            raise ValueError("REPOSITORY_INVALID")
        return v

    @field_validator("pr_number")
    @classmethod
    def _validate_pr(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("PR_NUMBER_INVALID")
        return v

    @model_validator(mode="after")
    def _validate_stage_bindings(self) -> MilestoneEvent:
        int_fields = (self.integration_head, self.integration_generation, self.integration_base_sha)
        if any(f is not None for f in int_fields) and not all(f is not None for f in int_fields):
            raise ValueError("PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN")
        order = MILESTONE_ORDER[self.milestone]
        if order >= MILESTONE_ORDER[MilestoneType.CANDIDATE_READY]:
            if not self.candidate_id:
                raise ValueError(f"CANDIDATE_ID_REQUIRED_FOR_{self.milestone.value}")
        if order >= MILESTONE_ORDER[MilestoneType.PR_READY]:
            if not self.repository:
                raise ValueError(f"REPOSITORY_REQUIRED_FOR_{self.milestone.value}")
            if self.pr_number is None:
                raise ValueError(f"PR_NUMBER_REQUIRED_FOR_{self.milestone.value}")
            if not self.candidate_head:
                raise ValueError(f"CANDIDATE_HEAD_REQUIRED_FOR_{self.milestone.value}")
        if self.milestone == MilestoneType.MERGED:
            if not self.merge_commit_sha:
                raise ValueError("MERGE_COMMIT_SHA_REQUIRED_FOR_MERGED")
            if not self.current_main_sha:
                raise ValueError("CURRENT_MAIN_SHA_REQUIRED_FOR_MERGED")
        return self


class UnnecessaryOwnerInterruptEvent(BaseTelemetryEvent):
    event_type: Literal["UNNECESSARY_OWNER_INTERRUPT"] = "UNNECESSARY_OWNER_INTERRUPT"
    reason: StrictStr | None = None


class UnnecessaryFullRebindEvent(BaseTelemetryEvent):
    event_type: Literal["UNNECESSARY_FULL_REBIND"] = "UNNECESSARY_FULL_REBIND"
    candidate_id: StrictStr = Field(min_length=1)
    reason: StrictStr | None = None

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("CANDIDATE_ID_REQUIRED")
        return v.strip()


class DuplicateVerificationEvent(BaseTelemetryEvent):
    event_type: Literal["DUPLICATE_VERIFICATION"] = "DUPLICATE_VERIFICATION"
    candidate_id: StrictStr = Field(min_length=1)
    verifier_ref: StrictStr | None = None

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("CANDIDATE_ID_REQUIRED")
        return v.strip()

    @field_validator("verifier_ref")
    @classmethod
    def _validate_verifier_ref(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_evidence_ref(v)
        return v


class BlockedLaneGlobalStopEvent(BaseTelemetryEvent):
    event_type: Literal["BLOCKED_LANE_GLOBAL_STOP"] = "BLOCKED_LANE_GLOBAL_STOP"
    lane_id: StrictStr = Field(min_length=1)
    reason: StrictStr | None = None

    @field_validator("lane_id")
    @classmethod
    def _validate_lane_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("LANE_ID_REQUIRED")
        return v.strip()


class GenuineExternalOwnerGateEvent(BaseTelemetryEvent):
    event_type: Literal["GENUINE_EXTERNAL_OWNER_GATE"] = "GENUINE_EXTERNAL_OWNER_GATE"
    gate_type: ExternalOwnerGateType
    reason: StrictStr | None = None


class AffectedDimensionRebindEvent(BaseTelemetryEvent):
    event_type: Literal["AFFECTED_DIMENSION_REBIND"] = "AFFECTED_DIMENSION_REBIND"
    candidate_id: StrictStr = Field(min_length=1)
    dimension: RebindDimension
    reason: StrictStr | None = None
    integration_head: StrictStr | None = None
    integration_generation: StrictInt | None = Field(default=None, ge=1)
    integration_base_sha: StrictStr | None = None

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("CANDIDATE_ID_REQUIRED")
        return v.strip()

    @field_validator("integration_head", "integration_base_sha")
    @classmethod
    def _validate_shas(cls, v: str | None, info: Any) -> str | None:
        if v is not None:
            return _validate_git_sha(v, info.field_name)
        return v

    @model_validator(mode="after")
    def _validate_rebind_bindings(self) -> AffectedDimensionRebindEvent:
        int_fields = (self.integration_head, self.integration_generation, self.integration_base_sha)
        if any(f is not None for f in int_fields) and not all(f is not None for f in int_fields):
            raise ValueError("PARTIAL_INTEGRATION_SUBJECT_FORBIDDEN")
        return self


class ObservationWindowClosureWitness(BaseTelemetryEvent):
    event_type: Literal["OBSERVATION_WINDOW_CLOSURE"] = "OBSERVATION_WINDOW_CLOSURE"
    closed_at: AwareDatetime | None = None
    closure_reason: StrictStr | None = None

    @model_validator(mode="after")
    def _align_and_validate_closed_at(self) -> ObservationWindowClosureWitness:
        if self.closed_at is None:
            object.__setattr__(self, "closed_at", self.timestamp)
        elif self.closed_at != self.timestamp:
            raise ValueError("CLOSED_AT_TIMESTAMP_MISMATCH")
        return self


TelemetryEvent = Union[
    MilestoneEvent,
    UnnecessaryOwnerInterruptEvent,
    UnnecessaryFullRebindEvent,
    DuplicateVerificationEvent,
    BlockedLaneGlobalStopEvent,
    GenuineExternalOwnerGateEvent,
    AffectedDimensionRebindEvent,
    ObservationWindowClosureWitness,
]

telemetry_event_adapter: TypeAdapter[TelemetryEvent] = TypeAdapter(
    Annotated[TelemetryEvent, Field(discriminator="event_type")]
)


def parse_telemetry_event(data: Mapping[str, Any]) -> TelemetryEvent:
    return telemetry_event_adapter.validate_python(data)


class CompletionPathTelemetryProjection(_TelemetryFrozen):
    schema_version: StrictStr = SCHEMA
    issue_id: StrictStr
    candidate_id: StrictStr | None = None
    repository: StrictStr | None = None
    pr_number: StrictInt | None = None
    candidate_head: StrictStr | None = None
    integration_head: StrictStr | None = None
    integration_generation: StrictInt | None = None
    integration_base_sha: StrictStr | None = None
    merge_commit_sha: StrictStr | None = None
    current_main_sha: StrictStr | None = None

    ready_at: MilestoneValue = NOT_OBSERVED
    candidate_ready_at: MilestoneValue = NOT_OBSERVED
    verified_at: MilestoneValue = NOT_OBSERVED
    pr_ready_at: MilestoneValue = NOT_OBSERVED
    merged_at: MilestoneValue = NOT_OBSERVED
    reconciled_at: MilestoneValue = NOT_OBSERVED
    closed_at: MilestoneValue = NOT_OBSERVED

    milestone_evidence: Mapping[StrictStr, StrictStr] = Field(default_factory=dict)

    owner_interrupt_count: FrictionValue = NOT_OBSERVED
    unnecessary_full_rebind_count: FrictionValue = NOT_OBSERVED
    duplicate_verification_count: FrictionValue = NOT_OBSERVED
    blocked_lane_global_stop_count: FrictionValue = NOT_OBSERVED

    owner_interrupt_observability: ObservabilityStatus = ObservabilityStatus.NOT_OBSERVED
    unnecessary_full_rebind_observability: ObservabilityStatus = ObservabilityStatus.NOT_OBSERVED
    duplicate_verification_observability: ObservabilityStatus = ObservabilityStatus.NOT_OBSERVED
    blocked_lane_global_stop_observability: ObservabilityStatus = ObservabilityStatus.NOT_OBSERVED

    observation_window_closed: StrictBool = False
    observation_window_closed_at: AwareDatetime | None = None
    observation_window_witness_ref: StrictStr | None = None

    genuine_external_owner_gates_observed: StrictInt = 0
    affected_dimension_rebinds_observed: StrictInt = 0

    compression_gate_evaluable: StrictBool = False
    compression_gate_pass: StrictBool = False

    mutation_authorized: Literal[False] = False

    @field_validator("schema_version")
    @classmethod
    def _validate_schema(cls, v: str) -> str:
        if v != SCHEMA:
            raise ValueError("COMPLETION_PATH_TELEMETRY_SCHEMA_INVALID")
        return v

    @field_validator(
        "candidate_head",
        "integration_head",
        "integration_base_sha",
        "merge_commit_sha",
        "current_main_sha",
    )
    @classmethod
    def _validate_projection_shas(cls, v: str | None, info: Any) -> str | None:
        if v is not None:
            return _validate_git_sha(v, info.field_name)
        return v

    @field_validator("integration_generation")
    @classmethod
    def _validate_projection_generation(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("INTEGRATION_GENERATION_INVALID")
        return v

    @field_validator("repository")
    @classmethod
    def _validate_projection_repo(cls, v: str | None) -> str | None:
        if v is not None and not REPO_PATTERN.fullmatch(v):
            raise ValueError("REPOSITORY_INVALID")
        return v

    @field_validator("pr_number")
    @classmethod
    def _validate_projection_pr(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("PR_NUMBER_INVALID")
        return v

    @field_validator("candidate_id")
    @classmethod
    def _validate_projection_candidate_id(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("CANDIDATE_ID_REQUIRED")
        return v.strip() if v is not None else None

    @field_validator("mutation_authorized", mode="before")
    @classmethod
    def _validate_mutation(cls, v: Any) -> Literal[False]:
        if v is not False:
            raise ValueError("MUTATION_AUTHORIZATION_FORBIDDEN")
        return False

    @model_validator(mode="after")
    def _validate_projection_invariants(self) -> CompletionPathTelemetryProjection:
        milestone_values = {
            MilestoneType.READY: self.ready_at,
            MilestoneType.CANDIDATE_READY: self.candidate_ready_at,
            MilestoneType.VERIFIED: self.verified_at,
            MilestoneType.PR_READY: self.pr_ready_at,
            MilestoneType.MERGED: self.merged_at,
            MilestoneType.RECONCILED: self.reconciled_at,
            MilestoneType.CLOSED: self.closed_at,
        }
        evidence = dict(self.milestone_evidence)
        for milestone, value in milestone_values.items():
            if value != NOT_OBSERVED:
                ref = evidence.get(milestone.value)
                if ref is None:
                    raise ValueError("OBSERVED_MILESTONE_EVIDENCE_REQUIRED")
                _validate_evidence_ref(ref)
            elif milestone.value in evidence:
                raise ValueError("UNOBSERVED_MILESTONE_CANNOT_HAVE_EVIDENCE")

        counters = (
            self.owner_interrupt_count,
            self.unnecessary_full_rebind_count,
            self.duplicate_verification_count,
            self.blocked_lane_global_stop_count,
        )
        observability = (
            self.owner_interrupt_observability,
            self.unnecessary_full_rebind_observability,
            self.duplicate_verification_observability,
            self.blocked_lane_global_stop_observability,
        )
        for counter in counters:
            if isinstance(counter, int) and (isinstance(counter, bool) or counter < 0):
                raise ValueError("FRICTION_COUNTER_INVALID")

        if self.observation_window_closed:
            if (
                self.observation_window_closed_at is None
                or self.observation_window_witness_ref is None
            ):
                raise ValueError("OBSERVATION_WINDOW_WITNESS_REQUIRED")
            _validate_evidence_ref(self.observation_window_witness_ref)
            if any(status != ObservabilityStatus.OBSERVED for status in observability):
                raise ValueError("CLOSED_WINDOW_COUNTER_OBSERVABILITY_INVALID")
            if any(counter == NOT_OBSERVED for counter in counters):
                raise ValueError("CLOSED_WINDOW_COUNTER_NOT_OBSERVED")
        else:
            if (
                self.observation_window_closed_at is not None
                or self.observation_window_witness_ref is not None
            ):
                raise ValueError("OPEN_WINDOW_CANNOT_HAVE_CLOSURE_WITNESS")
            if any(status != ObservabilityStatus.NOT_OBSERVED for status in observability):
                raise ValueError("OPEN_WINDOW_COUNTER_OBSERVABILITY_INVALID")

        has_all_milestones = all(value != NOT_OBSERVED for value in milestone_values.values())
        has_identities = bool(
            self.issue_id
            and self.candidate_id
            and self.repository
            and self.pr_number
            and self.candidate_head
            and self.merge_commit_sha
            and self.current_main_sha
        )
        expected_evaluable = bool(
            self.observation_window_closed and has_all_milestones and has_identities
        )
        if self.compression_gate_evaluable != expected_evaluable:
            raise ValueError("COMPRESSION_GATE_EVALUABLE_INCONSISTENT")

        expected_pass = bool(
            expected_evaluable
            and self.owner_interrupt_count == 0
            and self.unnecessary_full_rebind_count == 0
            and self.duplicate_verification_count == 0
            and self.blocked_lane_global_stop_count == 0
        )
        if self.compression_gate_pass != expected_pass:
            raise ValueError("COMPRESSION_GATE_PASS_INCONSISTENT")
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def canonical_hash(self) -> str:
        return canonical_hash(self.to_dict())


def _canonical_event_key(event: BaseTelemetryEvent) -> str:
    payload = event.model_dump(mode="json")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def project_completion_path_telemetry(
    events: Sequence[TelemetryEvent],
) -> CompletionPathTelemetryProjection:
    if not events:
        raise ValueError("NO_EVENTS_PROVIDED")

    # Deterministic idempotent deduplication preserving encounter order. A reused
    # evidence hash must describe the same event; otherwise the evidence binding
    # is contradictory and fails closed.
    seen_keys: set[str] = set()
    evidence_payloads: dict[tuple[str, str, str], str] = {}
    unique_events: list[TelemetryEvent] = []
    for ev in events:
        key = _canonical_event_key(ev)
        milestone_identity = ev.milestone.value if isinstance(ev, MilestoneEvent) else ""
        evidence_identity = (ev.event_type, milestone_identity, ev.evidence_ref)
        prior_key = evidence_payloads.get(evidence_identity)
        if prior_key is not None and prior_key != key:
            raise ValueError("CONFLICTING_DUPLICATE_EVIDENCE_REF")
        evidence_payloads[evidence_identity] = key
        if key not in seen_keys:
            seen_keys.add(key)
            unique_events.append(ev)

    window_witnesses = [
        ev for ev in unique_events if isinstance(ev, ObservationWindowClosureWitness)
    ]
    if len(window_witnesses) > 1:
        raise ValueError("CONFLICTING_WINDOW_CLOSURE")
    window_witness: ObservationWindowClosureWitness | None = (
        window_witnesses[0] if window_witnesses else None
    )

    if window_witness is not None:
        closure_instant = window_witness.closed_at or window_witness.timestamp
        for ev in unique_events:
            if ev is not window_witness and ev.timestamp > closure_instant:
                raise ValueError(
                    f"POST_WINDOW_EVENT: event timestamp {ev.timestamp} is after window closure {closure_instant}"
                )

    issue_id: str | None = None
    candidate_id: str | None = None
    repository: str | None = None
    pr_number: int | None = None
    candidate_head: str | None = None
    integration_head: str | None = None
    integration_generation: int | None = None
    integration_base_sha: str | None = None
    merge_commit_sha: str | None = None
    current_main_sha: str | None = None

    milestone_timestamps: dict[MilestoneType, AwareDatetime] = {}
    milestone_events: dict[MilestoneType, MilestoneEvent] = {}

    friction_counts: dict[FrictionType, int] = {
        FrictionType.UNNECESSARY_OWNER_INTERRUPT: 0,
        FrictionType.UNNECESSARY_FULL_REBIND: 0,
        FrictionType.DUPLICATE_VERIFICATION: 0,
        FrictionType.BLOCKED_LANE_GLOBAL_STOP: 0,
    }

    genuine_external_owner_gates = 0
    affected_dimension_rebinds = 0

    window_witness: ObservationWindowClosureWitness | None = None

    for ev in unique_events:
        # 1. Issue ID binding and conflict check
        if issue_id is None:
            issue_id = ev.issue_id
        elif ev.issue_id != issue_id:
            raise ValueError(f"ISSUE_ID_CONFLICT: expected {issue_id}, got {ev.issue_id}")

        # 2. Window closure handling
        if isinstance(ev, ObservationWindowClosureWitness):
            if window_witness is not None:
                raise ValueError("CONFLICTING_WINDOW_CLOSURE")
            window_witness = ev
            closure_instant = ev.closed_at or ev.timestamp
            # Validate all previous events happened on or before closed_at
            for prev_ev in unique_events:
                if prev_ev.timestamp > closure_instant:
                    raise ValueError(
                        f"POST_WINDOW_EVENT: event timestamp {prev_ev.timestamp} is after window closure {closure_instant}"
                    )
            continue

        # 3. Post-window event check
        if window_witness is not None:
            closure_instant = window_witness.closed_at or window_witness.timestamp
            if ev.timestamp > closure_instant:
                raise ValueError(
                    f"POST_WINDOW_EVENT: event timestamp {ev.timestamp} is after window closure {closure_instant}"
                )

        # Track integration fields if present
        ev_int_gen = getattr(ev, "integration_generation", None)
        ev_int_head = getattr(ev, "integration_head", None)
        ev_int_base = getattr(ev, "integration_base_sha", None)

        if ev_int_gen is not None:
            if integration_generation is not None and ev_int_gen < integration_generation:
                raise ValueError(
                    f"INTEGRATION_GENERATION_REGRESSION: expected >= {integration_generation}, got {ev_int_gen}"
                )
            if integration_generation is not None and ev_int_gen > integration_generation:
                if ev_int_head is None:
                    raise ValueError("INTEGRATION_GENERATION_ADVANCE_REQUIRES_HEAD")

        if ev_int_head is not None:
            if integration_head is not None and ev_int_head != integration_head:
                if ev_int_gen is None:
                    raise ValueError("INTEGRATION_HEAD_CHANGED_WITHOUT_GENERATION_INCREMENT")
                if integration_generation is not None and ev_int_gen <= integration_generation:
                    raise ValueError("INTEGRATION_HEAD_CHANGED_WITHOUT_GENERATION_INCREMENT")
            integration_head = ev_int_head

        if ev_int_base is not None:
            if integration_base_sha is not None and ev_int_base != integration_base_sha:
                if ev_int_gen is None:
                    raise ValueError("INTEGRATION_BASE_CHANGED_WITHOUT_GENERATION_INCREMENT")
                if integration_generation is not None and ev_int_gen <= integration_generation:
                    raise ValueError("INTEGRATION_BASE_CHANGED_WITHOUT_GENERATION_INCREMENT")
            integration_base_sha = ev_int_base

        if ev_int_gen is not None:
            integration_generation = ev_int_gen

        # 4. Milestone event handling
        if isinstance(ev, MilestoneEvent):
            if ev.candidate_id is not None:
                if candidate_id is None:
                    candidate_id = ev.candidate_id
                elif ev.candidate_id != candidate_id:
                    raise ValueError(
                        f"CANDIDATE_ID_CONFLICT: expected {candidate_id}, got {ev.candidate_id}"
                    )

            if ev.repository is not None:
                if repository is None:
                    repository = ev.repository
                elif ev.repository != repository:
                    raise ValueError(
                        f"REPOSITORY_CONFLICT: expected {repository}, got {ev.repository}"
                    )

            if ev.pr_number is not None:
                if pr_number is None:
                    pr_number = ev.pr_number
                elif ev.pr_number != pr_number:
                    raise ValueError(
                        f"PR_NUMBER_CONFLICT: expected {pr_number}, got {ev.pr_number}"
                    )

            if ev.candidate_head is not None:
                if candidate_head is None:
                    candidate_head = ev.candidate_head
                elif ev.candidate_head != candidate_head:
                    raise ValueError(
                        f"CANDIDATE_HEAD_CONFLICT: expected {candidate_head}, got {ev.candidate_head}"
                    )

            if ev.merge_commit_sha is not None:
                if merge_commit_sha is None:
                    merge_commit_sha = ev.merge_commit_sha
                elif ev.merge_commit_sha != merge_commit_sha:
                    raise ValueError(
                        f"MERGE_COMMIT_SHA_CONFLICT: expected {merge_commit_sha}, got {ev.merge_commit_sha}"
                    )

            if ev.current_main_sha is not None:
                if current_main_sha is None:
                    current_main_sha = ev.current_main_sha
                elif ev.current_main_sha != current_main_sha:
                    raise ValueError(
                        f"CURRENT_MAIN_SHA_CONFLICT: expected {current_main_sha}, got {ev.current_main_sha}"
                    )

            if ev.milestone in milestone_events:
                raise ValueError(
                    f"CONFLICTING_DUPLICATE_MILESTONE: conflicting {ev.milestone.value} milestone"
                )

            milestone_timestamps[ev.milestone] = ev.timestamp
            milestone_events[ev.milestone] = ev

        # 5. Friction events handling
        elif isinstance(ev, UnnecessaryOwnerInterruptEvent):
            friction_counts[FrictionType.UNNECESSARY_OWNER_INTERRUPT] += 1
        elif isinstance(ev, UnnecessaryFullRebindEvent):
            if candidate_id is None:
                candidate_id = ev.candidate_id
            elif ev.candidate_id != candidate_id:
                raise ValueError(
                    f"CANDIDATE_ID_CONFLICT: expected {candidate_id}, got {ev.candidate_id}"
                )
            friction_counts[FrictionType.UNNECESSARY_FULL_REBIND] += 1
        elif isinstance(ev, DuplicateVerificationEvent):
            if candidate_id is None:
                candidate_id = ev.candidate_id
            elif ev.candidate_id != candidate_id:
                raise ValueError(
                    f"CANDIDATE_ID_CONFLICT: expected {candidate_id}, got {ev.candidate_id}"
                )
            friction_counts[FrictionType.DUPLICATE_VERIFICATION] += 1
        elif isinstance(ev, BlockedLaneGlobalStopEvent):
            friction_counts[FrictionType.BLOCKED_LANE_GLOBAL_STOP] += 1

        # 6. Non-friction events handling
        elif isinstance(ev, GenuineExternalOwnerGateEvent):
            genuine_external_owner_gates += 1
        elif isinstance(ev, AffectedDimensionRebindEvent):
            if candidate_id is None:
                candidate_id = ev.candidate_id
            elif ev.candidate_id != candidate_id:
                raise ValueError(
                    f"CANDIDATE_ID_CONFLICT: expected {candidate_id}, got {ev.candidate_id}"
                )
            affected_dimension_rebinds += 1

    # 7. Milestone order regression check across all observed milestones
    observed_milestones = sorted(milestone_timestamps.keys(), key=lambda m: MILESTONE_ORDER[m])
    for i in range(len(observed_milestones)):
        for j in range(i + 1, len(observed_milestones)):
            m1 = observed_milestones[i]
            m2 = observed_milestones[j]
            t1 = milestone_timestamps[m1]
            t2 = milestone_timestamps[m2]
            if t1 > t2:
                raise ValueError(
                    f"MILESTONE_ORDER_REGRESSION: {m1.value} at {t1} occurred after {m2.value} at {t2}"
                )

    # 8. Compute friction counters and per-counter observability
    has_closed_window = window_witness is not None
    if has_closed_window:
        owner_interrupt_count: FrictionValue = friction_counts[
            FrictionType.UNNECESSARY_OWNER_INTERRUPT
        ]
        unnecessary_full_rebind_count: FrictionValue = friction_counts[
            FrictionType.UNNECESSARY_FULL_REBIND
        ]
        duplicate_verification_count: FrictionValue = friction_counts[
            FrictionType.DUPLICATE_VERIFICATION
        ]
        blocked_lane_global_stop_count: FrictionValue = friction_counts[
            FrictionType.BLOCKED_LANE_GLOBAL_STOP
        ]

        owner_interrupt_observability = ObservabilityStatus.OBSERVED
        unnecessary_full_rebind_observability = ObservabilityStatus.OBSERVED
        duplicate_verification_observability = ObservabilityStatus.OBSERVED
        blocked_lane_global_stop_observability = ObservabilityStatus.OBSERVED
    else:
        owner_interrupt_count = (
            friction_counts[FrictionType.UNNECESSARY_OWNER_INTERRUPT]
            if friction_counts[FrictionType.UNNECESSARY_OWNER_INTERRUPT] > 0
            else NOT_OBSERVED
        )
        unnecessary_full_rebind_count = (
            friction_counts[FrictionType.UNNECESSARY_FULL_REBIND]
            if friction_counts[FrictionType.UNNECESSARY_FULL_REBIND] > 0
            else NOT_OBSERVED
        )
        duplicate_verification_count = (
            friction_counts[FrictionType.DUPLICATE_VERIFICATION]
            if friction_counts[FrictionType.DUPLICATE_VERIFICATION] > 0
            else NOT_OBSERVED
        )
        blocked_lane_global_stop_count = (
            friction_counts[FrictionType.BLOCKED_LANE_GLOBAL_STOP]
            if friction_counts[FrictionType.BLOCKED_LANE_GLOBAL_STOP] > 0
            else NOT_OBSERVED
        )

        owner_interrupt_observability = ObservabilityStatus.NOT_OBSERVED
        unnecessary_full_rebind_observability = ObservabilityStatus.NOT_OBSERVED
        duplicate_verification_observability = ObservabilityStatus.NOT_OBSERVED
        blocked_lane_global_stop_observability = ObservabilityStatus.NOT_OBSERVED

    # 9. Compute Compression Gate
    has_all_7_milestones = all(m in milestone_timestamps for m in MilestoneType)
    has_identities = bool(
        issue_id
        and candidate_id
        and repository
        and pr_number
        and candidate_head
        and merge_commit_sha
        and current_main_sha
    )
    compression_gate_evaluable = bool(has_all_7_milestones and has_identities and has_closed_window)
    compression_gate_pass = bool(
        compression_gate_evaluable
        and owner_interrupt_count == 0
        and unnecessary_full_rebind_count == 0
        and duplicate_verification_count == 0
        and blocked_lane_global_stop_count == 0
    )

    milestone_evidence = {m.value: ev.evidence_ref for m, ev in milestone_events.items()}

    assert issue_id is not None

    return CompletionPathTelemetryProjection(
        issue_id=issue_id,
        candidate_id=candidate_id,
        repository=repository,
        pr_number=pr_number,
        candidate_head=candidate_head,
        integration_head=integration_head,
        integration_generation=integration_generation,
        integration_base_sha=integration_base_sha,
        merge_commit_sha=merge_commit_sha,
        current_main_sha=current_main_sha,
        ready_at=milestone_timestamps.get(MilestoneType.READY, NOT_OBSERVED),
        candidate_ready_at=milestone_timestamps.get(MilestoneType.CANDIDATE_READY, NOT_OBSERVED),
        verified_at=milestone_timestamps.get(MilestoneType.VERIFIED, NOT_OBSERVED),
        pr_ready_at=milestone_timestamps.get(MilestoneType.PR_READY, NOT_OBSERVED),
        merged_at=milestone_timestamps.get(MilestoneType.MERGED, NOT_OBSERVED),
        reconciled_at=milestone_timestamps.get(MilestoneType.RECONCILED, NOT_OBSERVED),
        closed_at=milestone_timestamps.get(MilestoneType.CLOSED, NOT_OBSERVED),
        milestone_evidence=milestone_evidence,
        owner_interrupt_count=owner_interrupt_count,
        unnecessary_full_rebind_count=unnecessary_full_rebind_count,
        duplicate_verification_count=duplicate_verification_count,
        blocked_lane_global_stop_count=blocked_lane_global_stop_count,
        owner_interrupt_observability=owner_interrupt_observability,
        unnecessary_full_rebind_observability=unnecessary_full_rebind_observability,
        duplicate_verification_observability=duplicate_verification_observability,
        blocked_lane_global_stop_observability=blocked_lane_global_stop_observability,
        observation_window_closed=has_closed_window,
        observation_window_closed_at=window_witness.closed_at if window_witness else None,
        observation_window_witness_ref=window_witness.evidence_ref if window_witness else None,
        genuine_external_owner_gates_observed=genuine_external_owner_gates,
        affected_dimension_rebinds_observed=affected_dimension_rebinds,
        compression_gate_evaluable=compression_gate_evaluable,
        compression_gate_pass=compression_gate_pass,
        mutation_authorized=False,
    )
