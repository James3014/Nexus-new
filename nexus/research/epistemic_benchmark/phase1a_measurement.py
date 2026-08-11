from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nexus.research.epistemic_benchmark.phase1a_contracts import (
    Phase1AArm,
    compute_canonical_sha256,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceProducerPhase(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    LOCAL = "LOCAL"


class EpistemicType(str, Enum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"


class ValidationState(str, Enum):
    ADMISSIBLE = "ADMISSIBLE"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class TrajectoryPhase(str, Enum):
    BASELINE = "BASELINE"
    DETERMINISTIC_PREWORK = "DETERMINISTIC_PREWORK"
    LOCAL_EXPLORATION = "LOCAL_EXPLORATION"
    EVIDENCE_VALIDATION = "EVIDENCE_VALIDATION"
    ONLINE = "ONLINE"
    FINAL_VERIFIER = "FINAL_VERIFIER"


class ActionKind(str, Enum):
    FILE_READ = "FILE_READ"
    SEARCH = "SEARCH"
    TEST = "TEST"
    TOOL_ACTION = "TOOL_ACTION"
    PROVIDER_CALL = "PROVIDER_CALL"
    EVIDENCE_OBSERVATION = "EVIDENCE_OBSERVATION"
    EVIDENCE_CONSUMPTION = "EVIDENCE_CONSUMPTION"
    VERIFICATION = "VERIFICATION"


@dataclass(frozen=True)
class EvidenceRef:
    ref: str
    source_sha256: str
    physical: bool = True

    def __post_init__(self) -> None:
        _require_text("evidence_ref", self.ref)
        _require_sha256("source_sha256", self.source_sha256)
        if not isinstance(self.physical, bool):
            raise ValueError("physical must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "source_sha256": self.source_sha256,
            "physical": self.physical,
        }


@dataclass(frozen=True)
class EvidenceObservation:
    task_id: str
    arm: Phase1AArm | str
    producer_phase: EvidenceProducerPhase | str
    epistemic_type: EpistemicType | str
    bounded_claim: str
    evidence_refs: tuple[EvidenceRef, ...]
    derivation_lineage: tuple[str, ...]
    validation_state: ValidationState | str
    validator_contract_hash: str
    validator_evidence_refs: tuple[str, ...] = ()
    producer_verifier_independent: bool = False
    claims_proven: bool = False
    claims_final: bool = False
    claims_approval_authority: bool = False
    claims_routing_authority: bool = False
    claims_final_semantic_correctness: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "arm", _coerce_enum(Phase1AArm, self.arm, "arm"))
        object.__setattr__(
            self,
            "producer_phase",
            _coerce_enum(
                EvidenceProducerPhase,
                self.producer_phase,
                "producer_phase",
            ),
        )
        object.__setattr__(
            self,
            "epistemic_type",
            _coerce_enum(EpistemicType, self.epistemic_type, "epistemic_type"),
        )
        object.__setattr__(
            self,
            "validation_state",
            _coerce_enum(
                ValidationState,
                self.validation_state,
                "validation_state",
            ),
        )

        _require_text("task_id", self.task_id)
        _require_text("bounded_claim", self.bounded_claim)
        _require_sha256("validator_contract_hash", self.validator_contract_hash)
        _require_text_tuple("derivation_lineage", self.derivation_lineage)
        _require_text_tuple("validator_evidence_refs", self.validator_evidence_refs)

        if not isinstance(self.evidence_refs, tuple):
            raise ValueError("evidence_refs must be a tuple")
        if not all(isinstance(ref, EvidenceRef) for ref in self.evidence_refs):
            raise ValueError("evidence_refs must contain EvidenceRef values")

        if self.epistemic_type == EpistemicType.OBSERVED:
            if not self.evidence_refs:
                raise ValueError("OBSERVED requires physical evidence references")
            if any(not ref.physical for ref in self.evidence_refs):
                raise ValueError("OBSERVED evidence references must be physical")

        if self.epistemic_type == EpistemicType.INFERRED:
            if not self.derivation_lineage:
                raise ValueError("INFERRED requires derivation lineage")

        if self.validation_state == ValidationState.ADMISSIBLE:
            if not self.validator_evidence_refs:
                raise ValueError("ADMISSIBLE requires validator evidence")
            if not self.producer_verifier_independent:
                raise ValueError(
                    "ADMISSIBLE requires producer/verifier independence"
                )

        if self.producer_phase == EvidenceProducerPhase.LOCAL:
            if self.arm != Phase1AArm.C:
                raise ValueError("Phase 1A Local evidence is allowed only in Arm C")

        authority_flags = {
            "claims_proven": self.claims_proven,
            "claims_final": self.claims_final,
            "claims_approval_authority": self.claims_approval_authority,
            "claims_routing_authority": self.claims_routing_authority,
            "claims_final_semantic_correctness": (
                self.claims_final_semantic_correctness
            ),
        }
        for name, value in authority_flags.items():
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be bool")
            if value:
                raise ValueError(
                    f"Phase 1A observation cannot claim authority: {name}"
                )

    def identity_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "arm": self.arm.value,
            "producer_phase": self.producer_phase.value,
            "epistemic_type": self.epistemic_type.value,
            "bounded_claim": self.bounded_claim,
            "evidence_refs": [ref.to_dict() for ref in self.evidence_refs],
            "derivation_lineage": list(self.derivation_lineage),
            "validation_state": self.validation_state.value,
            "validator_contract_hash": self.validator_contract_hash,
            "validator_evidence_refs": list(self.validator_evidence_refs),
            "producer_verifier_independent": self.producer_verifier_independent,
            "claims_proven": False,
            "claims_final": False,
            "claims_approval_authority": False,
            "claims_routing_authority": False,
            "claims_final_semantic_correctness": False,
        }

    @property
    def observation_sha256(self) -> str:
        return _stable_hash(self.identity_dict())

    @property
    def observation_id(self) -> str:
        return f"P1A-OBS-{self.observation_sha256[:24]}"


@dataclass(frozen=True)
class AdmissibleObservationSet:
    task_id: str
    arm: Phase1AArm
    observation_ids: tuple[str, ...]
    observation_hashes: tuple[str, ...]
    admissible_observation_set_sha256: str

    def provider_safe_handoff(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "arm": self.arm.value,
            "observation_ids": list(self.observation_ids),
            "admissible_observation_set_sha256": (
                self.admissible_observation_set_sha256
            ),
        }


def build_admissible_observation_set(
    observations: list[EvidenceObservation] | tuple[EvidenceObservation, ...],
) -> AdmissibleObservationSet:
    if not observations:
        raise ValueError("admissible observation set cannot be empty")
    if not all(isinstance(obs, EvidenceObservation) for obs in observations):
        raise ValueError("observation set contains an invalid observation value")

    first = observations[0]
    pairs: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for obs in observations:
        if obs.validation_state != ValidationState.ADMISSIBLE:
            raise ValueError("only ADMISSIBLE observations may enter handoff")
        if obs.task_id != first.task_id or obs.arm != first.arm:
            raise ValueError("observation set task/arm identity drift")
        if obs.observation_id in seen_ids:
            raise ValueError("duplicate observation identity")
        seen_ids.add(obs.observation_id)
        pairs.append((obs.observation_id, obs.observation_sha256))

    pairs.sort(key=lambda item: item[0])
    body = {
        "task_id": first.task_id,
        "arm": first.arm.value,
        "observations": [
            {"observation_id": obs_id, "observation_sha256": obs_hash}
            for obs_id, obs_hash in pairs
        ],
    }
    return AdmissibleObservationSet(
        task_id=first.task_id,
        arm=first.arm,
        observation_ids=tuple(obs_id for obs_id, _ in pairs),
        observation_hashes=tuple(obs_hash for _, obs_hash in pairs),
        admissible_observation_set_sha256=_stable_hash(body),
    )


@dataclass(frozen=True)
class ActionEvent:
    experiment_id: str
    manifest_id: str
    run_id: str
    scope_id: str
    task_id: str
    arm: Phase1AArm | str
    session_id: str
    attempt_id: str
    sequence: int
    phase: TrajectoryPhase | str
    actor_class: str
    normalized_target: str
    action_kind: ActionKind | str
    signature_payload: dict[str, Any]
    evidence_refs: tuple[str, ...] = ()
    provider: str = ""
    model: str = ""
    status: str = "OK"
    retry_count: int = 0
    started_at_ms: int = 0
    duration_ms: int = 0
    physical_artifact_sha256: str = ""
    validation_evidence_refs: tuple[str, ...] = ()
    uncached_input_tokens: int = 0
    fuzzy_signature: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arm", _coerce_enum(Phase1AArm, self.arm, "arm"))
        object.__setattr__(
            self,
            "phase",
            _coerce_enum(TrajectoryPhase, self.phase, "phase"),
        )
        object.__setattr__(
            self,
            "action_kind",
            _coerce_enum(ActionKind, self.action_kind, "action_kind"),
        )

        for name in (
            "experiment_id",
            "manifest_id",
            "run_id",
            "scope_id",
            "task_id",
            "session_id",
            "attempt_id",
            "actor_class",
            "normalized_target",
            "status",
        ):
            _require_text(name, getattr(self, name))

        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise ValueError("sequence must be an integer")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        _require_nonnegative_int("retry_count", self.retry_count)
        _require_nonnegative_int("started_at_ms", self.started_at_ms)
        _require_nonnegative_int("duration_ms", self.duration_ms)
        _require_nonnegative_int(
            "uncached_input_tokens",
            self.uncached_input_tokens,
        )
        _require_text_tuple("evidence_refs", self.evidence_refs)
        _require_text_tuple(
            "validation_evidence_refs",
            self.validation_evidence_refs,
        )

        if not isinstance(self.signature_payload, dict):
            raise ValueError("signature_payload must be a dict")
        _stable_hash(self.signature_payload)

        if self.action_kind == ActionKind.PROVIDER_CALL:
            _require_text("provider", self.provider)
            _require_text("model", self.model)

        if self.physical_artifact_sha256:
            _require_sha256(
                "physical_artifact_sha256",
                self.physical_artifact_sha256,
            )

        if self.fuzzy_signature is not None:
            raise ValueError(
                "fuzzy signature is exploratory-only and cannot be "
                "decision-bearing"
            )

    @property
    def action_signature(self) -> str:
        return _stable_hash(
            {
                "action_kind": self.action_kind.value,
                "normalized_target": self.normalized_target,
                "signature_payload": self.signature_payload,
            }
        )

    @property
    def trajectory_identity(self) -> tuple[str, ...]:
        return (
            self.experiment_id,
            self.manifest_id,
            self.run_id,
            self.scope_id,
            self.task_id,
            self.arm.value,
            self.session_id,
            self.attempt_id,
        )

    def identity_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "manifest_id": self.manifest_id,
            "run_id": self.run_id,
            "scope_id": self.scope_id,
            "task_id": self.task_id,
            "arm": self.arm.value,
            "session_id": self.session_id,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "phase": self.phase.value,
            "actor_class": self.actor_class,
            "normalized_target": self.normalized_target,
            "action_kind": self.action_kind.value,
            "action_signature": self.action_signature,
            "evidence_refs": list(self.evidence_refs),
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "retry_count": self.retry_count,
            "started_at_ms": self.started_at_ms,
            "duration_ms": self.duration_ms,
            "physical_artifact_sha256": self.physical_artifact_sha256,
            "validation_evidence_refs": list(self.validation_evidence_refs),
            "uncached_input_tokens": self.uncached_input_tokens,
        }

    @property
    def event_sha256(self) -> str:
        return _stable_hash(self.identity_dict())


