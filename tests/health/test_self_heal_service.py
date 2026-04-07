from pathlib import Path
from datetime import datetime
import json

from nexus.core.state_contracts import NexusState, HealthMetrics
from nexus.health.models import HealthDiagnosis, HealthSnapshot, HealthTrigger, PhaseScore, RepairExecutionResult
from nexus.health.service import SelfHealService
from nexus.services.memory import FaultLesson
from nexus.health.scoring import HealthScorer


class _ExecutorStub:
    def __init__(self, result: RepairExecutionResult):
        self.result = result
        self.plans = []

    def execute(self, plan):
        self.plans.append(plan)
        return self.result


def _critical_snapshot(score: float = 45.0) -> HealthSnapshot:
    return HealthSnapshot(
        overall_score=score,
        outcome_score=score,
        phase_average=score,
        confidence=0.9,
        status="CRITICAL",
        phase_scores={"A": PhaseScore("A", score, 1.0, "CRITICAL", {"regression_pass_rate": 0.0})},
        reasons=["review_status:rejected"],
    )


def _healthy_snapshot(score: float = 93.0) -> HealthSnapshot:
    return HealthSnapshot(
        overall_score=score,
        outcome_score=score,
        phase_average=score,
        confidence=0.95,
        status="HEALTHY",
        phase_scores={"A": PhaseScore("A", score, 1.0, "HEALTHY", {"regression_pass_rate": 100.0})},
        reasons=[],
    )


def test_self_heal_service_records_repaired_cycle(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-pass")
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="inject_only",
            success=True,
            injected_tasks=["auto.repair.phase.a"],
            task_runner_invoked=True,
            return_codes={"task_runner": 0},
            notes=["task_runner_rc:0"],
        )
    )

    snapshots = [_critical_snapshot(), _healthy_snapshot()]

    def fake_apply(_state):
        snap = snapshots.pop(0)
        _state.health_score = snap.overall_score
        _state.pipeline_health = snap.phase_average or snap.overall_score
        _state.metadata["health_snapshot"] = {
            "overall_score": snap.overall_score,
            "status": snap.status,
            "reasons": list(snap.reasons),
        }
        return snap

    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", fake_apply)
    monkeypatch.setattr(
        "nexus.health.service.HealthDiagnostics.diagnose",
        lambda _state, snap: HealthDiagnosis(
            kind="audit_failure" if snap.status != "HEALTHY" else "healthy",
            summary="audit rejected" if snap.status != "HEALTHY" else "healthy",
            target_phase="A" if snap.status != "HEALTHY" else None,
        ),
    )

    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)

    assert cycle.status == "repaired"
    assert state.metadata["self_heal_cycle"]["status"] == "repaired"
    assert state.metadata["auto_repair_last_result"]["cycle_status"] == "repaired"
    assert "self_heal_route_phase_weights" in state.metadata
    assert state.metadata["self_heal_route_phase_weights"]["R"] > 0
    assert state.metadata["self_heal_route_policy_sync"] == "ok"
    policy_path = tmp_path / ".nexus" / "knowledge" / "policy_memory.jsonl"
    assert policy_path.exists()
    rows = [
        json.loads(line)
        for line in policy_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(row.get("rule_id") == "ROUTE-WEIGHT-R" for row in rows)
    assert executor.plans


def test_self_heal_service_records_failed_execution(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-fail")
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="safe_execute",
            success=False,
            executed_actions=["auto.repair.environment"],
            return_codes={"auto.repair.environment": 1},
            notes=["executed:auto.repair.environment:rc=1"],
        )
    )

    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", lambda _state: _critical_snapshot())
    monkeypatch.setattr(
        "nexus.health.service.HealthDiagnostics.diagnose",
        lambda _state, _snap: HealthDiagnosis(kind="environment_failure", summary="runtime degraded"),
    )

    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)

    assert cycle.status == "failed"
    assert state.metadata["self_heal_cycle"]["execution"]["success"] is False
    assert state.metadata["auto_repair_last_result"]["cycle_status"] == "failed"


def test_self_heal_service_ingests_benchmark_evidence(monkeypatch, tmp_path):
    state = NexusState(
        task_id="heal-evidence",
        health_metrics=HealthMetrics(last_check_at=datetime.now(), status="WARNING"),
        token_capture_status="unknown",
    )
    csv_path = tmp_path / "ci_benchmark_autorepair.csv"
    csv_path.write_text(
        "task_id,status,tokens,token_raw_model,token_fallback_est,token_system_overhead,token_source_x,token_source_r,token_capture_status,phase_path,review_status,duration,health,drift,lowest_phase_health,policy_hit,learning_velocity\n"
        "OFF-001,PASS,100,0,0,100,0,100,internal,P -> D -> R -> A -> C,APPROVED,1.0,93.33,0.0,75.0,,0.0\n",
        encoding="utf-8",
    )
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="safe_execute",
            success=True,
            executed_actions=["auto.repair.evidence"],
            return_codes={"auto.repair.evidence": 0},
            notes=["executed:auto.repair.evidence:rc=0"],
        )
    )

    original_apply = HealthScorer.apply_snapshot

    def fake_apply_after(s):
        s.metadata.update({"thinking_depth_score": 1.0, "plan_density_score": 1.0})
        return original_apply(s)

    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", fake_apply_after)
    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)

    assert cycle.status == "repaired"
    assert cycle.after.overall_score >= 90.0
    assert state.token_capture_status == "internal"
    assert state.metadata["last_review_status"] == "APPROVED"


