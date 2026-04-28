from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from nexus.contracts import RLMBudget, RLMBudgetState, RLMTraceEvent, RLMTraceWriter
from nexus.core.belief_engine import BeliefEngine
from nexus.governance.capability_gate import CapabilityGate
from nexus.services.mem_palace import MemPalace


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
                policy_reason=str(metadata.get("rlm_policy_reason", "") or ""),
                stop_reason=stop_reason,
                artifact_refs=list(result.get("artifact_refs", []) or []),
            )
        )

    def prepare_iteration(self, *, project_root: Path, ctx: Any, iteration: int) -> bool:
        metadata = getattr(getattr(ctx, "state", None), "metadata", {}) or {}
        action = f"repair iteration {iteration}: {getattr(ctx, 'task_desc', '')}"
        try:
            allowed_tools = CapabilityGate().get_tools("R")
        except Exception:
            allowed_tools = []

        try:
            confidence = BeliefEngine(project_root / ".nexus" / "belief_state.json").assess_confidence(
                self.task_id,
                action,
            )
        except Exception:
            confidence = float(metadata.get("belief_confidence", 0.7) or 0.7)
        confidence = max(0.0, min(1.0, float(confidence)))

        policy_reason = ""
        if confidence < float(metadata.get("rlm_low_confidence_threshold", 0.35) or 0.35):
            write_tools = {"multi_replace_file_content", "replace_file_content", "safe_patch", "write_to_file"}
            allowed_tools = [tool for tool in allowed_tools if tool not in write_tools]
            policy_reason = "low_belief_confidence"

        try:
            palace_ok = MemPalace(str(project_root)).audit_action("R", action)
        except Exception:
            palace_ok = True
        metadata["rlm_allowed_tools"] = [str(tool) for tool in allowed_tools]
        metadata["belief_confidence"] = confidence
        metadata["rlm_policy_reason"] = policy_reason
        if not palace_ok:
            metadata["rlm_policy_blocked"] = True
            metadata["rlm_policy_blocked_reason"] = "mempalace_action_denied"
            self.record_policy_blocked(
                iteration=iteration,
                allowed_tools=metadata["rlm_allowed_tools"],
                confidence=confidence,
                blocked_reason="mempalace_action_denied",
            )
            return False
        return True

    def record_policy_blocked(
        self,
        *,
        iteration: int,
        allowed_tools: list[str],
        confidence: float,
        blocked_reason: str,
    ) -> None:
        self.writer.append(
            RLMTraceEvent(
                task_id=self.task_id,
                phase="R",
                iteration_id=f"policy-{iteration}",
                action_type="policy",
                observation="iteration blocked before repair",
                confidence=confidence,
                allowed_tools=allowed_tools,
                blocked_reason=blocked_reason,
                policy_reason=blocked_reason,
                stop_reason="policy_blocked",
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
