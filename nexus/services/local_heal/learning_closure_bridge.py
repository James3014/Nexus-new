from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from nexus.services.local_heal.memory_trace import MemoryTrace
from nexus.services.local_heal.candidate_envelope import CandidateEnvelope


INTERNAL_CLASSIFICATIONS = {
    "verifier_pass",
    "verifier_fail",
    "parser_fail",
    "owner_gated",
    "correct_abstain",
    "unsupported",
    "evidence_gap",
    "action_protocol_gap",
    "verifier_gap",
}

LEARNING_WRITEBACK_ENV = "NEXUS_LOCAL_HEAL_LEARNING_WRITEBACK"
_DISABLED_WRITEBACK_VALUES = frozenset({"0", "false", "no", "off"})


def _learning_writeback_disabled() -> bool:
    return os.environ.get(LEARNING_WRITEBACK_ENV, "").strip().lower() in _DISABLED_WRITEBACK_VALUES


def _disabled_writeback_evidence(target: str, **extra: Any) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "schema": "nexus.local_heal.learning_closure.v1",
        "writeback_status": "disabled",
        "writeback_disabled": True,
        "disabled_by": LEARNING_WRITEBACK_ENV,
        "writeback_target": target,
        "training_export_allowed": False,
        "internal_only": True,
    }
    evidence.update(extra)
    return evidence


def classify_learning_outcome(ctx: Any) -> str:
    op = ctx.op if hasattr(ctx, "op") else ctx
    reason = str(getattr(op, "failure_reason", "") or "").lower()
    if getattr(op, "solve_eligible", False) and not reason:
        return "verifier_pass"
    if "owner" in reason:
        return "owner_gated"
    if "unsupported" in reason:
        return "unsupported"
    if "parser" in reason or "syntax" in reason:
        return "parser_fail"
    if "evidence" in reason:
        return "evidence_gap"
    if "protocol" in reason:
        return "action_protocol_gap"
    if "verifier" in reason or "logic_regression" in reason:
        return "verifier_fail"
    return "correct_abstain" if not getattr(op, "final_patch", "") else "verifier_gap"


def _lineage(op: Any) -> dict[str, Any]:
    terminal = str(getattr(op, "terminal_outcome", "") or "").upper()
    if not terminal:
        if getattr(op, "solve_eligible", False) and not getattr(op, "failure_reason", ""):
            terminal = "SUCCEEDED"
        elif getattr(op, "failure_reason", ""):
            # A failure without an explicit terminal lifecycle decision is
            # parked for owner/reconcile handling; it is never auto-replayed.
            terminal = "PARKED"
        else:
            terminal = "PARKED"
    uncertain = bool(getattr(op, "uncertain_mutation", False))
    receipt_path = str(getattr(op, "receipt_path", "") or "").strip()
    evidence_present = bool(
        getattr(op, "terminal_evidence_present", False)
        or getattr(op, "evidence_present", False)
        or (receipt_path and receipt_path != "receipt:pending")
    )
    qualified = terminal in {"SUCCEEDED", "FAILED", "CANCELLED"} and not uncertain and evidence_present
    retrieved = [str(item) for item in (getattr(op, "retrieved_lesson_ids", None) or []) if str(item)]
    if not retrieved:
        trace = getattr(op, "_memory_influence_trace", None)
        if isinstance(trace, MemoryTrace):
            retrieved = [str(item) for item in (trace.memory_evidence_ids or []) if str(item)]
    applied = [str(item) for item in (getattr(op, "applied_lesson_ids", None) or []) if str(item)]
    explicit_disposition = str(getattr(op, "lesson_disposition", "") or "").lower()
    disposition = explicit_disposition if explicit_disposition in {"reinforce", "contradict", "retire"} else "none"
    if disposition == "none" and applied:
        if terminal == "SUCCEEDED":
            disposition = "reinforce"
        elif terminal == "FAILED":
            disposition = "contradict"
        elif terminal in {"CANCELLED", "PROCESS_LOST", "RETIRED"}:
            disposition = "retire"
    return {
        "task_id": str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown"),
        "attempt_id": str(getattr(op, "attempt_id", "") or ""),
        "action_id": str(getattr(op, "action_id", "") or ""),
        "idempotency_key": str(getattr(op, "idempotency_key", "") or ""),
        "terminal_outcome": terminal,
        "uncertain_mutation": uncertain,
        "auto_replay_allowed": False,
        "qualification_status": "QUALIFIED" if qualified else "UNQUALIFIED",
        "qualification_evidence_present": evidence_present,
        "retrieved_lesson_ids": retrieved,
        "applied_lesson_ids": applied,
        "lesson_disposition": disposition,
    }


