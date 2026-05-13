from __future__ import annotations

import json

import pytest

from nexus.contracts.learning_experience import build_learning_experience
from nexus.contracts.s2t_policy import (
    S2TAdoptionDecision,
    S2TAdoptionMetrics,
    S2TCandidate,
    S2TSelector,
    S2TStrictGate,
)
from nexus.contracts.s2t_trace import (
    S2TDecisionSpan,
    S2TEpisodeTrace,
    S2TTraceEvent,
    S2TTraceWriter,
    export_agent_lightning_preferences,
    export_model_training_v2,
    export_model_training_v3,
    redact_s2t_event,
)


def _candidate(
    candidate_id: str,
    *,
    selector_score: float,
    verifier_result: str = "pass",
    risk_flags: list[str] | None = None,
) -> S2TCandidate:
    return S2TCandidate(
        candidate_id=candidate_id,
        source="repair_pass",
        content_ref=f".nexus/reports/s2t/candidates/{candidate_id}.json",
        claimed_outcome="patch passes targeted tests",
        static_score=0.5,
        selector_score=selector_score,
        verifier_result=verifier_result,
        evidence_refs=["tests/contracts/test_s2t_contracts.py"] if verifier_result == "pass" else [],
        risk_flags=risk_flags or [],
    )


def test_s2t_trace_event_round_trips_and_rejects_success_without_verifier() -> None:
    event = S2TTraceEvent(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[_candidate("A", selector_score=0.42)],
        selected_candidate_id="A",
        selection_reason_codes=["has_empirical_test_evidence"],
        verifier_name="pytest",
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/pytest.json",
        semantic_verified=True,
        delivery_gate="pass",
    )

    restored = S2TTraceEvent.from_dict(event.to_dict())

    assert restored == event
    assert restored.schema_version == "s2t.v1"

    payload = event.to_dict()
    payload["unexpected"] = "schema drift"
    with pytest.raises(ValueError, match="unknown S2TTraceEvent fields"):
        S2TTraceEvent.from_dict(payload)

    with pytest.raises(ValueError, match="semantic_verified requires verifier_result=pass"):
        S2TTraceEvent(
            task_id="task-1",
            run_id="run-1",
            model="gemini-3-flash-preview",
            mode="strict",
            phase="C",
            risk_tier="public_claim",
            candidate_set_id="candset-1",
            candidates=[_candidate("A", selector_score=0.7, verifier_result="fail")],
            selected_candidate_id="A",
            verifier_result="fail",
            semantic_verified=True,
        )


def test_s2t_episode_trace_serializes_decision_spans() -> None:
    span = S2TDecisionSpan(
        node="candidate",
        phase="R",
        candidate_set_id="candset-1",
        selected_candidate_id="AB",
        gate_passed=True,
        verifier_result="pass",
        reason_codes=["has_empirical_test_evidence"],
        reward=1.0,
    )
    episode = S2TEpisodeTrace(
        episode_id="episode-1",
        task_id="task-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        spans=[span],
        cost={"model_calls": 3},
    )

    payload = episode.to_dict()

    assert payload["schema_version"] == "s2t_episode.v1"
    assert payload["spans"][0]["selected_candidate_id"] == "AB"
    assert payload["spans"][0]["reward"] == 1.0
    assert payload["cost"]["model_calls"] == 3

    with pytest.raises(ValueError, match="verifier_result must be pass"):
        S2TDecisionSpan(
            node="candidate",
            phase="R",
            candidate_set_id="candset-1",
            selected_candidate_id="AB",
            gate_passed=True,
            verifier_result="maybe",
        )


