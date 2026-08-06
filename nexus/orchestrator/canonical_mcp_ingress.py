"""MCP transport adapter for the canonical product runtime seam.

The adapter normalizes task facts only.  It cannot choose a lane, provider,
model, topology, Target, lifecycle transition, or canonical mutation path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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


def build_mcp_execution_context(
    *,
    task_id: str,
    workspace_revision: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str] = (),
) -> dict[str, Any]:
    normalized_files = tuple(sorted(str(path) for path in allowed_files))
    normalized_verifiers = tuple(str(command) for command in verifier_commands)
    if len(normalized_verifiers) > 1:
        raise ValueError("MCP_VERIFIER_COMMAND_COUNT_EXCEEDED")
    context: dict[str, Any] = {
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "local_assist_mode": "advisor",
        "local_assist_policy_source": "mcp_product_entry",
        "target_files": list(normalized_files),
        "target_file": normalized_files[0] if normalized_files else "",
        "product_entry": "nexus_task_run",
    }
    if normalized_verifiers:
        context["verifier_command"] = normalized_verifiers[0]
    return context
