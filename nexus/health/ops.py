from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from nexus.health.diagnostics import HealthDiagnostics
from nexus.health.evaluator import HealthEvaluator
from nexus.health.executor import RepairExecutor
from nexus.health.planner import RepairPlanner
from nexus.health.scoring import HealthScorer
from nexus.health.service import SelfHealService


logger = logging.getLogger(__name__)

# 🧪 全域評估器實例 (Singleton Pattern for Phase 1)
_health_eval = HealthEvaluator()


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
HEALTH_EXPLAIN_TIMESERIES_RELATIVE_PATH = Path(".nexus/metrics/health_explain_timeseries.jsonl")


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


@dataclass(frozen=True)
class HealthExplainResult:
    snapshot_score: float
    snapshot_status: str
    pipeline_health: float
    phase_health: dict[str, float] = field(default_factory=dict)
    anti_hallucination: dict[str, object] = field(default_factory=dict)
    learning: dict[str, object] = field(default_factory=dict)
    self_healing: dict[str, object] = field(default_factory=dict)
    adversarial_metrics: dict[str, object] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def normalize_check_level(level: str) -> str:
    normalized = CHECK_LEVEL_ALIASES.get(level, level)
    if normalized not in CHECK_BENCHMARK_TASKS:
        raise ValueError(f"Unsupported self-check level: {level}")
    return normalized


def _collect_snapshot(engine):
    state = engine.state_io.load_global_state()
    return _health_eval.evaluate_state(state).get("snapshot")

def _build_snapshot_result(normalized: str, snapshot) -> SelfCheckResult:
    return SelfCheckResult(
        level=normalized,
        ok=snapshot.overall_score >= CHECK_MIN_HEALTH[normalized],
        snapshot_score=snapshot.overall_score,
        snapshot_status=snapshot.status,
        benchmark_tasks=0,
        notes=["snapshot_only"],
    )

def _run_benchmark_check(engine, normalized: str, tasks: int):
    output_path = Path(engine.run_dir) / f"self_check_{normalized}.csv"
    results = engine.run_benchmark(
        framework="swe-verified",
        task_count=tasks,
        output_csv=str(output_path),
        model=None,
        target=None,
    )
    return results, output_path

def _build_benchmark_result(normalized: str, snapshot, tasks: int, results, output_path: Path) -> SelfCheckResult:
    if not results:
        return SelfCheckResult(
            level=normalized, ok=False, snapshot_score=snapshot.overall_score,
            snapshot_status=snapshot.status, benchmark_tasks=tasks,
            benchmark_output=output_path, notes=["benchmark_no_results"],
        )
    avg_health = round(sum(float(row.get("health", 0.0)) for row in results) / len(results), 2)
    pass_rate = round(len([row for row in results if row.get("status") == "PASS"]) / len(results) * 100.0, 2)
    ok = pass_rate == 100.0 and avg_health >= CHECK_MIN_HEALTH[normalized]
    notes = [f"benchmark_cases:{len(results)}", f"benchmark_pass_rate:{pass_rate}"]
    if avg_health < CHECK_MIN_HEALTH[normalized]:
        notes.append("health_below_threshold")
    return SelfCheckResult(
        level=normalized, ok=ok, snapshot_score=snapshot.overall_score,
        snapshot_status=snapshot.status, benchmark_tasks=len(results),
        benchmark_avg_health=avg_health, benchmark_pass_rate=pass_rate,
        benchmark_output=output_path, notes=notes,
    )

def run_self_check(engine, level: str = "standard") -> SelfCheckResult:
    normalized = normalize_check_level(level)
    snapshot = _collect_snapshot(engine)
    benchmark_tasks = CHECK_BENCHMARK_TASKS[normalized]

    if benchmark_tasks == 0:
        return _build_snapshot_result(normalized, snapshot)

    results, output_path = _run_benchmark_check(engine, normalized, benchmark_tasks)
    return _build_benchmark_result(normalized, snapshot, benchmark_tasks, results, output_path)


def _diagnose_and_plan(engine):
    state = engine.state_io.load_global_state()
    before = _health_eval.evaluate_state(state).get("snapshot", {})
    diagnosis = _health_eval.diagnose_drift(state, before)
    plan = RepairPlanner(Path(engine.project_root)).build_plan(diagnosis, state=state)
    planned_actions = [action.id for action in plan.actions]
    phase_route = list(getattr(plan, "phase_route", []))
    return state, before, diagnosis, plan, planned_actions, phase_route

def _execute_heal_cycle(engine, state, mode: str):
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
    return cycle

def _build_heal_result(mode: str, cycle, before, diagnosis, planned_actions, phase_route) -> SelfHealCommandResult:
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

