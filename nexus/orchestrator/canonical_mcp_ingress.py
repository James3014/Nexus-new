"""MCP transport adapter for the canonical product runtime seam.

The adapter normalizes task facts only.  It cannot choose a lane, provider,
model, topology, Target, lifecycle transition, or canonical mutation path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from nexus.contracts.execution_identity import (
    require_execution_world,
    require_transport_ingress,
)

CALLER_ROUTE_OVERRIDE_FIELDS = frozenset(
    {
        "execution_preference",
        "preferred_worker",
        "preferred_model",
        "execution_lane",
        "execution_topology",
        "execution_world",
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
    return _build_canonical_ingress_context(
        task_id=task_id,
        workspace_revision=workspace_revision,
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
        execution_world="development_task",
        transport_ingress="mcp",
        product_entry="nexus_task_run",
    )


def build_cli_execution_context(
    *,
    task_id: str,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str],
    workspace_revision: str,
) -> dict[str, Any]:
    del what, why
    return _build_canonical_ingress_context(
        task_id=task_id,
        workspace_revision=workspace_revision,
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
        execution_world="development_task",
        transport_ingress="cli",
        product_entry="nexus_cli",
    )


def build_direct_execution_context(
    *,
    task_id: str,
    what: str,
    why: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str],
    workspace_revision: str,
) -> dict[str, Any]:
    del what, why
    return _build_canonical_ingress_context(
        task_id=task_id,
        workspace_revision=workspace_revision,
        allowed_files=allowed_files,
        verifier_commands=verifier_commands,
        execution_world="development_task",
        transport_ingress="direct",
        product_entry="nexus_direct",
    )


def _build_canonical_ingress_context(
    *,
    task_id: str,
    workspace_revision: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str],
    execution_world: str,
    transport_ingress: str,
    product_entry: str,
) -> dict[str, Any]:
    normalized_files = tuple(sorted(str(path) for path in allowed_files))
    normalized_verifiers = tuple(str(command) for command in verifier_commands)
    if len(normalized_verifiers) > 1:
        raise ValueError("MCP_VERIFIER_COMMAND_COUNT_EXCEEDED")
    world = require_execution_world(execution_world)
    ingress = require_transport_ingress(transport_ingress)
    semantic_payload = {
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "execution_world": world,
        "allowed_files": list(normalized_files),
        "verifier_commands": list(normalized_verifiers),
    }
    semantic_hash = "sha256:" + hashlib.sha256(
        json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    context: dict[str, Any] = {
        "task_id": str(task_id),
        "workspace_revision": str(workspace_revision),
        "execution_world": world,
        "transport_ingress": ingress,
        "canonical_semantic_hash": semantic_hash,
        "local_assist_mode": "advisor",
        "local_assist_policy_source": f"{ingress}_product_entry",
        "target_files": list(normalized_files),
        "target_file": normalized_files[0] if normalized_files else "",
        "product_entry": product_entry,
    }
    if normalized_verifiers:
        context["verifier_command"] = normalized_verifiers[0]
    return context
