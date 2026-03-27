from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from nexus.core.state_contracts import NexusState
from nexus.health.diagnostics import HealthDiagnostics
from nexus.health.executor import RepairExecutor
from nexus.health.models import (
    HealthDiagnosis,
    HealthSnapshot,
    RepairExecutionResult,
    RepairPlan,
    SelfHealCycleResult,
)
from nexus.health.planner import RepairPlanner
from nexus.health.policy import HealthTriggerPolicy
from nexus.health.scoring import HealthScorer
from nexus.health.signature_extractor import FaultSignatureExtractor
from nexus.services.memory import MemoryService


class SelfHealService:
    def __init__(self, repo_root: Path, executor: Optional[RepairExecutor] = None):
        self.repo_root = Path(repo_root)
        self.executor = executor or RepairExecutor(self.repo_root)
        self.memory_service = MemoryService(str(self.repo_root))

    def run_cycle(self, state: NexusState) -> SelfHealCycleResult:
        self._attach_fault_signatures(state)
        self._inject_fault_lessons(state)
        before = HealthScorer.apply_snapshot(state)
        triggers = HealthTriggerPolicy.evaluate_and_record(state, before)
        diagnosis = HealthDiagnostics.diagnose(state, before)
        self._update_diagnosis_fidelity(state, diagnosis.kind)
        planner = RepairPlanner(self.repo_root)
        plan = planner.build_plan(diagnosis)
        policy_actions = planner.build_policy_actions(triggers)
        if policy_actions:
            merged_actions = {action.id: action for action in plan.actions}
            for action in policy_actions:
                merged_actions.setdefault(action.id, action)
            plan = RepairPlan(
                diagnosis=plan.diagnosis,
                actions=list(merged_actions.values()),
                phase_route=list(plan.phase_route),
            )
        execution = self.executor.execute(plan)
        self._ingest_execution_evidence(state, plan, execution)
        after = HealthScorer.apply_snapshot(state)
        after_diagnosis = HealthDiagnostics.diagnose(state, after)

        status, notes = self._classify(before, diagnosis, plan, execution, after, after_diagnosis)
        if triggers:
            notes.extend([f"trigger:{trigger.code}" for trigger in triggers])
        result = SelfHealCycleResult(
            status=status,
            before=before,
            diagnosis=diagnosis,
            plan=plan,
            execution=execution,
            after=after,
            after_diagnosis=after_diagnosis,
            notes=notes,
        )
        self._record(state, result)
        self._record_fault_lesson(state, result)
        return result

    def _classify(
        self,
        before: HealthSnapshot,
        diagnosis: HealthDiagnosis,
        plan: RepairPlan,
        execution: RepairExecutionResult,
        after: HealthSnapshot,
        after_diagnosis: HealthDiagnosis,
    ) -> tuple[str, list[str]]:
        notes: list[str] = []
        if diagnosis.kind == "healthy" and not plan.actions:
            return "healthy", ["already_healthy"]
        if not plan.actions:
            return "noop", ["no_repair_actions"]
        if not execution.success:
            notes.extend(execution.notes)
            notes.append("execution_failed")
            return "failed", notes
        if after.overall_score >= 80.0 and after.overall_score >= before.overall_score:
            notes.extend(execution.notes)
            notes.append("health_recovered")
            return "repaired", notes
        notes.extend(execution.notes)
        notes.append(f"post_diagnosis:{after_diagnosis.kind}")
        return "degraded", notes

    def _ingest_execution_evidence(
        self,
        state: NexusState,
        plan: RepairPlan,
        execution: RepairExecutionResult,
    ) -> None:
        if not execution.success:
            return

        self._apply_evidence_json(state)
        telemetry = execution.telemetry or {}
        if telemetry:
            if telemetry.get("sandbox_hit_rate") is not None:
                state.metadata["sandbox_hit_rate"] = float(telemetry["sandbox_hit_rate"])
            state.metadata["sandbox_telemetry"] = telemetry

        executed = set(execution.executed_actions)
        for action in plan.actions:
            if action.id not in executed:
                continue
            for artifact in action.artifact_paths:
                path = self.repo_root / artifact
                if path.suffix == ".csv" and path.exists():
                    self._apply_benchmark_csv(state, path)

    def _apply_benchmark_csv(self, state: NexusState, csv_path: Path) -> None:
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
        state.metadata.pop("health_error_kind", None)

    def _record(self, state: NexusState, result: SelfHealCycleResult) -> None:
        state.metadata["health_snapshot"] = self._snapshot_dict(result.after)
        state.metadata["health_diagnosis"] = asdict(result.after_diagnosis)
        state.metadata["self_heal_cycle"] = {
            "status": result.status,
            "before": self._snapshot_dict(result.before),
            "diagnosis": asdict(result.diagnosis),
            "phase_route": list(result.plan.phase_route),
            "plan_actions": [action.id for action in result.plan.actions],
            "execution": {
                "disposition": result.execution.disposition,
                "success": result.execution.success,
                "executed_actions": list(result.execution.executed_actions),
                "injected_tasks": list(result.execution.injected_tasks),
                "manifest_path": str(result.execution.manifest_path) if result.execution.manifest_path else None,
                "task_runner_invoked": result.execution.task_runner_invoked,
                "return_codes": dict(result.execution.return_codes),
                "notes": list(result.execution.notes),
                "telemetry": dict(result.execution.telemetry),
            },
            "after": self._snapshot_dict(result.after),
            "after_diagnosis": asdict(result.after_diagnosis),
            "notes": list(result.notes),
        }
        state.metadata["auto_repair_last_result"] = {
            "disposition": result.execution.disposition,
            "success": result.execution.success,
            "executed_actions": list(result.execution.executed_actions),
            "injected_tasks": list(result.execution.injected_tasks),
            "manifest_path": str(result.execution.manifest_path) if result.execution.manifest_path else None,
            "task_runner_invoked": result.execution.task_runner_invoked,
            "return_codes": dict(result.execution.return_codes),
            "notes": list(result.execution.notes),
            "telemetry": dict(result.execution.telemetry),
            "diagnosis_kind": result.diagnosis.kind,
            "health_score": result.after.overall_score,
            "cycle_status": result.status,
        }

    def _apply_evidence_json(self, state: NexusState) -> None:
        path = self.repo_root / ".nexus" / "runs" / "latest" / "evidence.json"
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

    def _attach_fault_signatures(self, state: NexusState) -> None:
        text = self._get_fault_text(state)
        signatures = FaultSignatureExtractor.extract(text)
        if not signatures:
            return
        serialized = [asdict(sig) for sig in signatures]
        state.metadata["fault_signatures"] = serialized
        state.metadata["fault_hash"] = serialized[0]["hash"]

    @staticmethod
    def _get_fault_text(state: NexusState) -> str:
        for key in ("health_error_text", "last_error_text", "last_traceback", "error_log"):
            value = state.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    def _update_diagnosis_fidelity(self, state: NexusState, diagnosis_kind: str) -> None:
        signatures = state.metadata.get("fault_signatures") or []
        if not signatures:
            state.metadata["diagnosis_fidelity"] = 0.0
            return
        first = signatures[0] if isinstance(signatures[0], dict) else {}
        fault_hash = str(first.get("hash", ""))
        history = state.metadata.get("fault_signature_history")
        if not isinstance(history, list):
            history = []
        prior = next((h for h in history if h.get("hash") == fault_hash), None)
        if prior is None:
            fidelity = 65.0
        elif prior.get("diagnosis_kind") == diagnosis_kind:
            fidelity = 100.0
        else:
            fidelity = 25.0
        history.append({"hash": fault_hash, "diagnosis_kind": diagnosis_kind})
        state.metadata["fault_signature_history"] = history[-100:]
        state.metadata["diagnosis_fidelity"] = fidelity

    def _inject_fault_lessons(self, state: NexusState) -> None:
        fault_hash = str(state.metadata.get("fault_hash", ""))
        if not fault_hash:
            return
        lessons = self.memory_service.lookup_fault_lessons(fault_hash, limit=3)
        if not lessons:
            return
        state.metadata["fault_lesson_hits"] = lessons
        # Link memory retrieval into policy hit context for downstream learning.
        for idx, lesson in enumerate(lessons):
            state.policy_hit_ids.append(f"FAULT-{fault_hash[:8]}-{idx}")

    def _record_fault_lesson(self, state: NexusState, result: SelfHealCycleResult) -> None:
        fault_hash = str(state.metadata.get("fault_hash", ""))
        signatures = state.metadata.get("fault_signatures") or []
        if not fault_hash or not isinstance(signatures, list) or not signatures:
            return
        first = signatures[0] if isinstance(signatures[0], dict) else {}
        error_type = str(first.get("error_type", "unknown"))
        diagnosis_kind = str(result.diagnosis.kind)
        audit_score = result.after.phase_scores.get("A")
        audit_pass_rate = 0.0
        if audit_score is not None:
            audit_pass_rate = max(0.0, min(1.0, float(audit_score.score) / 100.0))

        self.memory_service.record_fault_lesson(
            fault_hash=fault_hash,
            error_type=error_type,
            diagnosis_kind=diagnosis_kind,
            lesson=f"{diagnosis_kind} -> {result.status}",
            repair_patch="; ".join(result.execution.executed_actions or result.execution.injected_tasks),
            audit_pass_rate=audit_pass_rate,
            metadata={
                "cycle_status": result.status,
                "after_score": result.after.overall_score,
                "notes": list(result.notes),
            },
        )

    @staticmethod
    def _snapshot_dict(snapshot: HealthSnapshot) -> dict:
        return {
            "overall_score": snapshot.overall_score,
            "outcome_score": snapshot.outcome_score,
            "phase_average": snapshot.phase_average,
            "confidence": snapshot.confidence,
            "status": snapshot.status,
            "reasons": list(snapshot.reasons),
        }