def run_self_heal(engine, mode: str = "standard") -> SelfHealCommandResult:
    if mode not in {"dry-run", "standard", "strict"}:
        raise ValueError(f"Unsupported self-heal mode: {mode}")

    state, before, diagnosis, plan, planned_actions, phase_route = _diagnose_and_plan(engine)

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

    cycle = _execute_heal_cycle(engine, state, mode)
    return _build_heal_result(mode, cycle, before, diagnosis, planned_actions, phase_route)


def _collect_anti_hallucination(metadata: dict) -> dict[str, object]:
    proof_type = str(metadata.get("last_proof_type", "") or "")
    proof_value = str(metadata.get("last_proof_value", "") or "")
    return {
        "last_review_status": str(metadata.get("last_review_status", "") or ""),
        "patch_generated": bool(metadata.get("last_patch_generated", False)),
        "patch_apply_success": bool(metadata.get("last_patch_apply_success", False)),
        "proof_type": proof_type,
        "proof_present": bool(proof_type and proof_value),
        "phantom_success_reason": str(metadata.get("phantom_success_reason", "") or ""),
    }

def _collect_learning_metrics(metadata: dict) -> dict[str, object]:
    return {
        "frozen": bool(metadata.get("learning_frozen", False)),
        "freeze_reasons": list(metadata.get("learning_freeze_reasons", []) or []),
        "ingest_status": str(metadata.get("learning_ingest_status", "") or ""),
        "curiosity_score": float(metadata.get("curiosity_score", 0.0) or 0.0),
        "pattern_reuse_rate": float(metadata.get("pattern_reuse_rate", 0.0) or 0.0),
        "lesson_quality": float(metadata.get("lesson_quality", 0.0) or 0.0),
        "next_run_hit_rate": float(metadata.get("next_run_hit_rate", 0.0) or 0.0),
    }

def _collect_self_healing(metadata: dict) -> dict[str, object]:
    cycle = metadata.get("self_heal_cycle") or {}
    route_bias = metadata.get("self_heal_route_bias") or {}
    return {
        "cycle_status": str(cycle.get("status", "") or ""),
        "diagnosis_kind": str((cycle.get("diagnosis") or {}).get("kind", "") or ""),
        "after_diagnosis_kind": str((cycle.get("after_diagnosis") or {}).get("kind", "") or ""),
        "phase_route": list(cycle.get("phase_route", []) or []),
        "route_before": list(route_bias.get("route_before", []) or []),
        "route_after": list(route_bias.get("route_after", []) or []),
        "route_weights": dict(metadata.get("self_heal_route_phase_weights", {}) or {}),
        "policy_sync": str(metadata.get("self_heal_route_policy_sync", "") or ""),
    }

def run_health_explain(engine) -> HealthExplainResult:
    state = engine.state_io.load_global_state()
    snapshot = _health_eval.evaluate_state(state).get("snapshot")
    metadata = state.metadata or {}
    
    phase_health = _gather_phase_health(state)
    anti_hallucination = _collect_anti_hallucination(metadata)
    learning = _collect_learning_metrics(metadata)
    self_healing = _collect_self_healing(metadata)
    adversarial_metrics = _build_adversarial_metrics(metadata)

    result = HealthExplainResult(
        snapshot_score=round(float(snapshot.overall_score), 2),
        snapshot_status=str(snapshot.status),
        pipeline_health=round(float(state.pipeline_health or 0.0), 2),
        phase_health=phase_health,
        anti_hallucination=anti_hallucination,
        learning=learning,
        self_healing=self_healing,
        adversarial_metrics=adversarial_metrics,
        notes=_build_explain_notes(anti_hallucination, learning, self_healing),
    )
    
    _record_explain_timeseries(engine, result)
    return result

def _gather_phase_health(state: NexusState) -> dict[str, float]:
    return {
        phase: round(float(getattr(metric, "health", 0.0) or 0.0), 2)
        for phase, metric in (state.phase_metrics or {}).items()
    }

def _build_explain_notes(anti_hallucination: dict, learning: dict, self_healing: dict) -> list[str]:
    notes: list[str] = []
    if anti_hallucination["patch_generated"] and anti_hallucination["patch_apply_success"] and not anti_hallucination["proof_present"]:
        notes.append("anti_hallucination_block_risk:missing_proof")
    if learning["frozen"]:
        notes.append("learning_frozen")
    if self_healing["cycle_status"]:
        notes.append(f"self_heal_cycle:{self_healing['cycle_status']}")
    return notes

def _record_explain_timeseries(engine, result: HealthExplainResult) -> None:
    try:
        _append_health_explain_timeseries(Path(engine.project_root), result)
    except OSError as exc:
        result.notes.append(f"timeseries_log_write_failed:{exc.__class__.__name__}")