def test_s2t_trace_writer_appends_jsonl_and_redacts_training_export(tmp_path) -> None:
    event = S2TTraceEvent(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[_candidate("A", selector_score=0.7)],
        selected_candidate_id="A",
        verifier_result="pass",
        secret_values={"api_token": "secret-token"},
        private_paths=["/Users/jameschen/Workspace/nexus/private.txt"],
    )
    trace_path = tmp_path / "s2t.jsonl"
    S2TTraceWriter(trace_path).append(event)

    rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]

    assert rows[0]["schema_version"] == "s2t.v1"
    redacted = redact_s2t_event(event)
    assert redacted["secret_values"] == {}
    assert redacted["private_paths"] == ["<redacted-path>"]


def test_s2t_selector_is_fail_closed_and_prefers_verified_evidence() -> None:
    decision = S2TSelector().select(
        [
            _candidate("A", selector_score=0.95, verifier_result="fail"),
            _candidate("B", selector_score=0.70, verifier_result="pass"),
        ]
    )

    assert decision.selected_candidate_id == "B"
    assert "verifier_failed_candidate_excluded" in decision.reason_codes

    no_winner = S2TSelector().select([_candidate("A", selector_score=0.95, verifier_result="fail")])
    assert no_winner.selected_candidate_id == "NO_VERIFIED_CANDIDATE"
    assert no_winner.gate_passed is False


def test_s2t_strict_gate_blocks_public_claim_without_gate_evidence() -> None:
    gate = S2TStrictGate()
    blocked = gate.evaluate(
        risk_tier="public_claim",
        decision=S2TSelector().select([_candidate("A", selector_score=0.8)]),
        verifier_result="pass",
        verifier_evidence_ref="",
    )

    assert blocked.gate_passed is False
    assert blocked.failure_reason == "public_claim_requires_gate_evidence"

    passed = gate.evaluate(
        risk_tier="public_claim",
        decision=S2TSelector().select([_candidate("A", selector_score=0.8)]),
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/claim_gate.json",
    )
    assert passed.gate_passed is True


def test_s2t_agent_lightning_export_emits_preference_pairs() -> None:
    event = S2TTraceEvent(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[
            _candidate("A", selector_score=0.95, verifier_result="fail"),
            _candidate("B", selector_score=0.70, verifier_result="pass"),
        ],
        selected_candidate_id="B",
        verifier_result="pass",
    )

    exported = export_agent_lightning_preferences([event])

    assert exported["format"] == "agent-lightning-preferences-v1"
    assert exported["pairs"][0]["chosen_candidate_id"] == "B"
    assert exported["pairs"][0]["rejected_candidate_id"] == "A"


def test_model_training_export_v2_preserves_v1_compat_and_redaction() -> None:
    event = S2TTraceEvent(
        task_id="task-1",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[
            _candidate("A", selector_score=0.95, verifier_result="fail"),
            _candidate("B", selector_score=0.70, verifier_result="pass"),
        ],
        selected_candidate_id="B",
        verifier_result="pass",
        secret_values={"token": "secret"},
        private_paths=["/Users/jameschen/private.txt"],
    )

    exported = export_model_training_v2([event])

    assert exported["schema_version"] == "nexus_model_training_export.v2"
    assert exported["compat"]["agent_lightning_preferences_v1"]["format"] == "agent-lightning-preferences-v1"
    assert exported["compat"]["agent_lightning_preferences_v1"]["pair_count"] == 1
    assert exported["redacted_source_rows"][0]["secret_values"] == {}
    assert exported["redacted_source_rows"][0]["private_paths"] == ["<redacted-path>"]


