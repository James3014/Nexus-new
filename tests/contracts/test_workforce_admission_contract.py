from __future__ import annotations

from enum import Enum

import pytest

from nexus.contracts.workforce_admission import (
    AdmissionDecision,
    WorkforceAdmissionDecision,
    WorkforceAdmissionRequest,
    WorkforceWorker,
    parse_autonomy_rank,
)


def test_admission_decision_enum_values() -> None:
    assert AdmissionDecision.ALLOW.value == "ALLOW"
    assert AdmissionDecision.BLOCK.value == "BLOCK"
    assert AdmissionDecision.ESCALATE.value == "ESCALATE"


class _WrongEnumFamily(Enum):
    YES = "YES"


def test_admission_decision_rejects_forged_values_fail_closed() -> None:
    forged = [
        "FORGED",
        "ALLOW",
        "allow",
        "",
        None,
        0,
        1,
        1.5,
        [],
        {},
        object(),
        _WrongEnumFamily.YES,
    ]
    for value in forged:
        with pytest.raises(ValueError, match="must be an AdmissionDecision member"):
            WorkforceAdmissionDecision(decision=value)  # type: ignore[arg-type]


def test_admission_decision_valid_values_remain_deterministic() -> None:
    for member in (AdmissionDecision.ALLOW, AdmissionDecision.BLOCK, AdmissionDecision.ESCALATE):
        decision = WorkforceAdmissionDecision(decision=member)
        assert decision.decision is member
        assert decision.to_dict()["decision"] == member.value
    assert WorkforceAdmissionDecision().decision is AdmissionDecision.BLOCK


def test_gb021_admission_decision_preserves_fail_closed_reason() -> None:
    blocked = WorkforceAdmissionDecision(
        decision=AdmissionDecision.BLOCK,
        decision_reasons=("missing_controls",),
        missing_controls=("task_card",),
    )
    assert blocked.to_dict()["decision"] == "BLOCK"
    assert blocked.missing_controls == ("task_card",)
    with pytest.raises(ValueError):
        WorkforceAdmissionDecision(decision="ALLOW")  # type: ignore[arg-type]


def test_autonomy_level_deterministic_parsing_and_ordering() -> None:
    ranks = [
        parse_autonomy_rank("L0"),
        parse_autonomy_rank("L0.25"),
        parse_autonomy_rank("L0.5"),
        parse_autonomy_rank("L1"),
        parse_autonomy_rank("L2"),
        parse_autonomy_rank("L2+"),
        parse_autonomy_rank("L3_HISTORICAL"),
    ]
    # Check strictly increasing integer order without floating point ambiguity
    assert ranks == [0, 1, 2, 3, 4, 5, 6]
    assert sorted(ranks) == ranks

    with pytest.raises(ValueError, match="Unknown autonomy level"):
        parse_autonomy_rank("L4")


def test_workforce_admission_request_serialization_and_immutability() -> None:
    req = WorkforceAdmissionRequest(
        requested_worker_id="agy_flash",
        provider="agy",
        model="gemini-3.6-flash-high",
        role="fast_bounded_implementation",
        autonomy="L2",
        context="nexus_bounded",
        mutation_requested=False,
        explicit_experiment_authorization=False,
        route_authorized=True,
        provided_controls=["task_card", "allowed_files"],  # type: ignore[arg-type]
    )

    assert req.schema == "nexus.workforce_admission_request.v1"
    assert isinstance(req.provided_controls, tuple)
    assert req.provided_controls == ("task_card", "allowed_files")

    # Immutability
    with pytest.raises(AttributeError):
        req.route_authorized = False  # type: ignore[misc]

    d = req.to_dict()
    assert d["schema"] == "nexus.workforce_admission_request.v1"
    assert d["requested_worker_id"] == "agy_flash"
    assert d["provided_controls"] == ["task_card", "allowed_files"]

    roundtrip = WorkforceAdmissionRequest.from_dict(d)
    assert roundtrip == req


def test_workforce_worker_serialization_and_immutability() -> None:
    worker = WorkforceWorker(
        worker_id="agy_flash",
        provider="agy",
        model="gemini-3.6-flash-high",
        state="PROVEN_MAINCHAIN",
        availability="AVAILABLE",
        roles=["fast_bounded_implementation", "focused_verification"],  # type: ignore[arg-type]
        autonomy="L2",
        preferred_context="nexus_bounded",
        benchmark_ref="agy_flash",
        requires=["task_card", "allowed_files"],  # type: ignore[arg-type]
        forbidden_claims=["architecture_authority"],  # type: ignore[arg-type]
    )

    assert isinstance(worker.roles, tuple)
    assert isinstance(worker.requires, tuple)

    with pytest.raises(AttributeError):
        worker.state = "QUARANTINED"  # type: ignore[misc]

    d = worker.to_dict()
    assert d["worker_id"] == "agy_flash"
    assert d["roles"] == ["fast_bounded_implementation", "focused_verification"]
    assert d["requires"] == ["task_card", "allowed_files"]


def test_workforce_admission_decision_schema_and_serialization() -> None:
    dec = WorkforceAdmissionDecision(
        schema="nexus.workforce_admission_decision.v1",
        decision=AdmissionDecision.ALLOW,
        resolved_worker_id="agy_flash",
        resolved_provider="agy",
        resolved_model="gemini-3.6-flash-high",
        requested_role="fast_bounded_implementation",
        admitted_role="fast_bounded_implementation",
        requested_autonomy="L2",
        admitted_autonomy="L2",
        requested_context="nexus_bounded",
        admitted_context="nexus_bounded",
        autonomy_ceiling="L2",
        decision_reasons=["All constraints passed"],  # type: ignore[arg-type]
        required_controls=["task_card"],  # type: ignore[arg-type]
        missing_controls=[],  # type: ignore[arg-type]
        policy_schema="nexus.model_workforce.v1",
        policy_status="current",
        policy_last_verified="2026-07-29",
        policy_hash="abc123hash",
        route_authority="CapabilityPlanner",
        freshness_evidence={"last_verified": "2026-07-29", "verified_age_days": 0, "is_future": False},
    )

    assert dec.schema == "nexus.workforce_admission_decision.v1"
    d = dec.to_dict()
    assert d["schema"] == "nexus.workforce_admission_decision.v1"
    assert d["decision"] == "ALLOW"
    assert d["resolved_worker_id"] == "agy_flash"
    assert d["freshness_evidence"]["is_future"] is False


def test_gb025_tampered_identity_does_not_change_admission_vocabulary() -> None:
    payload = WorkforceAdmissionDecision(decision=AdmissionDecision.BLOCK).to_dict()
    payload["decision"] = "allow"
    with pytest.raises(ValueError):
        WorkforceAdmissionDecision(decision=payload["decision"])  # type: ignore[arg-type]
