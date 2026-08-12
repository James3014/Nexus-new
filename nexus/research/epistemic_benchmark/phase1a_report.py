"""Phase 1A authoritative report/replay substrate.

This module composes accepted G1/G2/G3 contracts.  It does not create a new
routing, consumption, settlement, approval, or release authority.  Reports are
rebuilt from bound source objects and verified by deterministic replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nexus.research.epistemic_benchmark.phase1a_contracts import (
    Phase1AArm,
    Phase1AArmIdentity,
    compute_canonical_sha256,
    compute_triplet_comparability_fingerprint,
    validate_triplet_comparability,
)
from nexus.research.epistemic_benchmark.phase1a_measurement import (
    ActionKind,
    AdmissibleObservationSet,
    Phase1ARecomputation,
    Phase1ATrajectory,
    RecomputationResult,
    TrajectoryPhase,
    compute_phase1a_metrics,
    compute_phase1a_recomputation,
    verify_observation_set_consumption,
)
from nexus.research.epistemic_benchmark.phase1a_qualification import (
    Phase1AFrozenManifest,
    Phase1ARunRow,
    RunClassification,
    RunKind,
    select_formal_effect_rows,
)
from nexus.services.verified_assist_contract import (
    evaluate_assist_credit,
    verify_consumption_proof,
)

PHASE1A_REPORT_SCHEMA = "nexus.epistemic_benchmark.phase1a_report.v1"
PHASE1A_REPORT_VERIFIER_SCHEMA = "nexus.epistemic_benchmark.phase1a_report_verifier.v1"

_ALLOWED_DECISIONS = {
    "EVIDENCE_INSUFFICIENT",
    "STOP",
    "REVISE",
    "CONTINUE",
    "NO_EFFECT",
}


@dataclass(frozen=True)
class Phase1ADecisionEvidence:
    """Frozen upstream decision evidence consumed by the report replay.

    The report does not decide whether these facts are true.  It binds their
    authoritative source identity and deterministically applies the frozen G4
    ordering.  The evidence object itself is therefore part of the source hash.
    """

    evidence_sha256: str
    integrity_sufficient: bool = True
    invalidity_excessive: bool = False
    false_success_detected: bool = False
    authority_regression_detected: bool = False
    safety_regression_detected: bool = False
    semantic_regression_detected: bool = False
    quality_preserved: bool = True

    def __post_init__(self) -> None:
        _require_sha256("evidence_sha256", self.evidence_sha256)
        for name in (
            "integrity_sufficient",
            "invalidity_excessive",
            "false_success_detected",
            "authority_regression_detected",
            "safety_regression_detected",
            "semantic_regression_detected",
            "quality_preserved",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_sha256": self.evidence_sha256,
            "integrity_sufficient": self.integrity_sufficient,
            "invalidity_excessive": self.invalidity_excessive,
            "false_success_detected": self.false_success_detected,
            "authority_regression_detected": self.authority_regression_detected,
            "safety_regression_detected": self.safety_regression_detected,
            "semantic_regression_detected": self.semantic_regression_detected,
            "quality_preserved": self.quality_preserved,
        }


@dataclass(frozen=True)
class Phase1AReportRunSource:
    arm_identity: Phase1AArmIdentity
    trajectory: Phase1ATrajectory
    run_row: Phase1ARunRow
    observation_set: AdmissibleObservationSet | None = None
    verified_assist_packet: Mapping[str, Any] | None = None
    verified_assist_consumption: Mapping[str, Any] | None = None
    settlement: Mapping[str, Any] | None = None
    reverified_observation_ids: tuple[str, ...] = ()
    contradictory_observation_ids: tuple[str, ...] = ()

    @property
    def arm(self) -> Phase1AArm:
        return self.arm_identity.arm


@dataclass(frozen=True)
class Phase1AReportSource:
    manifest: Phase1AFrozenManifest
    arm_a: Phase1AReportRunSource
    arm_b: Phase1AReportRunSource
    arm_c: Phase1AReportRunSource
    decision_evidence: Phase1ADecisionEvidence

    @property
    def runs(self) -> tuple[Phase1AReportRunSource, ...]:
        return (self.arm_a, self.arm_b, self.arm_c)


@dataclass(frozen=True)
class Phase1AReplayVerification:
    schema: str
    ok: bool
    reasons: tuple[str, ...]
    expected_report_sha256: str
    observed_report_sha256: str
    claim_boundary: Mapping[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "ok": self.ok,
            "reasons": list(self.reasons),
            "expected_report_sha256": self.expected_report_sha256,
            "observed_report_sha256": self.observed_report_sha256,
            "claim_boundary": dict(self.claim_boundary),
        }


def _mapping(value: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _require_sha256(name: str, value: Any) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a sha256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a sha256 hex digest") from exc


def _arm_key(arm: Phase1AArm) -> str:
    return {
        Phase1AArm.A: "A",
        Phase1AArm.B: "B",
        Phase1AArm.C: "C",
    }[arm]


def _verified_assist_packet_body(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild the exact content projection covered by VerifiedAssistPacket.packet_hash."""
    return {
        "task_id": packet.get("task_id"),
        "producer": packet.get("producer"),
        "reproduction_evidence": packet.get("reproduction_evidence"),
        "target_files": packet.get("target_files"),
        "exact_spans": packet.get("exact_spans"),
        "semantic_assertions": packet.get("semantic_assertions"),
        "failure_class": packet.get("failure_class"),
        "bounded_diagnosis": packet.get("bounded_diagnosis"),
        "verifier_evidence": packet.get("verifier_evidence"),
        "producer_verification": packet.get("producer_verification"),
        "treatment_run_id": packet.get("treatment_run_id"),
        "planner_decision_id": packet.get("planner_decision_id"),
        "task_contract_hash": packet.get("task_contract_hash"),
    }


