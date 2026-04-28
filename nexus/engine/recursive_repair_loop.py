from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from nexus.contracts import RLMBudget, RLMBudgetState, RLMTraceEvent, RLMTraceWriter


def recursive_repair_enabled(ctx: Any) -> bool:
    metadata = getattr(getattr(ctx, "state", None), "metadata", {}) or {}
    return bool(metadata.get("rlm_recursive_repair_enabled")) or os.getenv("NEXUS_RLM_REPAIR_LOOP") == "1"


def _task_slug(task_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", task_id.strip().lower()).strip("-")
    return slug or "task"


def _budget_from_context(ctx: Any, max_iterations: int) -> RLMBudget:
    raw_budget = (getattr(getattr(ctx, "state", None), "metadata", {}) or {}).get("rlm_budget")
    if isinstance(raw_budget, RLMBudget):
        return raw_budget
    if isinstance(raw_budget, dict):
        payload = {key: int(value) for key, value in raw_budget.items() if value is not None}
        payload.setdefault("max_iterations", max_iterations)
        return RLMBudget.from_dict(payload)
    return RLMBudget(max_iterations=max_iterations)


class RecursiveRepairLoop:
    """Governed R-phase recursive trace adapter.

    The loop is observational first: SUBMIT records a handoff to Phase A, while
    the existing A/C gates remain the only source of success.
    """

    def __init__(self, *, project_root: Path, task_id: str, budget: RLMBudget):
        self.task_id = task_id
        self.state = RLMBudgetState.from_budget(budget)
        self.trace_path = project_root / ".nexus" / "reports" / "rlm_trace" / f"{_task_slug(task_id)}.jsonl"
        self.writer = RLMTraceWriter(self.trace_path)

    @classmethod
    def from_context(cls, *, project_root: str | Path, ctx: Any, max_iterations: int) -> "RecursiveRepairLoop":
        task_id = str(getattr(ctx, "task_id", "") or getattr(getattr(ctx, "state", None), "task_id", "") or "task")
        return cls(
            project_root=Path(project_root),
            task_id=task_id,
            budget=_budget_from_context(ctx, max_iterations=max_iterations),
        )

    def record_repair(self, *, iteration: int, status: str, result: dict[str, Any], metadata: dict[str, Any]) -> None:
        status_text = str(status or "")
        action_type = "submit" if status_text != "REJECTED" else "repair"
        stop_reason = "submit" if action_type == "submit" else "repair_rejected"
        allowed_tools = metadata.get("rlm_allowed_tools", [])
        if not isinstance(allowed_tools, list):
            allowed_tools = []
        confidence = float(metadata.get("belief_confidence", 0.0) or 0.0)
        confidence = max(0.0, min(1.0, confidence))
        self.writer.append(
            RLMTraceEvent(
                task_id=self.task_id,
                phase="R",
                iteration_id=f"r-{iteration}",
                action_type=action_type,
                observation=status_text,
                delta_hypothesis=str(result.get("no_change_reason", "") or ""),
                confidence=confidence,
                allowed_tools=[str(tool) for tool in allowed_tools],
                stop_reason=stop_reason,
                artifact_refs=list(result.get("artifact_refs", []) or []),
            )
        )

    def record_audit(self, *, iteration: int, audit_result: dict[str, Any]) -> None:
        audit_success = bool(audit_result.get("audit_success"))
        status = str(audit_result.get("status", ""))
        phantom_reason = str(audit_result.get("phantom_reason") or "")
        stop_reason = "verified" if audit_success else "audit_rejected"
        self.writer.append(
            RLMTraceEvent(
                task_id=self.task_id,
                phase="A",
                iteration_id=f"a-{iteration}",
                parent_iteration_id=f"r-{iteration}",
                action_type="audit",
                observation=status,
                blocked_reason=phantom_reason,
                stop_reason=stop_reason,
            )
        )

    def consume_iteration(self, *, llm_calls: int = 1, tool_calls: int = 0, output_chars: int = 0) -> RLMBudgetState:
        self.state = self.state.consume(
            iterations=1,
            llm_calls=llm_calls,
            tool_calls=tool_calls,
            output_chars=output_chars,
        )
        return self.state

    def record_budget_exhausted(self, *, iteration: int) -> None:
        self.writer.append(
            RLMTraceEvent(
                task_id=self.task_id,
                phase="R",
                iteration_id=f"budget-{iteration}",
                action_type="stop",
                observation="budget exhausted",
                blocked_reason=",".join(self.state.exhausted_reasons),
                stop_reason="budget_exhausted",
            )
        )
