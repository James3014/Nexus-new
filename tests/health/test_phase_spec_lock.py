from datetime import datetime

from nexus.core.state_contracts import NexusState, PhaseMetric, StepRecord
from nexus.health.policy import HealthTriggerPolicy
from nexus.health.scoring import HealthScorer
from nexus.health.signals import HealthSignalCollector


def test_signal_collector_populates_missing_spec_metrics():
    state = NexusState(task_id="spec-lock-signals")
    state.metadata["false_positive_rate"] = 17.0
    state.metadata["next_run_hit_rate"] = 62.0
    state.steps_history = [
        StepRecord(
            phase="X",
            step_id="X-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"findings": ["doc"], "status": "SUCCESS", "tokens_used": 400},
        ),
        StepRecord(
            phase="D",
            step_id="D-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"pack_keys": ["root", "trace"]},
        ),
    ]
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert "false_positive_rate" in collected["D"]
    assert collected["D"]["false_positive_rate"] == 17.0
    assert "next_run_hit_rate" in collected["C"]
    assert collected["C"]["next_run_hit_rate"] == 62.0
    assert "research_latency" in collected["X"]


def test_signal_collector_accepts_normalized_and_legacy_risk_scales():
    fractional = NexusState(task_id="health-risk-fractional")
    fractional.steps_history = [
        StepRecord(
            phase="P",
            step_id="P-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"prediction": {"intent_pass": True, "risk_score": 0.25}},
        ),
    ]
    fractional.phase_metrics.setdefault("P", PhaseMetric(signals={}))

    legacy = NexusState(task_id="health-risk-legacy")
    legacy.steps_history = [
        StepRecord(
            phase="P",
            step_id="P-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"prediction": {"intent_pass": True, "risk_score": 25}},
        ),
    ]
    legacy.phase_metrics.setdefault("P", PhaseMetric(signals={}))

    normalized = NexusState(task_id="health-risk-normalized")
    normalized.steps_history = [
        StepRecord(
            phase="P",
            step_id="P-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"prediction": {"intent_pass": True, "risk_score": 90, "risk_score_0_1": 0.25}},
        ),
    ]
    normalized.phase_metrics.setdefault("P", PhaseMetric(signals={}))

    assert HealthSignalCollector.collect(fractional)["P"]["dependency_validity"] == 75.0
    assert HealthSignalCollector.collect(legacy)["P"]["dependency_validity"] == 75.0
    assert HealthSignalCollector.collect(normalized)["P"]["dependency_validity"] == 75.0


def test_scorer_accepts_research_latency_norm_alias():
    state = NexusState(task_id="spec-lock-x-alias")
    state.phase_metrics["X"].signals = {
        "evidence_quality": 90.0,
        "source_relevance": 85.0,
        "research_latency_norm": 30.0,
    }

    snapshot = HealthScorer.apply_snapshot(state)
    assert snapshot.phase_scores["X"].completeness == 1.0
    assert snapshot.phase_scores["X"].score > 0.0


def test_trigger_policy_tracks_spec_thresholds_with_streaks():
    state = NexusState(task_id="spec-lock-triggers")
    state.learning_velocity = -0.2
    state.metadata["learning_velocity_non_positive_streak"] = 2
    state.metadata["phase_health_below_85_streak"] = {"R": 1}

    state.phase_metrics["R"].signals = {
        "fix_success_rate": 10.0,
        "retry_penalty": 90.0,
        "scope_drift": 80.0,
    }
    state.phase_metrics["A"].signals = {
        "regression_pass_rate": 0.0,
        "side_effect_score": 20.0,
        "coverage_signal": 30.0,
    }
    state.health_metrics.last_check_at = datetime.now()
    state.health_metrics.test_pass_rate = 0.0
    state.health_metrics.error_rate = 1.0
    state.health_metrics.token_efficiency = 0.1
    state.metadata["last_review_status"] = "REJECTED"

    snapshot = HealthScorer.apply_snapshot(state)
    triggers = HealthTriggerPolicy.evaluate_and_record(state, snapshot)
    codes = {trigger.code for trigger in triggers}

    assert "phase_health_low" in codes
    assert "pipeline_health_low" in codes
    assert "audit_regression_fail" in codes
    assert "learning_velocity_stalled" in codes