def _provider_call_ledger(run: Phase1AReportRunSource) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "event_sha256": event.event_sha256,
            "sequence": event.sequence,
            "phase": event.phase.value,
            "provider": event.provider,
            "model": event.model,
            "status": event.status,
            "retry_count": event.retry_count,
        }
        for event in run.trajectory.events
        if event.action_kind == ActionKind.PROVIDER_CALL
    )


def _validate_provider_calls(manifest: Phase1AFrozenManifest, run: Phase1AReportRunSource) -> None:
    calls = [
        event for event in run.trajectory.events if event.action_kind == ActionKind.PROVIDER_CALL
    ]
    online = [event for event in calls if event.phase == TrajectoryPhase.ONLINE]
    if not online:
        raise ValueError(f"Arm {_arm_key(run.arm)} requires an Online provider call")
    if any(
        event.provider != manifest.online_provider or event.model != manifest.online_model
        for event in online
    ):
        raise ValueError(f"Arm {_arm_key(run.arm)} Online provider/model identity drift")

    local = [event for event in calls if event.phase == TrajectoryPhase.LOCAL_EXPLORATION]
    if run.arm in (Phase1AArm.A, Phase1AArm.B) and local:
        raise ValueError(f"Arm {_arm_key(run.arm)} rejects Local provider calls")
    if run.arm == Phase1AArm.C:
        if not local:
            raise ValueError("Arm C requires a Local exploration provider call")
        if any(
            event.provider != manifest.local_provider or event.model != manifest.local_model
            for event in local
        ):
            raise ValueError("Arm C Local provider/model identity drift")