@dataclass(frozen=True)
class Phase1ATrajectory:
    events: tuple[ActionEvent, ...]
    trajectory_sha256: str

    @property
    def arm(self) -> Phase1AArm:
        return self.events[0].arm

    @property
    def task_id(self) -> str:
        return self.events[0].task_id

    def phase_events(self, phase: TrajectoryPhase) -> tuple[ActionEvent, ...]:
        return tuple(event for event in self.events if event.phase == phase)


def validate_trajectory(
    events: list[ActionEvent] | tuple[ActionEvent, ...],
) -> Phase1ATrajectory:
    if not events:
        raise ValueError("trajectory cannot be empty")
    if not all(isinstance(event, ActionEvent) for event in events):
        raise ValueError("trajectory contains an invalid event value")

    first_identity = events[0].trajectory_identity
    previous_sequence = -1
    event_hashes: list[str] = []
    for event in events:
        if event.trajectory_identity != first_identity:
            raise ValueError("trajectory identity drift")
        if event.sequence <= previous_sequence:
            raise ValueError("trajectory sequence must be strictly increasing")
        previous_sequence = event.sequence
        event_hashes.append(event.event_sha256)

    body = {
        "trajectory_identity": list(first_identity),
        "event_sha256s": event_hashes,
    }
    return Phase1ATrajectory(
        events=tuple(events),
        trajectory_sha256=_stable_hash(body),
    )