class LearningClosureBridge:
    def __init__(
        self,
        path: Path | None = None,
        *,
        findings_store: Any | None = None,
        project_root: Path | None = None,
        enable_findings: bool = True,
    ) -> None:
        root = Path(__file__).resolve().parents[3]
        self.project_root = project_root or root
        self.path = path or root / ".nexus/reports/learn/learning_closure.jsonl"
        self.findings_store = findings_store
        self.enable_findings = enable_findings

    def _extract_memory_trace(self, ctx: Any) -> dict[str, Any]:
        for carrier in (ctx, getattr(ctx, "op", None)):
            if carrier is None:
                continue
            trace = getattr(carrier, "_memory_influence_trace", None)
            if isinstance(trace, MemoryTrace):
                return trace.to_dict()
            if isinstance(trace, dict) and trace:
                return trace
        return {}

    def _build_findings_body(self, lesson: dict[str, Any], memory_trace: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"Local-heal outcome: {lesson['classification']}",
                f"Task: {lesson['task_id']}",
                f"Summary: {lesson['summary']}",
                f"Receipt: {lesson['receipt_id']}",
                f"Memory trace status: {memory_trace.get('trace_status', 'TRACE_MISSING')}",
                f"Memory evidence ids: {', '.join(memory_trace.get('memory_evidence_ids') or [])}",
            ]
        )

    def _write_findings_card(self, lesson: dict[str, Any], memory_trace: dict[str, Any]) -> dict[str, Any]:
        if not self.enable_findings:
            return {"findings_writeback_status": "disabled"}
        try:
            from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

            store = self.findings_store or FindingsMemoryStore(self.project_root)
            body = self._build_findings_body(lesson, memory_trace)
            card = FindingsCard(
                id=str(lesson["lesson_id"])[:8],
                kind="episodes",
                title=f"LocalHeal lesson: {lesson['task_id']}",
                scope="task",
                tags=["local_heal", str(lesson["classification"])],
                stage="learning_closure",
                confidence="high" if lesson["classification"] == "verifier_pass" else "medium",
                evidence_paths=[str(lesson["receipt_id"])],
                retrieval_hints=[
                    str(lesson["task_id"]),
                    str(lesson["classification"]),
                    *[str(item) for item in memory_trace.get("memory_evidence_ids") or []],
                ],
                body=body,
                task_id=str(lesson["task_id"]),
                extra={
                    "lesson_id": lesson["lesson_id"],
                    "classification": lesson["classification"],
                    "receipt_id": lesson["receipt_id"],
                    "memory_trace_status": memory_trace.get("trace_status", "TRACE_MISSING"),
                    "retrieved_memory_ids": list(memory_trace.get("memory_evidence_ids") or []),
                    "training_export_allowed": False,
                    "internal_only": True,
                    "content": body,
                },
            )
            path = store.write(card)
            return {
                "findings_writeback_status": "ok",
                "findings_card_id": card.id,
                "findings_card_path": path,
            }
        except Exception as exc:
            return {
                "findings_writeback_status": "failed_non_blocking",
                "findings_failure_reason": exc.__class__.__name__,
            }

    def write_lesson(self, ctx: Any) -> dict[str, Any]:
        if _learning_writeback_disabled():
            return _disabled_writeback_evidence("lesson")
        op = ctx.op if hasattr(ctx, "op") else ctx
        classification = classify_learning_outcome(ctx)
        if classification not in INTERNAL_CLASSIFICATIONS:
            classification = "verifier_gap"
        memory_trace = self._extract_memory_trace(ctx)
        lineage = _lineage(op)
        lesson = {
            "lesson_id": f"lh-{uuid.uuid4().hex[:12]}",
            "task_id": str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown"),
            "classification": classification,
            "summary": str(getattr(op, "failure_reason", "") or classification)[:300],
            "provenance": str(getattr(op, "receipt_path", "") or "receipt:pending"),
            "receipt_id": str(getattr(op, "receipt_path", "") or "receipt:pending"),
            "training_export_allowed": False,
            "internal_only": True,
            "memory_trace_status": memory_trace.get("trace_status", "TRACE_MISSING"),
            "retrieved_memory_ids": list(memory_trace.get("memory_evidence_ids") or []),
            **lineage,
        }
        lesson.update(self._write_findings_card(lesson, memory_trace))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lesson, sort_keys=True) + "\n")
        return lesson

    def write_envelope_lesson(
        self,
        ctx: Any,
        envelope: CandidateEnvelope,
        selected: bool,
        selected_by: str,
        verifier_result: str,
    ) -> dict[str, Any]:
        if _learning_writeback_disabled():
            return _disabled_writeback_evidence(
                "envelope_lesson",
                candidate_id=envelope.candidate_id,
            )
        op = ctx.op if hasattr(ctx, "op") else ctx
        lineage = _lineage(op)
        
        failure_class = "none"
        if not selected:
            failure_class = "not_selected"
        elif verifier_result != "pass":
            failure_class = "verifier_fail" if verifier_result == "fail" else "blocked"
            
        lesson = {
            "lesson_id": f"lh-cand-{uuid.uuid4().hex[:12]}",
            "task_id": str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown"),
            "candidate_id": envelope.candidate_id,
            "model": envelope.model,
            "role": envelope.role,
            "selected": selected,
            "selected_by": selected_by,
            "verifier_result": verifier_result if selected else "not_run",
            "failure_class": failure_class,
            "risk_flags": list(envelope.risk_flags),
            "future_weight_delta": 1.0 if (selected and verifier_result == "pass") else -0.5 if (selected and verifier_result == "fail") else 0.0,
            "training_export_allowed": False,
            "internal_only": True,
            **lineage,
        }
        
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lesson, sort_keys=True) + "\n")
        return lesson