def test_self_heal_service_executes_policy_actions_even_when_healthy(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-policy-only")
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="safe_execute",
            success=True,
            executed_actions=["auto.optimize.learning"],
            return_codes={"auto.optimize.learning": 0},
            notes=["executed:auto.optimize.learning:rc=0"],
        )
    )
    snapshots = [_healthy_snapshot(92.0), _healthy_snapshot(93.0)]

    monkeypatch.setattr(
        "nexus.health.service.HealthScorer.apply_snapshot",
        lambda _state: snapshots.pop(0),
    )
    monkeypatch.setattr(
        "nexus.health.service.HealthDiagnostics.diagnose",
        lambda _state, _snap: HealthDiagnosis(kind="healthy", summary="healthy"),
    )
    monkeypatch.setattr(
        "nexus.health.service.HealthTriggerPolicy.evaluate_and_record",
        lambda _state, _snap, *args: [
            HealthTrigger(
                code="learning_velocity_stalled",
                reason="velocity stalled",
                severity="MEDIUM",
            )
        ],
    )

    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)
    assert cycle.status == "repaired"
    assert "auto.optimize.learning" in cycle.execution.executed_actions


def test_self_heal_service_preserves_phase_route_when_merging_policy_actions(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-route-preserve")
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="inject_only",
            success=True,
            executed_actions=["auto.repair.route.r"],
            injected_tasks=["auto.repair.route.r"],
            return_codes={"task_runner": 0},
            notes=["task_runner_rc:0"],
            task_runner_invoked=True,
        )
    )
    snapshots = [_critical_snapshot(60.0), _critical_snapshot(60.0)]

    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", lambda _state: snapshots.pop(0))
    monkeypatch.setattr(
        "nexus.health.service.HealthDiagnostics.diagnose",
        lambda _state, _snap: HealthDiagnosis(kind="audit_failure", summary="audit rejected repair", target_phase="A"),
    )
    monkeypatch.setattr(
        "nexus.health.service.HealthTriggerPolicy.evaluate_and_record",
        lambda _state, _snap, *args: [
            HealthTrigger(code="pipeline_health_low", reason="pipeline below 88", severity="HIGH")
        ],
    )

    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)
    assert cycle.plan.phase_route == ["R", "A", "D", "R", "A"]


def test_self_heal_service_attaches_fault_signature_and_fidelity(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-signature")
    state.metadata["last_error_text"] = """
Traceback (most recent call last):
  File "nexus/core/commander.py", line 42, in <module>
    import non_existent_pkg
ModuleNotFoundError: No module named 'non_existent_pkg'
"""
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="safe_execute",
            success=True,
            executed_actions=["auto.repair.environment"],
            return_codes={"auto.repair.environment": 0},
            notes=["executed:auto.repair.environment:rc=0"],
            telemetry={"sandbox_hit_rate": 1.0},
        )
    )
    snapshots = [_critical_snapshot(45.0), _healthy_snapshot(91.0)]
    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", lambda _state: snapshots.pop(0))
    monkeypatch.setattr(
        "nexus.health.service.HealthTriggerPolicy.evaluate_and_record",
        lambda _state, _snap, *args: [],
    )

    cycle = SelfHealService(Path(tmp_path), executor=executor).run_cycle(state)
    assert cycle.diagnosis.kind == "environment_failure"
    assert state.metadata.get("fault_hash")
    assert state.metadata.get("diagnosis_fidelity", 0.0) > 0.0
    assert state.metadata.get("sandbox_hit_rate") == 1.0


def test_self_heal_service_injects_fault_lessons_and_records_new_one(monkeypatch, tmp_path):
    state = NexusState(task_id="heal-fault-lessons")
    state.metadata["last_error_text"] = """
Traceback (most recent call last):
  File "nexus/core/commander.py", line 42, in <module>
    import non_existent_pkg
ModuleNotFoundError: No module named 'non_existent_pkg'
"""
    executor = _ExecutorStub(
        RepairExecutionResult(
            disposition="safe_execute",
            success=True,
            executed_actions=["auto.repair.environment"],
            return_codes={"auto.repair.environment": 0},
            notes=["executed:auto.repair.environment:rc=0"],
        )
    )
    snapshots = [_critical_snapshot(45.0), _healthy_snapshot(92.0)]
    monkeypatch.setattr("nexus.health.service.HealthScorer.apply_snapshot", lambda _state: snapshots.pop(0))
    monkeypatch.setattr(
        "nexus.health.service.HealthTriggerPolicy.evaluate_and_record",
        lambda _state, _snap, *args: [],
    )

    service = SelfHealService(Path(tmp_path), executor=executor)
    service.memory_service.record_fault_lesson(FaultLesson(
        fault_hash="preseed",
        error_type="ModuleNotFoundError",
        diagnosis_kind="environment_failure",
        lesson="Preseed lesson",
        repair_patch="auto.repair.environment",
        audit_pass_rate=1.0,
        metadata={},
    ))

    # Run once to generate real hash and persist a lesson.
    cycle = service.run_cycle(state)
    assert cycle.status in {"repaired", "degraded", "healthy", "failed"}
    fault_hash = state.metadata.get("fault_hash")
    assert fault_hash
    hits = service.memory_service.lookup_fault_lessons(fault_hash, limit=5)
    assert hits