def test_planner_route_for_audit_failure_is_explicit(tmp_path):
    from nexus.health.diagnostics import HealthDiagnosis
    from nexus.health.planner import RepairPlanner

    plan = RepairPlanner(tmp_path).build_plan(
        HealthDiagnosis(kind="audit_failure", summary="audit rejected", target_phase="A")
    )
    assert plan.phase_route == ["R", "A", "D", "R", "A"]
    route_ids = [a.id for a in plan.actions if a.id.startswith("auto.repair.route.")]
    assert route_ids[0] == "auto.repair.route.r"


def test_c_signal_prefers_stronger_metadata_and_approved_review():
    state = NexusState(task_id="spec-lock-c-merge")
    state.metadata["pattern_reuse_rate"] = 70.0
    state.metadata["lesson_quality"] = 82.0
    state.metadata["last_review_status"] = "APPROVED"
    state.policy_hit_ids = ["P1", "P2", "P3"]  # density score < metadata reuse score
    state.steps_history = [
        StepRecord(
            phase="C",
            step_id="C-1",
            status="completed",
            started_at=datetime.now(),
            metadata={},
        )
    ]
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert collected["C"]["pattern_reuse_rate"] == 70.0
    assert collected["C"]["lesson_quality"] >= 82.0


def test_x_signal_uses_gentle_token_proxy_for_latency():
    state = NexusState(task_id="spec-lock-x-latency")
    state.steps_history = [
        StepRecord(
            phase="X",
            step_id="X-1",
            status="completed",
            started_at=datetime.now(),
            metadata={"findings": ["e1"], "status": "SUCCESS", "tokens_used": 4000},
        )
    ]
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    # 4000 / 200 => 20 latency_norm (was 80 with older scaling)
    assert collected["X"]["research_latency"] == 20.0
    assert collected["X"]["evidence_quality"] >= 85.0
    assert collected["X"]["source_relevance"] >= 82.0


def test_r_signal_backfills_scope_drift_for_completeness():
    state = NexusState(task_id="spec-lock-r-scope")
    state.metadata["last_review_status"] = "APPROVED"
    state.retry_count = 1
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert "scope_drift" in collected["R"]
    assert collected["R"]["scope_drift"] > 0.0
    assert collected["R"]["retry_penalty"] == 20.0


def test_r_signal_sets_zero_retry_penalty_on_first_pass():
    state = NexusState(task_id="spec-lock-r-retry-zero")
    state.metadata["last_review_status"] = "APPROVED"
    state.retry_count = 0
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert collected["R"]["retry_penalty"] == 0.0


def test_a_signal_backfills_coverage_when_missing():
    state = NexusState(task_id="spec-lock-a-coverage")
    state.metadata["last_review_status"] = "APPROVED"
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert collected["A"]["coverage_signal"] == 80.0
    assert collected["A"]["regression_pass_rate"] == 100.0


def test_d_signal_prefers_diagnosis_fidelity_when_present():
    state = NexusState(task_id="spec-lock-d-fidelity")
    state.metadata["diagnosis_fidelity"] = 90.0
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert collected["D"]["root_cause_confidence"] >= 90.0
    assert collected["D"]["diagnosis_precision"] >= 90.0
    assert collected["D"]["false_positive_rate"] <= 10.0


def test_c_signal_uses_sandbox_hit_rate_to_raise_next_run_projection():
    state = NexusState(task_id="spec-lock-c-sandbox")
    state.metadata["sandbox_hit_rate"] = 1.0
    state.metadata["next_run_hit_rate"] = 50.0
    for phase in ("P", "X", "D", "R", "A", "C"):
        state.phase_metrics.setdefault(phase, PhaseMetric(signals={}))

    collected = HealthSignalCollector.collect(state)
    assert collected["C"]["next_run_hit_rate"] >= 88.0