def write_candidate_learning_closures(
    ctx: Any,
    envelopes: list[CandidateEnvelope],
    selected_id: str,
    selected_by: str,
    verifier_result: str,
    bridge: LearningClosureBridge | None = None,
) -> list[dict[str, Any]]:
    bridge = bridge or LearningClosureBridge()
    if _learning_writeback_disabled():
        return [
            _disabled_writeback_evidence("candidate_learning_closure", candidate_id=env.candidate_id)
            for env in envelopes
        ]
    lessons = []
    for env in envelopes:
        selected = (env.candidate_id == selected_id)
        sel_by_val = selected_by if selected else "none"
        try:
            lesson = bridge.write_envelope_lesson(ctx, env, selected, sel_by_val, verifier_result)
            lessons.append(lesson)
        except Exception:
            pass
    return lessons


def write_learning_closure(ctx: Any, bridge: LearningClosureBridge | None = None) -> dict[str, Any]:
    if _learning_writeback_disabled():
        result = _disabled_writeback_evidence("learning_closure")
        op = ctx.op if hasattr(ctx, "op") else ctx
        try:
            setattr(op, "_learning_closure", result)
        except Exception:
            pass
        return result
    op = ctx.op if hasattr(ctx, "op") else ctx
    lineage = _lineage(op)
    try:
        lesson = (bridge or LearningClosureBridge()).write_lesson(ctx)
        result = {"schema": "nexus.local_heal.learning_closure.v1", "writeback_status": "ok", "lesson": lesson}
    except Exception as exc:
        result = {
            "schema": "nexus.local_heal.learning_closure.v1",
            "writeback_status": "failed_non_blocking",
            "failure_reason": exc.__class__.__name__,
            "training_export_allowed": False,
            "internal_only": True,
        }
    
    # C6AH: Writeback to OutcomeMemoryManager for dynamic_learning_policy.json
    try:
        from nexus.learning.outcome_memory import EpisodeOutcomeRecord, OutcomeMemoryManager
        task_id = str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown")
        classification = classify_learning_outcome(ctx)
        OutcomeMemoryManager.save_episode_and_tune_sync(
            EpisodeOutcomeRecord.from_task(
                task_id=task_id,
                task_type="local_heal",
                task_desc=str(getattr(op, "problem_statement", "") or "")[:500],
                solved=bool(getattr(op, "solve_eligible", False) and not getattr(op, "failure_reason", "")),
                wall_duration_sec=float(getattr(op, "wall_time_sec", 0.0) or 0.0),
                total_tokens_used=0,
                trust_mismatch=False,
                receipts=[],
                attempt_id=lineage["attempt_id"],
                action_id=lineage["action_id"],
                idempotency_key=lineage["idempotency_key"],
                terminal_outcome=lineage["terminal_outcome"],
                retrieved_lesson_ids=lineage["retrieved_lesson_ids"],
                applied_lesson_ids=lineage["applied_lesson_ids"],
                qualification_evidence_present=lineage["qualification_evidence_present"],
                lesson_updates=(
                    [
                        {"lesson_id": lesson_id, "disposition": lineage["lesson_disposition"]}
                        for lesson_id in lineage["applied_lesson_ids"]
                    ]
                    if lineage["lesson_disposition"] != "none"
                    else []
                ),
            ),
            project_root=Path(__file__).resolve().parents[3],
        )
        result["outcome_memory_writeback"] = "ok"
    except Exception:
        result["outcome_memory_writeback"] = "skipped"
    
    setattr(op, "_learning_closure", result)
    return result
