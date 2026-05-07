from nexus.core.learning_evidence import LearningEvidenceBuilder
from nexus.core.learning_governance import LearningDecision
from nexus.core.learning_scorer import LearningScorer
from nexus.core.state_contracts import NexusState, StepRecord
from datetime import datetime


def _step(phase: str) -> StepRecord:
    now = datetime.now()
    return StepRecord(
        phase=phase,
        step_id=f"{phase}-1",
        status="completed",
        started_at=now,
        ended_at=now,
        metadata={},
    )


def _allow_short_trajectory(state: NexusState) -> None:
    state.metadata["governance_profile"] = {"min_evolution_steps": 1}


def test_learning_scorer_records_episode_signals():
    state = NexusState(task_id="learn-1")
    state.steps_history = [_step("P"), _step("X"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.policy_hit_ids = ["POL-1", "POL-2"]
    state.retry_count = 0
    state.metadata["pipeline_success"] = True
    _allow_short_trajectory(state)

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["episode_count"] == 1
    assert state.metadata["pattern_reuse_rate"] >= 85.0
    assert state.metadata["lesson_quality"] >= 88.0
    assert state.metadata["next_run_hit_rate"] >= 90.0
    assert state.metadata["learning_success_window"] == [1]


def test_learning_scorer_updates_rolling_window():
    state = NexusState(task_id="learn-2")
    state.steps_history = [_step("P"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.retry_count = 2
    state.metadata["learning_success_window"] = [1] * 9

    state.metadata["pipeline_success"] = False
    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    window = state.metadata["learning_success_window"]
    assert len(window) == 10
    assert window[-1] == 0
    assert state.metadata["episode_count"] == 1


def test_learning_scorer_respects_sir_veto_freeze():
    state = NexusState(task_id="learn-3")
    state.steps_history = [_step("P"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["pipeline_success"] = True
    state.metadata["sir_veto_learning"] = True

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is True
    assert "sir_veto" in state.metadata["learning_freeze_reasons"]
    assert "pattern_reuse_rate" not in state.metadata


def test_learning_scorer_triggers_canary_on_memory_drop():
    state = NexusState(task_id="learn-4")
    state.steps_history = [_step("P"), _step("X"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["pipeline_success"] = True
    state.metadata["memory_health_baseline"] = 100.0
    state.metadata["memory_health_current"] = 85.0

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is True
    assert state.metadata["canary_alert"] is True
    assert "memory_health_drop" in state.metadata["learning_freeze_reasons"]


def test_learning_scorer_uses_reviewer_ci_negative_feedback_to_freeze():
    state = NexusState(task_id="learn-5")
    state.steps_history = [_step("P"), _step("D"), _step("R")]
    state.metadata["last_review_status"] = "REJECTED"
    state.metadata["pipeline_success"] = False
    state.health_metrics.test_pass_rate = 0.0

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is True
    assert "curiosity_negative" in state.metadata["learning_freeze_reasons"]
    assert state.metadata["curiosity_feedback_reward"] <= -35.0


def test_learning_scorer_uses_reviewer_ci_positive_feedback_to_keep_learning():
    state = NexusState(task_id="learn-6")
    state.steps_history = [_step("P")]
    state.metadata["last_review_status"] = "APPROVED"
    state.metadata["pipeline_success"] = True
    state.health_metrics.test_pass_rate = 1.0
    _allow_short_trajectory(state)

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is False
    assert state.metadata["curiosity_feedback_reward"] >= 30.0
    assert state.metadata["pattern_reuse_rate"] >= 60.0


def test_learning_scorer_ignores_conflicting_reviewer_signal_when_pipeline_success_true():
    state = NexusState(task_id="learn-7")
    state.steps_history = [_step("P"), _step("X"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["last_review_status"] = "REJECTED"
    state.metadata["pipeline_success"] = True
    _allow_short_trajectory(state)

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is False
    assert state.metadata["curiosity_feedback_reward"] >= 10.0
    assert state.metadata["lesson_quality"] >= 85.0


def test_learning_scorer_freezes_when_success_patch_has_no_physical_proof():
    state = NexusState(task_id="learn-8")
    state.steps_history = [_step("P"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["pipeline_success"] = True
    state.metadata["last_review_status"] = "APPROVED"
    state.metadata["last_patch_generated"] = True
    state.metadata["last_patch_apply_success"] = True
    state.metadata["last_proof_type"] = ""
    state.metadata["last_proof_value"] = ""

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is True
    assert "missing_physical_proof_evidence" in state.metadata["learning_freeze_reasons"]
    assert "pattern_reuse_rate" not in state.metadata


def test_learning_scorer_allows_success_patch_with_valid_proof():
    state = NexusState(task_id="learn-9")
    state.steps_history = [_step("P"), _step("X"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["pipeline_success"] = True
    state.metadata["last_review_status"] = "APPROVED"
    state.metadata["last_patch_generated"] = True
    state.metadata["last_patch_apply_success"] = True
    state.metadata["last_proof_type"] = "git_diff_checksum"
    state.metadata["last_proof_value"] = "deadbeef"
    _allow_short_trajectory(state)

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence)

    assert state.metadata["learning_frozen"] is False
    assert state.metadata["pattern_reuse_rate"] >= 70.0


def test_learning_scorer_accepts_injected_governance_evaluator():
    class FakeGovernanceEvaluator:
        calls = 0

        @classmethod
        def evaluate(cls, state: NexusState, _evidence):
            cls.calls += 1
            state.metadata["learning_action"] = "fake_continue"
            return LearningDecision(freeze_learning=False, curiosity_score=77.0, reasons=["fake"])

    state = NexusState(task_id="learn-injected-governance")
    state.steps_history = [_step("P"), _step("D"), _step("R"), _step("A"), _step("C")]
    state.metadata["pipeline_success"] = True

    evidence = LearningEvidenceBuilder.build(state)
    LearningScorer.apply(state, evidence, governance_evaluator=FakeGovernanceEvaluator)

    assert FakeGovernanceEvaluator.calls == 1
    assert state.metadata["learning_action"] == "fake_continue"
    assert state.metadata["pattern_reuse_rate"] > 0.0


def test_learning_governance_records_event_emit_failure(monkeypatch):
    from nexus.core.learning_governance import LearningGovernance

    def fail_publish(*_args, **_kwargs):
        raise RuntimeError("event bus unavailable")

    monkeypatch.setattr(
        "nexus.core.learning_governance.NexusEventBus.publish",
        fail_publish,
    )
    state = NexusState(task_id="learn-event-failure")
    state.steps_history = [_step("P"), _step("D"), _step("R")]
    state.metadata["pipeline_success"] = False

    evidence = LearningEvidenceBuilder.build(state)
    decision = LearningGovernance.evaluate(state, evidence)

    assert isinstance(decision.freeze_learning, bool)
    assert state.metadata["learning_decision_event_emitted"] is False
    assert state.metadata["learning_decision_event_error"] == "event bus unavailable"


def test_learning_governance_event_emits_nexus_and_model_actions(monkeypatch):
    from nexus.core.learning_governance import LearningGovernance

    captured = {}

    def capture_publish(event_type, payload):
        captured["event_type"] = event_type
        captured.update(payload)

    monkeypatch.setattr(
        "nexus.core.learning_governance.NexusEventBus.publish",
        capture_publish,
    )
    state = NexusState(task_id="learn-event-actions")
    state.metadata["pipeline_success"] = True
    state.metadata["nexus_learning_action"] = "PROMOTE_NEXUS"
    state.metadata["model_learning_action"] = "EXPORT_MODEL"
    _allow_short_trajectory(state)

    evidence = LearningEvidenceBuilder.build(state)
    LearningGovernance.evaluate(state, evidence)

    assert state.metadata["learning_decision_event_emitted"] is True
    assert captured["event_type"] == "learning_decision"
    assert captured["nexus_action"] == "PROMOTE_NEXUS"
    assert captured["model_action"] == "EXPORT_MODEL"