def _validate_assist_binding(run: Phase1AReportRunSource) -> dict[str, Any]:
    if run.arm == Phase1AArm.A:
        if any(
            value is not None
            for value in (
                run.observation_set,
                run.verified_assist_packet,
                run.verified_assist_consumption,
                run.settlement,
            )
        ):
            raise ValueError("Arm A rejects Phase 1A assist evidence")
        return {
            "observation_set_sha256": "",
            "packet_hash": "",
            "consumption_proof": "",
            "settlement_sha256": "",
        }

    if run.observation_set is None:
        raise ValueError(f"Arm {_arm_key(run.arm)} requires an admissible observation set")
    if run.observation_set.task_id != run.arm_identity.task_id:
        raise ValueError("observation-set task identity drift")
    if run.observation_set.arm != run.arm:
        raise ValueError("observation-set arm identity drift")
    if run.verified_assist_packet is None or run.verified_assist_consumption is None:
        raise ValueError(
            f"Arm {_arm_key(run.arm)} requires packet and physical consumption evidence"
        )

    proof = verify_observation_set_consumption(
        run.observation_set,
        run.verified_assist_packet,
        run.verified_assist_consumption,
    )
    if proof.get("ok") is not True:
        raise ValueError(f"physical consumption verification failed: {proof.get('reason')}")
    consumption_check = verify_consumption_proof(run.verified_assist_consumption)
    if consumption_check.get("ok") is not True:
        raise ValueError(f"consumption proof invalid: {consumption_check.get('reason')}")
    credit = evaluate_assist_credit(run.verified_assist_consumption)
    if credit.get("assist_credited") is not True:
        raise ValueError(f"assist credit denied: {credit.get('reason')}")

    packet = _mapping(run.verified_assist_packet, "verified_assist_packet")
    consumption = _mapping(run.verified_assist_consumption, "verified_assist_consumption")
    packet_hash = str(packet.get("packet_hash") or "")
    if not packet_hash or packet_hash != str(consumption.get("packet_hash") or ""):
        raise ValueError("packet/consumption identity mismatch")
    if compute_canonical_sha256(_verified_assist_packet_body(packet)) != packet_hash:
        raise ValueError("verified assist packet hash mismatch")
    if str(packet.get("packet_id") or "") != str(consumption.get("packet_id") or ""):
        raise ValueError("packet/consumption packet-id mismatch")

    run_id = run.trajectory.events[0].run_id
    if str(packet.get("task_id") or "") != run.arm_identity.task_id:
        raise ValueError("packet task identity mismatch")
    if str(packet.get("treatment_run_id") or "") != run_id:
        raise ValueError("packet treatment-run identity mismatch")
    if str(packet.get("planner_decision_id") or "") != run.arm_identity.planner_decision_id:
        raise ValueError("packet planner-decision identity mismatch")
    if str(packet.get("task_contract_hash") or "") != run.arm_identity.task_contract_hash:
        raise ValueError("packet task-contract identity mismatch")

    settlement = _mapping(run.settlement, "settlement")
    if not settlement:
        raise ValueError(f"Arm {_arm_key(run.arm)} requires settlement evidence")
    settlement_credit = settlement.get("assist_credit")
    if not isinstance(settlement_credit, Mapping):
        raise ValueError("settlement assist-credit projection missing")
    if settlement_credit.get("assist_credited") is not True:
        raise ValueError("settlement does not credit physically consumed assist")
    if str(settlement_credit.get("packet_hash") or "") != packet_hash:
        raise ValueError("settlement packet identity mismatch")
    if str(settlement.get("treatment_run_id") or "") != run_id:
        raise ValueError("settlement treatment-run identity mismatch")
    if str(settlement.get("planner_decision_id") or "") != run.arm_identity.planner_decision_id:
        raise ValueError("settlement planner-decision identity mismatch")
    if str(settlement.get("task_contract_hash") or "") != run.arm_identity.task_contract_hash:
        raise ValueError("settlement task-contract identity mismatch")

    return {
        "observation_set_sha256": run.observation_set.admissible_observation_set_sha256,
        "packet_id": str(packet.get("packet_id") or ""),
        "packet_hash": packet_hash,
        "consumption_proof": str(consumption.get("consumption_proof") or ""),
        "settlement_sha256": compute_canonical_sha256(settlement),
    }


