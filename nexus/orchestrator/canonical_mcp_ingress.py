"""MCP transport adapter for the canonical planning seam.

The adapter normalizes task facts and returns planner identity only.  It cannot
choose a lane, provider, model, Target, lifecycle transition, or mutation path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from nexus.contracts.canonical_execution import CanonicalTaskContext
from nexus.engine.canonical_execution import plan_canonical_task

CALLER_ROUTE_OVERRIDE_FIELDS = frozenset(
    {
        "execution_preference",
        "preferred_worker",
        "preferred_model",
        "execution_lane",
        "provider",
        "model",
        "target_repo_root",
        "target_worktree_root",
    }
)
CANONICAL_MCP_TASK_FIELDS = frozenset(
    {"task_id", "what", "why", "allowed_files", "verifier_commands"}
)


def reject_caller_route_overrides(arguments: Mapping[str, Any]) -> None:
    for field in sorted(CALLER_ROUTE_OVERRIDE_FIELDS):
        if field in arguments:
            raise ValueError(f"CALLER_ROUTE_OVERRIDE_FORBIDDEN:{field}")
    unexpected = sorted(set(arguments) - CANONICAL_MCP_TASK_FIELDS)
    if unexpected:
        raise ValueError(f"MCP_CANONICAL_INGRESS_FIELD_FORBIDDEN:{unexpected[0]}")


def build_mcp_task_context(
    *,
    task_id: str,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str] = (),
) -> CanonicalTaskContext:
    normalized_files = tuple(sorted(str(path) for path in allowed_files))
    normalized_verifiers = tuple(str(command) for command in verifier_commands)
    top_level_paths = {path.split("/", 1)[0] for path in normalized_files}
    cross_module = len(normalized_files) > 1 and (
        len(top_level_paths) > 1 or any(path.startswith("nexus/") for path in normalized_files)
    )
    return CanonicalTaskContext(
        task_id=task_id,
        task_type="code",
        task_desc=what,
        route_features={
            "allowed_file_count": len(normalized_files),
            "impact_complexity": 0.8 if cross_module else 0.1,
            "is_cross_module_task": cross_module,
            "mutation_requested": True,
        },
        codeintel={"allowed_files": normalized_files, "verifier_commands": normalized_verifiers},
        phase_trace={"request_why": why},
    )


def plan_mcp_task(
    *,
    task_id: str,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str] = (),
) -> dict[str, Any]:
    context = build_mcp_task_context(
        task_id=task_id,
        what=what,
        why=why,
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
    )
    decision, projection = plan_canonical_task(context)
    return {
        "schema": "nexus.mcp_canonical_decision.v1",
        "status": "CANONICAL_DECISION_READY",
        "task_id": task_id,
        "execution_decision_authority": decision.authority,
        "context": context.to_dict(),
        "context_hash": context.context_hash,
        "execution_decision": decision.to_dict(),
        "decision_hash": decision.decision_hash,
        "canonical_execution_projection": projection.to_dict(),
        "projection_hash": projection.projection_hash,
        "mutation_dispatched": False,
        "next_action": "continue_via_canonical_runtime",
    }
