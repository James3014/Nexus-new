from pathlib import Path
import json
from dataclasses import dataclass
from unittest.mock import MagicMock

from nexus.core.state_contracts import HealthMetrics, NexusState


@dataclass(frozen=True)
class _FakeSnapshot:
    overall_score: float
    status: str


def _engine(tmp_path: Path) -> MagicMock:
    engine = MagicMock()
    engine.project_root = tmp_path
    engine.run_dir = tmp_path / "runs"
    engine.run_dir.mkdir(parents=True, exist_ok=True)
    engine.state_io = MagicMock()
    engine.state_io.load_global_state.return_value = NexusState(
        task_id="health-check",
        health_metrics=HealthMetrics(status="WARNING"),
    )
    return engine


def test_run_self_check_quick_uses_snapshot(monkeypatch, tmp_path):
    from nexus.health.ops import run_self_check

    engine = _engine(tmp_path)
    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda state: _FakeSnapshot(overall_score=87.5, status="HEALTHY"),
    )

    result = run_self_check(engine, level="quick")

    assert result.level == "quick"
    assert result.ok is True
    assert result.snapshot_score == 87.5
    assert result.benchmark_tasks == 0
    engine.run_benchmark.assert_not_called()


def test_run_self_check_high_requires_benchmark_health(monkeypatch, tmp_path):
    from nexus.health.ops import run_self_check

    engine = _engine(tmp_path)
    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda state: _FakeSnapshot(overall_score=88.0, status="WARNING"),
    )
    engine.run_benchmark.return_value = [
        {"task_id": "OFF-001", "status": "PASS", "health": 93.33},
    ]

    result = run_self_check(engine, level="high")

    assert result.level == "high"
    assert result.ok is True
    assert result.benchmark_tasks == 1
    assert result.benchmark_avg_health == 93.33
    engine.run_benchmark.assert_called_once()


def test_run_self_heal_dry_run_only_suggests(monkeypatch, tmp_path):
    from nexus.health.models import HealthDiagnosis, RepairAction
    from nexus.health.ops import run_self_heal

    engine = _engine(tmp_path)
    state = engine.state_io.load_global_state.return_value

    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda current: _FakeSnapshot(overall_score=42.0, status="CRITICAL"),
    )
    monkeypatch.setattr(
        "nexus.health.ops.HealthDiagnostics.diagnose",
        lambda current, snapshot: HealthDiagnosis(kind="audit_failure", summary="audit failed"),
    )
    monkeypatch.setattr(
        "nexus.health.ops.RepairPlanner.build_plan",
        lambda self, diagnosis, state=None: type(
            "Plan",
            (),
            {
                "actions": [
                    RepairAction(
                        id="auto.repair.phase.a",
                        description="repair audit",
                        run="nexus:runner --task repair_phase_A",
                        priority="HIGH",
                        disposition="inject_only",
                        reason="audit failed",
                    )
                ]
            },
        )(),
    )

    result = run_self_heal(engine, mode="dry-run")

    assert result.mode == "dry-run"
    assert result.ok is True
    assert result.cycle_status == "dry-run"
    assert result.planned_actions == ["auto.repair.phase.a"]
    engine.state_io.save_global_state.assert_not_called()
    assert "self_heal_cycle" not in state.metadata


def test_run_self_heal_strict_requires_repaired_and_90(monkeypatch, tmp_path):
    from nexus.health.ops import run_self_heal

    engine = _engine(tmp_path)
    cycle = type(
        "Cycle",
        (),
        {
            "status": "degraded",
            "after": type("After", (), {"overall_score": 72.0, "status": "WARNING"})(),
            "diagnosis": type("Diagnosis", (), {"kind": "audit_failure"})(),
            "after_diagnosis": type("Diagnosis", (), {"kind": "evidence_failure"})(),
            "notes": ["post_diagnosis:evidence_failure"],
        },
    )()
    monkeypatch.setattr(
        "nexus.health.ops.SelfHealService.run_cycle",
        lambda self, state: cycle,
    )

    result = run_self_heal(engine, mode="strict")

    assert result.mode == "strict"
    assert result.ok is False
    assert result.cycle_status == "degraded"
    engine.state_io.save_global_state.assert_called_once()