def _validate_source(source: Phase1AReportSource) -> None:
    if not isinstance(source, Phase1AReportSource):
        raise ValueError("source must be Phase1AReportSource")
    if tuple(run.arm for run in source.runs) != (Phase1AArm.A, Phase1AArm.B, Phase1AArm.C):
        raise ValueError("report source must contain exact A/B/C arm order")

    comparison = validate_triplet_comparability(
        source.arm_a.arm_identity,
        source.arm_b.arm_identity,
        source.arm_c.arm_identity,
    )
    if not comparison.is_comparable:
        raise ValueError("Phase 1A arm triplet is not comparable")

    task_id = source.arm_a.arm_identity.task_id
    if task_id not in set(source.manifest.formal_task_ids):
        raise ValueError("report task identity is outside frozen formal corpus")
    if source.manifest.online_provider != source.arm_a.arm_identity.online_provider:
        raise ValueError("frozen Online provider identity drift")
    if source.manifest.online_model != source.arm_a.arm_identity.online_model:
        raise ValueError("frozen Online model identity drift")

    for run in source.runs:
        if run.arm_identity.task_id != task_id:
            raise ValueError("run task identity drift")
        if run.run_row.task_id != task_id:
            raise ValueError("run-row task identity drift")
        if run.run_row.run_kind != RunKind.FORMAL:
            raise ValueError("qualification rows cannot enter Phase 1A formal report")
        if not run.trajectory.events or run.trajectory.events[0].task_id != task_id:
            raise ValueError("trajectory task identity drift")
        if run.trajectory.arm != run.arm:
            raise ValueError("trajectory arm identity drift")
        if run.trajectory.events[0].manifest_id != source.manifest.manifest_sha256:
            raise ValueError("trajectory frozen-manifest identity drift")
        _validate_provider_calls(source.manifest, run)
        _validate_assist_binding(run)

    selected = select_formal_effect_rows(source.manifest, tuple(run.run_row for run in source.runs))
    valid_rows = tuple(
        run.run_row
        for run in source.runs
        if run.run_row.classification
        in (RunClassification.VALID_SUCCESS, RunClassification.VALID_FAILURE)
    )
    if selected != valid_rows:
        raise ValueError("formal-effect row selection drift")