@dataclass(frozen=True)
class SignatureRecomputation:
    action_signature: str
    baseline_count: int
    validated_prework_count: int
    treatment_online_count: int
    potential: int
    recomputed: int
    avoided: int


@dataclass(frozen=True)
class RecomputationResult:
    mechanism: str
    potential_total: int
    recomputed_total: int
    avoided_total: int
    per_signature: tuple[SignatureRecomputation, ...]


@dataclass(frozen=True)
class Phase1ARecomputation:
    ba: RecomputationResult
    cb: RecomputationResult


def compute_recomputation_avoided(
    *,
    baseline_online: tuple[ActionEvent, ...],
    validated_prework: tuple[ActionEvent, ...],
    treatment_online: tuple[ActionEvent, ...],
    mechanism: str,
) -> RecomputationResult:
    _require_text("mechanism", mechanism)
    baseline_counts = Counter(event.action_signature for event in baseline_online)
    prework_counts = Counter(event.action_signature for event in validated_prework)
    treatment_counts = Counter(
        event.action_signature for event in treatment_online
    )

    rows: list[SignatureRecomputation] = []
    signatures = sorted(set(baseline_counts) | set(prework_counts))
    for signature in signatures:
        baseline_count = baseline_counts[signature]
        prework_count = prework_counts[signature]
        treatment_count = treatment_counts[signature]
        potential = min(baseline_count, prework_count)
        recomputed = min(potential, treatment_count)
        avoided = potential - recomputed
        rows.append(
            SignatureRecomputation(
                action_signature=signature,
                baseline_count=baseline_count,
                validated_prework_count=prework_count,
                treatment_online_count=treatment_count,
                potential=potential,
                recomputed=recomputed,
                avoided=avoided,
            )
        )

    return RecomputationResult(
        mechanism=mechanism,
        potential_total=sum(row.potential for row in rows),
        recomputed_total=sum(row.recomputed for row in rows),
        avoided_total=sum(row.avoided for row in rows),
        per_signature=tuple(rows),
    )