def _append_health_explain_timeseries(project_root: Path, result: HealthExplainResult) -> Path:
    output_path = project_root / HEALTH_EXPLAIN_TIMESERIES_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_score": round(float(result.snapshot_score), 2),
        "snapshot_status": str(result.snapshot_status),
        "pipeline_health": round(float(result.pipeline_health), 2),
        "phase_health": dict(result.phase_health),
        "anti_hallucination": dict(result.anti_hallucination),
        "learning": dict(result.learning),
        "self_healing": dict(result.self_healing),
        "adversarial_metrics": dict(result.adversarial_metrics),
        "notes": list(result.notes),
    }
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")
    return output_path


def _build_adversarial_metrics(metadata: dict) -> dict[str, object]:
    checks = int(metadata.get("anti_hallucination_checks", 0) or 0)
    blocks = int(metadata.get("anti_hallucination_block_count", 0) or 0)
    passes = int(metadata.get("anti_hallucination_pass_count", 0) or 0)
    d_block_rate = round((blocks / checks) * 100.0, 2) if checks > 0 else 0.0
    d_pass_rate = round((passes / checks) * 100.0, 2) if checks > 0 else 0.0

    status_window = metadata.get("self_heal_status_window")
    window = list(status_window) if isinstance(status_window, list) else []
    if window:
        repaired_like = len([s for s in window if str(s).lower() in {"repaired", "healthy"}])
        g_success_rate = round((repaired_like / len(window)) * 100.0, 2)
    else:
        g_success_rate = 0.0

    # Simple alignment score: reward successful repair and healthy gate behavior.
    # Penalize high block rate lightly (blocks are useful), but too many indicate unstable generator output.
    if checks == 0 and not window:
        alignment = 0.0
    else:
        alignment = max(
            0.0,
            min(
                100.0,
                round((0.6 * g_success_rate) + (0.3 * d_pass_rate) + (0.1 * (100.0 - d_block_rate)), 2),
            ),
        )
    return {
        "discriminator_checks": checks,
        "discriminator_block_count": blocks,
        "discriminator_pass_count": passes,
        "discriminator_block_rate": d_block_rate,
        "discriminator_pass_rate": d_pass_rate,
        "generator_success_window": len(window),
        "generator_success_rate": g_success_rate,
        "gan_alignment_score": alignment,
    }
class TelemetryIngestor:
    """📊 Nexus Telemetry Ingestor: 負責從外部文件導入遙測與測評數據。"""
    
    @staticmethod
    def apply_benchmark_csv(state: NexusState, csv_path: Path) -> None:
        import csv
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            return

        row = rows[-1]
        state.health_score = float(row.get("health") or state.health_score or 0.0)
        state.total_token_usage = int(float(row.get("tokens") or state.total_token_usage or 0))
        state.token_raw_model = int(float(row.get("token_raw_model") or state.token_raw_model or 0))
        state.token_fallback_est = int(float(row.get("token_fallback_est") or state.token_fallback_est or 0))
        state.token_system_overhead = int(float(row.get("token_system_overhead") or state.token_system_overhead or 0))
        state.phase_tokens["X"] = int(float(row.get("token_source_x") or state.phase_tokens.get("X", 0)))
        state.phase_tokens["R"] = int(float(row.get("token_source_r") or state.phase_tokens.get("R", 0)))
        state.token_capture_status = row.get("token_capture_status") or state.token_capture_status
        state.metadata["last_review_status"] = row.get("review_status") or state.metadata.get("last_review_status")
        state.health_metrics.test_pass_rate = 1.0 if row.get("status") == "PASS" else 0.0
        state.health_metrics.drift_index = float(row.get("drift") or state.health_metrics.drift_index or 0.0)
        state.health_metrics.error_rate = 0.0 if row.get("status") == "PASS" else 1.0
        
        if row.get("status") == "PASS" and state.token_capture_status != "unknown":
            state.health_metrics.token_efficiency = 1.0
        elif state.total_token_usage > 0:
            state.health_metrics.token_efficiency = max(
                0.0,
                1.0 - (state.token_system_overhead / max(state.total_token_usage, 1)),
            )
        state.health_metrics.last_check_at = datetime.now()
        state.health_metrics.status = "HEALTHY" if row.get("status") == "PASS" else "WARNING"

    @staticmethod
    def apply_evidence_json(state: NexusState, project_root: Path) -> None:
        path = project_root / ".nexus" / "runs" / "latest" / "evidence.json"
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        telemetry = payload.get("telemetry")
        if isinstance(telemetry, dict):
            state.metadata["evidence_telemetry"] = telemetry
            if telemetry.get("sandbox_hit_rate") is not None:
                state.metadata["sandbox_hit_rate"] = float(telemetry["sandbox_hit_rate"])
