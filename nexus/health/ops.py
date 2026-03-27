from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from nexus.health.diagnostics import HealthDiagnostics
from nexus.health.executor import RepairExecutor
from nexus.health.planner import RepairPlanner
from nexus.health.scoring import HealthScorer
from nexus.health.service import SelfHealService


CHECK_LEVEL_ALIASES = {
    "pre-merge": "standard",
    "nightly": "high",
}

CHECK_MIN_HEALTH = {
    "quick": 0.0,
    "standard": 80.0,
    "high": 90.0,
    "full": 90.0,
}

CHECK_BENCHMARK_TASKS = {
    "quick": 0,
    "standard": 1,
    "high": 1,
    "full": 10,
}

STRICT_SAFE_ACTION_TIMEOUT_SEC = 45
STRICT_TASK_RUNNER_TIMEOUT_SEC = 75
STRICT_TOTAL_TIMEOUT_SEC = 90


@dataclass(frozen=True)
class SelfCheckResult:
    level: str
    ok: bool
    snapshot_score: float
    snapshot_status: str
    benchmark_tasks: int = 0
    benchmark_avg_health: Optional[float] = None
    benchmark_pass_rate: Optional[float] = None
    benchmark_output: Optional[Path] = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SelfHealCommandResult:
    mode: str
    ok: bool
    cycle_status: str
    before_score: float
    after_score: float
    diagnosis_kind: str
    after_diagnosis_kind: str
    phase_route: list[str] = field(default_factory=list)
    planned_actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def normalize_check_level(level: str) -> str:
    normalized = CHECK_LEVEL_ALIASES.get(level, level)
    if normalized not in CHECK_BENCHMARK_TASKS:
        raise ValueError(f"Unsupported self-check level: {level}")
    return normalized


def run_self_check(engine, level: str = "standard") -> SelfCheckResult:
    normalized = normalize_check_level(level)
    state = engine.state_io.load_global_state()
    snapshot = HealthScorer.apply_snapshot(state)
    benchmark_tasks = CHECK_BENCHMARK_TASKS[normalized]

    if benchmark_tasks == 0:
        return SelfCheckResult(
            level=normalized,
            ok=snapshot.overall_score >= CHECK_MIN_HEALTH[normalized],
            snapshot_score=snapshot.overall_score,
            snapshot_status=snapshot.status,
            benchmark_tasks=0,
            notes=["snapshot_only"],
        )

    output_path = Path(engine.run_dir) / f"self_check_{normalized}.csv"
    results = engine.run_benchmark(
        framework="swe-verified",
        task_count=benchmark_tasks,
        output_csv=str(output_path),
        model=None,
        target=None,
    )

    if not results:
        return SelfCheckResult(
            level=normalized,
            ok=False,
            snapshot_score=snapshot.overall_score,
            snapshot_status=snapshot.status,
            benchmark_tasks=benchmark_tasks,
            benchmark_output=output_path,
            notes=["benchmark_no_results"],
        )

    avg_health = round(
        sum(float(row.get("health", 0.0)) for row in results) / len(results), 2
    )
    pass_rate = round(
        len([row for row in results if row.get("status") == "PASS"]) / len(results) * 100.0,
        2,
    )
    ok = pass_rate == 100.0 and avg_health >= CHECK_MIN_HEALTH[normalized]
    notes = [f"benchmark_cases:{len(results)}", f"benchmark_pass_rate:{pass_rate}"]
    if avg_health < CHECK_MIN_HEALTH[normalized]:
        notes.append("health_below_threshold")

    return SelfCheckResult(
        level=normalized,
        ok=ok,
        snapshot_score=snapshot.overall_score,
        snapshot_status=snapshot.status,
        benchmark_tasks=len(results),
        benchmark_avg_health=avg_health,
        benchmark_pass_rate=pass_rate,
        benchmark_output=output_path,
        notes=notes,
    )


def run_self_heal(engine, mode: str = "standard") -> SelfHealCommandResult:
    if mode not in {"dry-run", "standard", "strict"}:
        raise ValueError(f"Unsupported self-heal mode: {mode}")

    state = engine.state_io.load_global_state()
    before = HealthScorer.apply_snapshot(state)
    diagnosis = HealthDiagnostics.diagnose(state, before)
    plan = RepairPlanner(Path(engine.project_root)).build_plan(diagnosis, state=state)
    planned_actions = [action.id for action in plan.actions]
    phase_route = list(getattr(plan, "phase_route", []))

    if mode == "dry-run":
        return SelfHealCommandResult(
            mode=mode,
            ok=True,
            cycle_status="dry-run",
            before_score=before.overall_score,
            after_score=before.overall_score,
            diagnosis_kind=diagnosis.kind,
            after_diagnosis_kind=diagnosis.kind,
            phase_route=phase_route,
            planned_actions=planned_actions,
            notes=["no_execution"],
        )

    if mode == "strict":
        executor = RepairExecutor(
            Path(engine.project_root),
            safe_action_timeout_sec=STRICT_SAFE_ACTION_TIMEOUT_SEC,
            task_runner_timeout_sec=STRICT_TASK_RUNNER_TIMEOUT_SEC,
            total_timeout_sec=STRICT_TOTAL_TIMEOUT_SEC,
        )
        cycle = SelfHealService(Path(engine.project_root), executor=executor).run_cycle(state)
    else:
        cycle = SelfHealService(Path(engine.project_root)).run_cycle(state)
    engine.state_io.save_global_state(state)

    ok = cycle.status in {"healthy", "repaired"}
    if mode == "strict":
        ok = ok and cycle.after.overall_score >= 90.0

    cycle_plan = getattr(cycle, "plan", None)
    if cycle_plan is not None and getattr(cycle_plan, "actions", None) is not None:
        cycle_plan_actions = [action.id for action in cycle_plan.actions]
    else:
        cycle_plan_actions = planned_actions
    cycle_phase_route = list(getattr(cycle_plan, "phase_route", phase_route))

    return SelfHealCommandResult(
        mode=mode,
        ok=ok,
        cycle_status=cycle.status,
        before_score=getattr(getattr(cycle, "before", None), "overall_score", before.overall_score),
        after_score=cycle.after.overall_score,
        diagnosis_kind=cycle.diagnosis.kind,
        after_diagnosis_kind=cycle.after_diagnosis.kind,
        phase_route=cycle_phase_route,
        planned_actions=cycle_plan_actions,
        notes=list(cycle.notes),
    )
