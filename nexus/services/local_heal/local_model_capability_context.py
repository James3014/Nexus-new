"""C1: Local model capability execution context and result contract.

Provides shared context for capability execution and unified result format.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LocalModelCapabilityContext:
    """Shared context passed to capability executors."""
    task_id: str
    source_root: str
    problem_statement: str
    target_file: str
    target_symbol: str
    selected_capabilities: tuple[str, ...]
    execution_topology: str
    evidence_refs: tuple[str, ...]
    source_anchor: dict[str, Any] = field(default_factory=dict)
    failure_feedback: str = ""
    verifier_command: tuple[str, ...] = ()
    candidate_pool: list[Any] = field(default_factory=list)
    route_context: dict[str, Any] = field(default_factory=dict)
    local_model_metadata: dict[str, Any] = field(default_factory=dict)
    provider: Any = None


@dataclass
class CapabilityExecutionResult:
    """Unified result from capability execution."""
    name: str
    selected: bool
    invoked: bool
    gate_passed: bool
    outcome_contributed: bool
    evidence_present: bool
    evidence_refs: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""
    telemetries: dict[str, Any] = field(default_factory=dict)

    def to_receipt_dict(self) -> dict[str, Any]:
        """Convert to CapabilityReceipt-compatible dict."""
        return {
            "name": self.name,
            "selected": self.selected,
            "invoked": self.invoked,
            "gate_passed": self.gate_passed,
            "outcome_contributed": self.outcome_contributed,
            "evidence_present": self.evidence_present,
            "evidence_refs": list(self.evidence_refs),
            "failure_reason": self.failure_reason,
            "telemetries": self.telemetries,
        }


def build_capability_context_from_request(
    request: Any,
    raw_meta: dict[str, Any],
    candidates: list[Any] | None = None,
    provider: Any = None,
) -> LocalModelCapabilityContext:
    """Build capability context from LocalModelExecutorRequest and metadata."""
    return LocalModelCapabilityContext(
        task_id=getattr(request, "task_id", ""),
        source_root=getattr(request, "repo_root", ""),
        problem_statement=getattr(request, "problem_statement", ""),
        target_file=getattr(request, "target_file", ""),
        target_symbol=raw_meta.get("target_symbol", ""),
        selected_capabilities=tuple(getattr(request, "selected_capabilities", ())),
        execution_topology=raw_meta.get("execution_topology", ""),
        evidence_refs=tuple(getattr(request, "evidence_refs", ())),
        source_anchor={
            "present": raw_meta.get("source_anchor_present", False),
            "source": raw_meta.get("source_anchor_source", ""),
            "hash": raw_meta.get("source_anchor_hash", ""),
        },
        failure_feedback="" if not raw_meta.get("failure_feedback_present") else raw_meta.get("failure_feedback_text", ""),
        verifier_command=tuple(getattr(request, "route_context", {}).get("verifier_command", []) or []),
        candidate_pool=candidates or [],
        route_context=getattr(request, "route_context", {}),
        local_model_metadata=raw_meta,
        provider=provider,
    )