def compute_phase1a_recomputation(
    arm_a: Phase1ATrajectory,
    arm_b: Phase1ATrajectory,
    arm_c: Phase1ATrajectory,
) -> Phase1ARecomputation:
    if arm_a.arm != Phase1AArm.A:
        raise ValueError("first trajectory must be Phase 1A Arm A")
    if arm_b.arm != Phase1AArm.B:
        raise ValueError("second trajectory must be Phase 1A Arm B")
    if arm_c.arm != Phase1AArm.C:
        raise ValueError("third trajectory must be Phase 1A Arm C")

    common_a = _triplet_measurement_identity(arm_a)
    if _triplet_measurement_identity(arm_b) != common_a:
        raise ValueError("A/B measurement identity drift")
    if _triplet_measurement_identity(arm_c) != common_a:
        raise ValueError("A/C measurement identity drift")

    a_online = arm_a.phase_events(TrajectoryPhase.ONLINE)
    b_prework = tuple(
        event
        for event in arm_b.phase_events(
            TrajectoryPhase.DETERMINISTIC_PREWORK
        )
        if event.validation_evidence_refs
    )
    b_online = arm_b.phase_events(TrajectoryPhase.ONLINE)
    c_local = tuple(
        event
        for event in arm_c.phase_events(TrajectoryPhase.LOCAL_EXPLORATION)
        if event.validation_evidence_refs
    )
    c_online = arm_c.phase_events(TrajectoryPhase.ONLINE)

    return Phase1ARecomputation(
        ba=compute_recomputation_avoided(
            baseline_online=a_online,
            validated_prework=b_prework,
            treatment_online=b_online,
            mechanism="B_MINUS_A_DETERMINISTIC_MEDIATION",
        ),
        cb=compute_recomputation_avoided(
            baseline_online=b_online,
            validated_prework=c_local,
            treatment_online=c_online,
            mechanism="C_MINUS_B_LOCAL_INCREMENT",
        ),
    )