def _metric_projection(
    source: Phase1AReportSource,
    recomputation: Phase1ARecomputation,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for run, recompute in (
        (source.arm_a, None),
        (source.arm_b, recomputation.ba),
        (source.arm_c, recomputation.cb),
    ):
        if run.run_row.classification not in (
            RunClassification.VALID_SUCCESS,
            RunClassification.VALID_FAILURE,
        ):
            continue
        result[_arm_key(run.arm)] = compute_phase1a_metrics(
            run.trajectory,
            recomputation=recompute,
            observation_set=run.observation_set,
            verified_assist_packet=run.verified_assist_packet,
            verified_assist_consumption=run.verified_assist_consumption,
            reverified_observation_ids=run.reverified_observation_ids,
            contradictory_observation_ids=run.contradictory_observation_ids,
        )
    return result


def _recomputation_projection(value: RecomputationResult) -> dict[str, Any]:
    return {
        "mechanism": value.mechanism,
        "potential_total": value.potential_total,
        "recomputed_total": value.recomputed_total,
        "avoided_total": value.avoided_total,
        "per_signature": [
            {
                "action_signature": row.action_signature,
                "baseline_count": row.baseline_count,
                "validated_prework_count": row.validated_prework_count,
                "treatment_online_count": row.treatment_online_count,
                "potential": row.potential,
                "recomputed": row.recomputed,
                "avoided": row.avoided,
            }
            for row in value.per_signature
        ],
    }


def _decision(
    source: Phase1AReportSource,
    recomputation: Phase1ARecomputation,
) -> str:
    evidence = source.decision_evidence
    invalid_rows = [
        run.run_row
        for run in source.runs
        if run.run_row.classification
        not in (RunClassification.VALID_SUCCESS, RunClassification.VALID_FAILURE)
    ]
    if not evidence.integrity_sufficient or evidence.invalidity_excessive or invalid_rows:
        return "EVIDENCE_INSUFFICIENT"
    if (
        evidence.false_success_detected
        or evidence.authority_regression_detected
        or evidence.safety_regression_detected
    ):
        return "STOP"
    if evidence.semantic_regression_detected:
        return "REVISE"

    thresholds = source.manifest.meaningful_improvement_thresholds
    ba_threshold = thresholds.get("ba_min_avoided_actions")
    cb_threshold = thresholds.get("cb_min_avoided_actions")
    if ba_threshold is None or cb_threshold is None:
        return "EVIDENCE_INSUFFICIENT"
    if (
        evidence.quality_preserved
        and recomputation.ba.avoided_total >= ba_threshold
        and recomputation.cb.avoided_total >= cb_threshold
    ):
        return "CONTINUE"
    return "NO_EFFECT"


def _source_binding(
    source: Phase1AReportSource,
    recomputation: Phase1ARecomputation,
    metrics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    assist_bindings = {_arm_key(run.arm): _validate_assist_binding(run) for run in source.runs}
    return {
        "manifest_sha256": source.manifest.manifest_sha256,
        "manifest_version": source.manifest.manifest_version,
        "manifest_projection_sha256": compute_canonical_sha256(source.manifest.to_dict()),
        "triplet_fingerprint": compute_triplet_comparability_fingerprint(
            source.arm_a.arm_identity,
            source.arm_b.arm_identity,
            source.arm_c.arm_identity,
        ),
        "arm_identity_sha256": {
            _arm_key(run.arm): run.arm_identity.full_identity_hash() for run in source.runs
        },
        "trajectory_sha256": {
            _arm_key(run.arm): run.trajectory.trajectory_sha256 for run in source.runs
        },
        "trajectory_event_sha256": {
            _arm_key(run.arm): [event.event_sha256 for event in run.trajectory.events]
            for run in source.runs
        },
        "provider_call_ledger": {
            _arm_key(run.arm): list(_provider_call_ledger(run)) for run in source.runs
        },
        "assist_binding": assist_bindings,
        "run_classification": {
            _arm_key(run.arm): run.run_row.classification.value for run in source.runs
        },
        "run_row_sha256": {
            _arm_key(run.arm): compute_canonical_sha256({
                "task_id": run.run_row.task_id,
                "run_kind": run.run_row.run_kind.value,
                "classification": run.run_row.classification.value,
                "source_metrics": dict(run.run_row.metrics),
            })
            for run in source.runs
        },
        "metric_projection_sha256": compute_canonical_sha256(metrics),
        "ba_recomputation_sha256": compute_canonical_sha256(
            _recomputation_projection(recomputation.ba)
        ),
        "cb_recomputation_sha256": compute_canonical_sha256(
            _recomputation_projection(recomputation.cb)
        ),
        "decision_evidence": source.decision_evidence.to_dict(),
        "decision_evidence_projection_sha256": compute_canonical_sha256(
            source.decision_evidence.to_dict()
        ),
        "report_schema_verifier_hash": source.manifest.report_schema_verifier_hash,
    }


def build_phase1a_report(source: Phase1AReportSource) -> dict[str, Any]:
    """Build one deterministic Phase 1A report from authoritative source objects."""
    _validate_source(source)
    recomputation = compute_phase1a_recomputation(
        source.arm_a.trajectory,
        source.arm_b.trajectory,
        source.arm_c.trajectory,
    )
    metrics = _metric_projection(source, recomputation)
    source_binding = _source_binding(source, recomputation, metrics)
    decision = _decision(source, recomputation)
    if decision not in _ALLOWED_DECISIONS:
        raise AssertionError("unbounded Phase 1A report decision")

    body: dict[str, Any] = {
        "schema": PHASE1A_REPORT_SCHEMA,
        "source_binding": source_binding,
        "task_id": source.arm_a.arm_identity.task_id,
        "manifest_sha256": source.manifest.manifest_sha256,
        "formal_effect_arms": sorted(metrics),
        "metrics": metrics,
        "mechanisms": {
            "B_MINUS_A": _recomputation_projection(recomputation.ba),
            "C_MINUS_B": _recomputation_projection(recomputation.cb),
            "C_MINUS_A": {
                "kind": "TOTAL_EFFECT_ONLY",
                "online_tool_action_delta": (
                    metrics.get("C", {}).get("online_tool_action_count", 0)
                    - metrics.get("A", {}).get("online_tool_action_count", 0)
                ),
            },
        },
        "decision": decision,
        "thresholds": dict(source.manifest.meaningful_improvement_thresholds),
        "claim_boundary": {
            "verification_evidence_only": True,
            "issue29_complete": False,
            "g5_authorized": False,
            "route_authority": False,
            "approval_authority": False,
            "release_authority": False,
            "runtime_integration_proven": False,
            "causal_benefit_proven": False,
            "public_claim_allowed": False,
        },
    }
    body["report_sha256"] = compute_canonical_sha256(body)
    return body


def verify_phase1a_report(
    report: Mapping[str, Any],
    source: Phase1AReportSource,
) -> Phase1AReplayVerification:
    """Rebuild from source and compare the complete decision-bearing projection."""
    reasons: list[str] = []
    observed = dict(report) if isinstance(report, Mapping) else {}
    if not observed:
        reasons.append("REPORT_NOT_OBJECT")
        expected: dict[str, Any] = {}
    else:
        try:
            expected = build_phase1a_report(source)
        except (TypeError, ValueError, AssertionError):
            reasons.append("AUTHORITATIVE_REPLAY_FAILED")
            expected = {}

    if expected:
        if observed.get("schema") != PHASE1A_REPORT_SCHEMA:
            reasons.append("REPORT_SCHEMA_MISMATCH")
        observed_body = {key: value for key, value in observed.items() if key != "report_sha256"}
        expected_body = {key: value for key, value in expected.items() if key != "report_sha256"}
        if observed_body != expected_body:
            reasons.append("REPORT_PROJECTION_TAMPERED")
        observed_hash = str(observed.get("report_sha256") or "")
        expected_hash = str(expected.get("report_sha256") or "")
        if observed_hash != expected_hash:
            reasons.append("REPORT_HASH_MISMATCH")
        try:
            self_hash = compute_canonical_sha256(observed_body)
        except (TypeError, ValueError, RecursionError):
            reasons.append("REPORT_SELF_HASH_INVALID")
        else:
            if self_hash != observed_hash:
                reasons.append("REPORT_SELF_HASH_INVALID")
        if observed.get("claim_boundary") != expected.get("claim_boundary"):
            reasons.append("REPORT_CLAIM_BOUNDARY_MISMATCH")
    else:
        observed_hash = str(observed.get("report_sha256") or "")
        expected_hash = ""

    ordered = tuple(dict.fromkeys(reasons))
    return Phase1AReplayVerification(
        schema=PHASE1A_REPORT_VERIFIER_SCHEMA,
        ok=not ordered,
        reasons=ordered,
        expected_report_sha256=expected_hash,
        observed_report_sha256=observed_hash,
        claim_boundary={
            "verification_evidence_only": True,
            "issue29_complete": False,
            "g5_authorized": False,
            "approval_authority": False,
            "release_authority": False,
            "runtime_integration_proven": False,
            "causal_benefit_proven": False,
            "public_claim_allowed": False,
        },
    )


__all__ = [
    "PHASE1A_REPORT_SCHEMA",
    "PHASE1A_REPORT_VERIFIER_SCHEMA",
    "Phase1ADecisionEvidence",
    "Phase1AReportRunSource",
    "Phase1AReportSource",
    "Phase1AReplayVerification",
    "build_phase1a_report",
    "verify_phase1a_report",
]
