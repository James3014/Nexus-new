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
        """執行完整的自我修復循環。"""
        diagnosis, triggers, before = self._prepare_cycle(state)
        
        planner = RepairPlanner(self.repo_root)
        plan = planner.build_plan(diagnosis, state=state)
        plan = self._reconcile_plan(planner, plan, triggers)
        
        execution = self.executor.execute(plan)
        self._ingest_execution_evidence(state, plan, execution)
        
        after = HealthScorer.apply_snapshot(state)
        after_diagnosis = HealthDiagnostics.diagnose(state, after)
        
        return self._finalize_cycle(state, before, diagnosis, plan, execution, after, after_diagnosis, triggers)

    def _prepare_cycle(self, state: NexusState) -> tuple[HealthDiagnosis, list, HealthSnapshot]:
        self._attach_fault_signatures(state)
        self._inject_fault_lessons(state)
        before = HealthScorer.apply_snapshot(state)
        triggers = HealthTriggerPolicy.evaluate_and_record(state, before)
        diagnosis = HealthDiagnostics.diagnose(state, before)
        self._update_diagnosis_fidelity(state, diagnosis.kind)
        return diagnosis, triggers, before

    def _reconcile_plan(self, planner: RepairPlanner, plan: RepairPlan, triggers: list) -> RepairPlan:
        policy_actions = planner.build_policy_actions(triggers)
        if not policy_actions:
            return plan
        merged_actions = {action.id: action for action in plan.actions}
        for action in policy_actions:
            merged_actions.setdefault(action.id, action)
        return RepairPlan(diagnosis=plan.diagnosis, actions=list(merged_actions.values()), phase_route=list(plan.phase_route))

    def _finalize_cycle(self, state: NexusState, before: HealthSnapshot, diagnosis: HealthDiagnosis, 
                        plan: RepairPlan, execution: RepairExecutionResult, after: HealthSnapshot, 
                        after_diagnosis: HealthDiagnosis, triggers: list) -> SelfHealCycleResult:
        status, notes = self._classify(before, diagnosis, plan, execution, after, after_diagnosis)
        if triggers:
            notes.extend([f"trigger:{trigger.code}" for trigger in triggers])
        
        result = SelfHealCycleResult(
            status=status, before=before, diagnosis=diagnosis, plan=plan, 
            execution=execution, after=after, after_diagnosis=after_diagnosis, notes=notes
        )
        self._update_route_weight_memory(state, result)
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

        from nexus.health.ops import TelemetryIngestor
        TelemetryIngestor.apply_evidence_json(state, self.repo_root)
        
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
                    TelemetryIngestor.apply_benchmark_csv(state, path)


    def _record(self, state: NexusState, result: SelfHealCycleResult) -> None:
        self._update_self_heal_status_window(state, result.status)
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

    @staticmethod
    def _update_self_heal_status_window(state: NexusState, cycle_status: str) -> None:
        metadata = state.metadata
        raw = metadata.get("self_heal_status_window")
        window = list(raw) if isinstance(raw, list) else []
        status = str(cycle_status or "").strip().lower() or "unknown"
        window.append(status)
        window = window[-30:]
        metadata["self_heal_status_window"] = window


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

        from nexus.services.memory import FaultLesson
        self.memory_service.record_fault_lesson(FaultLesson(
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
                "phase_route": list(result.plan.phase_route),
            },
        ))

    def _update_route_weight_memory(self, state: NexusState, result: SelfHealCycleResult) -> None:
        """更新自我修復路徑的權重記錄。"""
        metadata = state.metadata
        route = [str(p).upper() for p in (result.plan.phase_route or []) if str(p).upper() in {"P", "X", "D", "R", "A", "C"}]
        if not route:
            return

        reward = HealthScorer.calculate_reward(result.status)
        old_weights = metadata.get("self_heal_route_phase_weights") or {}
        decay = min(0.99, max(0.5, float(metadata.get("self_heal_route_weight_decay", 0.92) or 0.92)))
        
        new_weights = HealthScorer.apply_decay_and_rewards(old_weights, route, reward, decay)
        
        metadata.update({
            "self_heal_route_phase_weights": new_weights,
            "self_heal_route_weight_last_update": datetime.now().isoformat(),
            "self_heal_route_weight_status": str(result.status)
        })
        
        try:
            self.memory_service.sync_route_phase_weights(
                new_weights, cycle_status=str(result.status),
                fault_hash=str(state.metadata.get("fault_hash", "") or "")
            )
            state.metadata["self_heal_route_policy_sync"] = "ok"
        except Exception:
            state.metadata["self_heal_route_policy_sync"] = "failed"


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