def test_run_self_heal_strict_uses_tight_executor(monkeypatch, tmp_path):
    from nexus.health.ops import (
        STRICT_SAFE_ACTION_TIMEOUT_SEC,
        STRICT_TOTAL_TIMEOUT_SEC,
        STRICT_TASK_RUNNER_TIMEOUT_SEC,
        run_self_heal,
    )

    engine = _engine(tmp_path)

    captured = {}

    class _Executor:
        def __init__(self, repo_root, safe_action_timeout_sec=0, task_runner_timeout_sec=0, total_timeout_sec=0):
            captured["safe"] = safe_action_timeout_sec
            captured["runner"] = task_runner_timeout_sec
            captured["total"] = total_timeout_sec

    class _Service:
        def __init__(self, repo_root, executor=None):
            captured["executor"] = executor

        def run_cycle(self, _state):
            return type(
                "Cycle",
                (),
                {
                    "status": "healthy",
                    "after": type("After", (), {"overall_score": 95.0, "status": "HEALTHY"})(),
                    "diagnosis": type("Diagnosis", (), {"kind": "healthy"})(),
                    "after_diagnosis": type("Diagnosis", (), {"kind": "healthy"})(),
                    "notes": [],
                    "before": type("Before", (), {"overall_score": 95.0})(),
                },
            )()

    monkeypatch.setattr("nexus.health.ops.RepairExecutor", _Executor)
    monkeypatch.setattr("nexus.health.ops.SelfHealService", _Service)

    result = run_self_heal(engine, mode="strict")
    assert result.ok is True
    assert captured["safe"] == STRICT_SAFE_ACTION_TIMEOUT_SEC
    assert captured["runner"] == STRICT_TASK_RUNNER_TIMEOUT_SEC
    assert captured["total"] == STRICT_TOTAL_TIMEOUT_SEC


def test_run_health_explain_returns_integrated_view(monkeypatch, tmp_path):
    from nexus.health.ops import run_health_explain

    engine = _engine(tmp_path)
    state = engine.state_io.load_global_state.return_value
    state.pipeline_health = 91.0
    state.phase_metrics["R"].health = 88.0
    state.metadata.update(
        {
            "last_review_status": "APPROVED",
            "last_patch_generated": True,
            "last_patch_apply_success": True,
            "last_proof_type": "git_diff_checksum",
            "last_proof_value": "abc",
            "anti_hallucination_checks": 10,
            "anti_hallucination_pass_count": 7,
            "anti_hallucination_block_count": 3,
            "learning_frozen": False,
            "learning_ingest_status": "ingested",
            "curiosity_score": 32.5,
            "pattern_reuse_rate": 80.0,
            "lesson_quality": 86.0,
            "next_run_hit_rate": 83.0,
            "self_heal_status_window": ["repaired", "failed", "healthy"],
            "self_heal_route_phase_weights": {"R": 10.0},
            "self_heal_route_policy_sync": "ok",
            "self_heal_cycle": {
                "status": "repaired",
                "diagnosis": {"kind": "audit_failure"},
                "after_diagnosis": {"kind": "healthy"},
                "phase_route": ["R", "A"],
            },
            "self_heal_route_bias": {
                "route_before": ["R", "A"],
                "route_after": ["A", "R"],
            },
        }
    )

    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda current: _FakeSnapshot(overall_score=93.0, status="HEALTHY"),
    )

    result = run_health_explain(engine)

    assert result.snapshot_score == 93.0
    assert result.anti_hallucination["proof_present"] is True
    assert result.learning["ingest_status"] == "ingested"
    assert result.self_healing["cycle_status"] == "repaired"
    assert result.adversarial_metrics["discriminator_checks"] == 10
    assert result.adversarial_metrics["generator_success_window"] == 3


def test_run_health_explain_alignment_zero_without_history(monkeypatch, tmp_path):
    from nexus.health.ops import run_health_explain

    engine = _engine(tmp_path)
    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda current: _FakeSnapshot(overall_score=50.0, status="WARNING"),
    )
    result = run_health_explain(engine)
    assert result.adversarial_metrics["gan_alignment_score"] == 0.0


def test_run_health_explain_appends_time_series_log(monkeypatch, tmp_path):
    from nexus.health.ops import (
        HEALTH_EXPLAIN_TIMESERIES_RELATIVE_PATH,
        run_health_explain,
    )

    engine = _engine(tmp_path)
    monkeypatch.setattr(
        "nexus.health.ops.HealthScorer.apply_snapshot",
        lambda current: _FakeSnapshot(overall_score=81.0, status="WARNING"),
    )

    run_health_explain(engine)
    run_health_explain(engine)

    output_path = tmp_path / HEALTH_EXPLAIN_TIMESERIES_RELATIVE_PATH
    assert output_path.exists()
    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    payload = json.loads(lines[-1])
    assert payload["snapshot_score"] == 81.0
    assert payload["snapshot_status"] == "WARNING"
    assert "adversarial_metrics" in payload
    assert "ts_utc" in payload
