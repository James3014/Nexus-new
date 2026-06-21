from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


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


class LearningClosureBridge:
    def __init__(self, path: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        self.path = path or root / ".nexus/reports/learn/learning_closure.jsonl"

    def write_lesson(self, ctx: Any) -> dict[str, Any]:
        op = ctx.op if hasattr(ctx, "op") else ctx
        classification = classify_learning_outcome(ctx)
        if classification not in INTERNAL_CLASSIFICATIONS:
            classification = "verifier_gap"
        lesson = {
            "lesson_id": f"lh-{uuid.uuid4().hex[:12]}",
            "task_id": str(getattr(op, "instance_id", "") or getattr(op, "task_id", "") or "unknown"),
            "classification": classification,
            "summary": str(getattr(op, "failure_reason", "") or classification)[:300],
            "provenance": str(getattr(op, "receipt_path", "") or "receipt:pending"),
            "receipt_id": str(getattr(op, "receipt_path", "") or "receipt:pending"),
            "training_export_allowed": False,
            "internal_only": True,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lesson, sort_keys=True) + "\n")
        return lesson


def write_learning_closure(ctx: Any, bridge: LearningClosureBridge | None = None) -> dict[str, Any]:
    op = ctx.op if hasattr(ctx, "op") else ctx
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
    setattr(op, "_learning_closure", result)
    return result
