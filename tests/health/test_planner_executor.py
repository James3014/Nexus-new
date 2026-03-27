from pathlib import Path

import yaml

from nexus.health.diagnostics import HealthDiagnosis
from nexus.health.models import HealthTrigger
from nexus.health.executor import RepairExecutor
from nexus.health.planner import RepairPlanner


def test_planner_builds_safe_execute_for_environment_failure(tmp_path):
    plan = RepairPlanner(tmp_path).build_plan(
        HealthDiagnosis(kind="environment_failure", summary="runtime degraded")
    )

    assert plan.phase_route == ["P", "R", "A"]
    assert any(action.disposition == "safe_execute" for action in plan.actions)
    assert any(action.id == "auto.repair.route.p" for action in plan.actions)
    assert any(action.id == "auto.repair.route.r" for action in plan.actions)
    assert any(action.id == "auto.repair.route.a" for action in plan.actions)


def test_executor_writes_manifest_for_inject_only_actions(tmp_path):
    repo_root = tmp_path
    (repo_root / "logs" / "delivery").mkdir(parents=True)
    planner = RepairPlanner(repo_root)
    plan = planner.build_plan(
        HealthDiagnosis(
            kind="audit_failure",
            summary="audit rejected repair",
            target_phase="A",
        )
    )

    invoked = {}

    def fake_runner(manifest_path: Path) -> int:
        invoked["manifest"] = manifest_path
        return 0

    result = RepairExecutor(repo_root, task_runner=fake_runner).execute(plan)

    assert result.disposition == "inject_only"
    assert result.task_runner_invoked is True
    manifest = yaml.safe_load(invoked["manifest"].read_text(encoding="utf-8"))
    assert manifest["defaults"]["require_completion_gate"] is True
    assert manifest["tasks"][0]["completion_gate"]["verify_commands"]
    if len(manifest["tasks"]) > 1:
        assert manifest["tasks"][1]["depends_on"] == [manifest["tasks"][0]["id"]]


def test_planner_skips_actions_for_insufficient_signals(tmp_path):
    plan = RepairPlanner(tmp_path).build_plan(
        HealthDiagnosis(kind="insufficient_signals", summary="not enough evidence")
    )

    assert plan.phase_route == ["X", "D"]
    assert any(action.id == "auto.repair.route.x" for action in plan.actions)
    assert any(action.id == "auto.repair.route.d" for action in plan.actions)


def test_planner_builds_policy_actions_from_triggers(tmp_path):
    planner = RepairPlanner(tmp_path)
    triggers = [
        HealthTrigger(code="phase_health_low", reason="R below 85 for 2 rounds", severity="HIGH", target_phase="R"),
        HealthTrigger(code="learning_velocity_stalled", reason="velocity <=0 for 3 rounds", severity="MEDIUM"),
    ]

    actions = planner.build_policy_actions(triggers)
    ids = {action.id for action in actions}

    assert "auto.repair.phase.r" in ids
    assert "auto.optimize.learning" in ids


def test_executor_marks_safe_execute_timeout(monkeypatch, tmp_path):
    repo_root = tmp_path
    planner = RepairPlanner(repo_root)
    plan = planner.build_plan(
        HealthDiagnosis(kind="environment_failure", summary="runtime degraded")
    )

    def fake_run(*args, **kwargs):
        import subprocess
        raise subprocess.TimeoutExpired(cmd="pytest", timeout=1)

    monkeypatch.setattr("nexus.health.executor.subprocess.run", fake_run)
    result = RepairExecutor(repo_root, safe_action_timeout_sec=1).execute(plan)
    assert result.success is False
    assert 124 in result.return_codes.values()


def test_executor_stops_when_sandbox_validation_fails(tmp_path):
    repo_root = tmp_path
    (repo_root / "logs" / "delivery").mkdir(parents=True)
    (repo_root / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "ops").mkdir(parents=True, exist_ok=True)
    planner = RepairPlanner(repo_root)
    plan = planner.build_plan(
        HealthDiagnosis(kind="audit_failure", summary="audit rejected repair", target_phase="A")
    )

    calls = {"count": 0}

    def fake_runner(_manifest_path: Path) -> int:
        calls["count"] += 1
        # First call is sandbox validation.
        return 1

    result = RepairExecutor(repo_root, task_runner=fake_runner, sandbox_enabled=True).execute(plan)

    assert result.success is False
    assert result.task_runner_invoked is False
    assert result.return_codes["sandbox_task_runner"] == 1
    assert calls["count"] == 1


def test_executor_runs_main_after_sandbox_success(tmp_path):
    repo_root = tmp_path
    (repo_root / "logs" / "delivery").mkdir(parents=True)
    (repo_root / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts" / "ops").mkdir(parents=True, exist_ok=True)
    planner = RepairPlanner(repo_root)
    plan = planner.build_plan(
        HealthDiagnosis(kind="audit_failure", summary="audit rejected repair", target_phase="A")
    )

    calls = {"count": 0}

    def fake_runner(_manifest_path: Path) -> int:
        calls["count"] += 1
        return 0

    result = RepairExecutor(repo_root, task_runner=fake_runner, sandbox_enabled=True).execute(plan)

    assert result.success is True
    assert result.task_runner_invoked is True
    assert result.telemetry["sandbox_attempted"] is True
    assert result.telemetry["sandbox_passed"] is True
    assert calls["count"] == 2
    assert (repo_root / ".nexus" / "runs" / "latest" / "evidence.json").exists()