def test_model_training_export_v2_applies_autodata_quality_gate() -> None:
    event = S2TTraceEvent(
        task_id="task-2",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[
            _candidate("A", selector_score=0.95, verifier_result="fail"),
            _candidate("B", selector_score=0.70, verifier_result="pass"),
        ],
        selected_candidate_id="B",
        verifier_result="pass",
    )
    experience = build_learning_experience(
        task_id="task-2",
        task_type="bug",
        usage_trace={
            "phase_trace": {"S": "start", "P": "plan", "X": "context", "D": "design", "R": "repair", "A": "audit", "C": "close"},
            "capabilities": {
                "artifact_gate_passed": True,
                "artifact_refs": ["artifact:task-2"],
                "claim_verified": True,
                "delivery_gate_passed": True,
                "delivery_refs": ["delivery:task-2"],
            },
            "s2t": {"trace_path": ".nexus/reports/s2t/task-2.jsonl"},
        },
        capability_receipts=[
            {
                "name": "autoreason",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_refs": ["autoreason:winner"],
            }
        ],
    )

    exported = export_model_training_v2(
        [event],
        experiences=[experience],
        quality_rows=[
            {
                "task_id": "task-2",
                "eligible_for_training": False,
                "reasons": ["low_step_trajectory"],
                "trajectory_step_count": 2,
                "information_density": 0.25,
            }
        ],
    )

    projection = exported["experience_rows"][0]["projection"]
    assert exported["compat"]["agent_lightning_preferences_v1"]["pair_count"] == 1
    assert exported["quality_gate"]["autodata_attached"] is True
    assert exported["quality_gate"]["training_eligible_count"] == 0
    assert projection["training_eligible"] is False
    assert projection["targets"] == ["hard_negative"]
    assert projection["autodata_gate"]["trajectory_steps"] == 2


def test_model_training_export_v3_emits_preference_reward_and_gated_experience_rows() -> None:
    event = S2TTraceEvent(
        task_id="task-3",
        run_id="run-1",
        model="gemini-3-flash-preview",
        mode="shadow",
        phase="R",
        risk_tier="high",
        candidate_set_id="candset-1",
        candidates=[
            _candidate("A", selector_score=0.95, verifier_result="fail"),
            _candidate("B", selector_score=0.70, verifier_result="pass"),
        ],
        selected_candidate_id="B",
        verifier_result="pass",
        verifier_evidence_ref=".nexus/reports/pytest.json",
        semantic_verified=True,
        delivery_gate="pass",
    )
    experience = build_learning_experience(
        task_id="task-3",
        task_type="bug",
        usage_trace={
            "phase_trace": {"S": "start", "P": "plan", "X": "context", "D": "design", "R": "repair", "A": "audit", "C": "close"},
            "capabilities": {
                "artifact_gate_passed": True,
                "claim_verified": True,
                "delivery_gate_passed": True,
            },
            "s2t": {"trace_path": ".nexus/reports/s2t/task-3.jsonl"},
        },
    )

    exported = export_model_training_v3(
        [event],
        experiences=[experience],
        quality_rows=[
            {
                "task_id": "task-3",
                "eligible_for_training": True,
                "trajectory_step_count": 12,
                "information_density": 0.8,
            }
        ],
    )

    row_types = {row["row_type"] for row in exported["training_rows"]}
    assert exported["schema_version"] == "nexus_model_training_export.v3"
    assert row_types == {"preference_pair", "reward_row", "experience_projection"}
    assert exported["summary"]["preference_pair_count"] == 1
    assert exported["summary"]["reward_row_count"] == 1
    assert exported["summary"]["training_eligible_count"] == 1


def test_s2t_adoption_gate_requires_shadow_and_heldout_lift() -> None:
    metrics = S2TAdoptionMetrics(
        eligible_rows=30,
        selector_override_verified_rate=0.72,
        original_top1_verified_rate=0.50,
        trust_mismatch_delta=0.0,
        public_claim_precision_delta=0.0,
        heldout_win_rate=0.60,
    )

    assert S2TAdoptionDecision.from_metrics(metrics).status == "strict_opt_in"

    weak = S2TAdoptionMetrics(
        eligible_rows=12,
        selector_override_verified_rate=0.72,
        original_top1_verified_rate=0.50,
        trust_mismatch_delta=0.0,
        public_claim_precision_delta=0.0,
        heldout_win_rate=0.60,
    )
    assert S2TAdoptionDecision.from_metrics(weak).status == "shadow_only"