@dataclass(frozen=True)
class FrozenTargetOracle:
    oracle_id: str
    oracle_sha256: str
    normalized_target: str
    independent: bool

    def __post_init__(self) -> None:
        _require_text("oracle_id", self.oracle_id)
        _require_sha256("oracle_sha256", self.oracle_sha256)
        _require_text("normalized_target", self.normalized_target)
        if self.independent is not True:
            raise ValueError("target oracle must be explicitly independent")


def compute_phase1a_metrics(
    trajectory: Phase1ATrajectory,
    *,
    recomputation: RecomputationResult | None = None,
    observation_set: AdmissibleObservationSet | None = None,
    consumed_observation_set_sha256: str | None = None,
    physical_consumption_proof_sha256: str | None = None,
    reverified_observation_ids: tuple[str, ...] = (),
    contradictory_observation_ids: tuple[str, ...] = (),
    frozen_target_oracle: FrozenTargetOracle | None = None,
) -> dict[str, Any]:
    online_events = trajectory.phase_events(TrajectoryPhase.ONLINE)
    final_events = trajectory.phase_events(TrajectoryPhase.FINAL_VERIFIER)

    online_tool_kinds = {
        ActionKind.FILE_READ,
        ActionKind.SEARCH,
        ActionKind.TEST,
        ActionKind.TOOL_ACTION,
    }
    online_tool_events = tuple(
        event for event in online_events if event.action_kind in online_tool_kinds
    )

    metrics: dict[str, Any] = {
        "online_tool_action_count": len(online_tool_events),
        "recomputation_avoided_count": (
            recomputation.avoided_total if recomputation else 0
        ),
        "recomputation_repeated_count": (
            recomputation.recomputed_total if recomputation else 0
        ),
        "repeated_file_reads": _repeated_exact_actions(
            online_events,
            ActionKind.FILE_READ,
        ),
        "repeated_searches": _repeated_exact_actions(
            online_events,
            ActionKind.SEARCH,
        ),
        "repeated_tests": _repeated_exact_actions(
            online_events,
            ActionKind.TEST,
        ),
        "time_to_first_correct_target_seconds": _time_to_first_target(
            trajectory,
            frozen_target_oracle,
        ),
        "final_verifier_action_count": len(final_events),
        "final_verifier_wall_time_seconds": (
            sum(event.duration_ms for event in final_events) / 1000.0
        ),
        "provider_call_count": sum(
            1
            for event in trajectory.events
            if event.action_kind == ActionKind.PROVIDER_CALL
        ),
        "provider_retry_count": sum(
            event.retry_count
            for event in trajectory.events
            if event.action_kind == ActionKind.PROVIDER_CALL
        ),
        "online_wall_time_seconds": (
            sum(event.duration_ms for event in online_events) / 1000.0
        ),
        "uncached_equivalent_online_input_tokens": sum(
            event.uncached_input_tokens for event in online_events
        ),
    }

    utilization = _evidence_rates(
        observation_set=observation_set,
        consumed_observation_set_sha256=consumed_observation_set_sha256,
        physical_consumption_proof_sha256=(
            physical_consumption_proof_sha256
        ),
        reverified_observation_ids=reverified_observation_ids,
        contradictory_observation_ids=contradictory_observation_ids,
    )
    metrics.update(utilization)
    return metrics


