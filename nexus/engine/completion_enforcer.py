from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompletionDecision:
    semantic_status: str
    retryable: bool
    blocker_type: str
    next_action: str


class CompletionEnforcementError(RuntimeError):
    def __init__(self, *, context: str, decision: CompletionDecision, failures: list[str]):
        self.context = context
        self.decision = decision
        self.failures = failures
        super().__init__(
            f"{context} semantic completion failed: "
            f"status={decision.semantic_status} "
            f"retryable={decision.retryable} "
            f"blocker={decision.blocker_type} "
            f"next_action={decision.next_action} "
            f"failures={failures}"
        )


def decide_completion(payload: dict[str, Any]) -> CompletionDecision:
    semantic_status = str(payload.get("semantic_status", "UNVERIFIED")).upper()
    retryable = bool(payload.get("retryable", False))
    blocker_type = str(payload.get("blocker_type", "unknown"))
    next_action = str(payload.get("next_action", "unknown"))
    return CompletionDecision(
        semantic_status=semantic_status,
        retryable=retryable,
        blocker_type=blocker_type,
        next_action=next_action,
    )


def enforce_completion(payload: dict[str, Any], *, context: str) -> CompletionDecision:
    decision = decide_completion(payload)
    if decision.semantic_status == "VERIFIED":
        return decision
    failures = list(payload.get("semantic_failures", []))
    raise CompletionEnforcementError(context=context, decision=decision, failures=failures)


def write_completion_handoff(
    *,
    project_root: Path,
    payload: dict[str, Any],
    context: str,
    report_file: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    decision = decide_completion(payload)
    safe_context = context.replace(":", "_").replace("/", "_")
    out = Path(output_path) if output_path else project_root / ".nexus" / "reports" / "completion" / f"{safe_context}_next_action.json"
    if not out.is_absolute():
        out = (project_root / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    next_actor = "nexus_retry_loop" if decision.retryable else "human_operator"
    reasons = list(payload.get("semantic_failures", []))
    summary = (
        f"{context} ended with semantic_status={decision.semantic_status} "
        f"blocker_type={decision.blocker_type} next_action={decision.next_action}"
    )
    handoff = {
        "status": decision.semantic_status,
        "summary": summary,
        "next_action": decision.next_action,
        "next_actor": next_actor,
        "task_id": payload.get("task_name") or context,
        "phase": "R" if decision.retryable else "C",
        "state_token": decision.semantic_status,
        "escalation_reasons": reasons,
        "action_brief": {
            "title": f"{context} completion follow-up",
            "instructions": "Continue from the recorded report and resolve semantic failures before claiming completion.",
            "context": {
                "command_name": payload.get("command_name"),
                "task_name": payload.get("task_name"),
                "blocker_type": decision.blocker_type,
                "report_file": str(report_file) if report_file else "",
                "execution_path": payload.get("execution_path"),
            },
        },
    }
    out.write_text(json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8")
    state_handoff = (project_root / ".nexus" / "state" / "last_handoff.json").resolve()
    state_handoff.parent.mkdir(parents=True, exist_ok=True)
    state_handoff.write_text(json.dumps(handoff, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