def _evidence_rates(
    *,
    observation_set: AdmissibleObservationSet | None,
    consumed_observation_set_sha256: str | None,
    physical_consumption_proof_sha256: str | None,
    reverified_observation_ids: tuple[str, ...],
    contradictory_observation_ids: tuple[str, ...],
) -> dict[str, float | None]:
    _require_text_tuple(
        "reverified_observation_ids",
        reverified_observation_ids,
    )
    _require_text_tuple(
        "contradictory_observation_ids",
        contradictory_observation_ids,
    )

    if observation_set is None:
        if consumed_observation_set_sha256 or physical_consumption_proof_sha256:
            raise ValueError("consumption evidence requires an observation set")
        return {
            "evidence_utilization_rate": None,
            "evidence_reverification_rate": None,
            "contradictory_evidence_rate": None,
        }

    known_ids = set(observation_set.observation_ids)
    reverified = set(reverified_observation_ids)
    contradictory = set(contradictory_observation_ids)
    if not reverified <= known_ids:
        raise ValueError("reverified observation identity is outside the set")
    if not contradictory <= known_ids:
        raise ValueError("contradictory observation identity is outside the set")

    denominator = len(known_ids)
    if denominator == 0:
        raise ValueError("admissible observation set cannot be empty")

    physically_consumed = False
    if consumed_observation_set_sha256 is not None:
        _require_sha256(
            "consumed_observation_set_sha256",
            consumed_observation_set_sha256,
        )
        if (
            consumed_observation_set_sha256
            != observation_set.admissible_observation_set_sha256
        ):
            raise ValueError("observation-set substitution detected")
        if physical_consumption_proof_sha256 is not None:
            _require_sha256(
                "physical_consumption_proof_sha256",
                physical_consumption_proof_sha256,
            )
            physically_consumed = True
    elif physical_consumption_proof_sha256 is not None:
        raise ValueError("physical consumption proof lacks set identity")

    return {
        "evidence_utilization_rate": 1.0 if physically_consumed else 0.0,
        "evidence_reverification_rate": len(reverified) / denominator,
        "contradictory_evidence_rate": len(contradictory) / denominator,
    }


def _time_to_first_target(
    trajectory: Phase1ATrajectory,
    oracle: FrozenTargetOracle | None,
) -> float | None:
    if oracle is None:
        return None
    start_ms = min(event.started_at_ms for event in trajectory.events)
    matches = [
        event.started_at_ms
        for event in trajectory.events
        if event.normalized_target == oracle.normalized_target
    ]
    if not matches:
        return None
    return (min(matches) - start_ms) / 1000.0


def _repeated_exact_actions(
    events: tuple[ActionEvent, ...],
    kind: ActionKind,
) -> int:
    counts = Counter(
        event.action_signature for event in events if event.action_kind == kind
    )
    return sum(max(0, count - 1) for count in counts.values())


def _triplet_measurement_identity(
    trajectory: Phase1ATrajectory,
) -> tuple[str, str, str, str]:
    first = trajectory.events[0]
    return (
        first.experiment_id,
        first.manifest_id,
        first.scope_id,
        first.task_id,
    )


def _coerce_enum(enum_type: type[Enum], value: Any, name: str) -> Any:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}: {value!r}") from exc


def _require_text(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _require_text_tuple(name: str, value: Any) -> None:
    if not isinstance(value, tuple):
        raise ValueError(f"{name} must be a tuple")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{name} must contain non-empty strings")


def _require_sha256(name: str, value: Any) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")


def _require_nonnegative_int(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _stable_hash(payload: Any) -> str:
    try:
        return compute_canonical_sha256(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "decision-bearing identity contains an unordered or invalid value"
        ) from exc
