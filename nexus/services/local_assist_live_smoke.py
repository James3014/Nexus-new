"""Explicit LiveSmoke operator-spec → canonical LocalAssistRequest translator.

Operator fixtures use ``nexus.local_assist.live_smoke_task.v1``.
The product service contract remains ``nexus.local_assist.request.v1``.

``LocalAssistRequest.from_dict`` must NOT silently accept live-smoke schemas.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_service import (
    REQUEST_SCHEMA,
    LocalAssistRequest,
)

LIVE_SMOKE_SCHEMA = "nexus.local_assist.live_smoke_task.v1"
DEFAULT_LOCAL_MODEL = "qwen2.5-coder:7b-instruct"


def is_live_smoke_payload(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return str(payload.get("schema") or "").strip() == LIVE_SMOKE_SCHEMA


def _require_false_or_absent(payload: Mapping[str, Any], key: str) -> None:
    if key not in payload:
        return
    if bool(payload.get(key)):
        raise ValueError(f"live_smoke_rejects_{key}")


def translate_live_smoke_to_request(
    payload: Mapping[str, Any],
    *,
    workspace_root: str | Path | None = None,
    action: str | None = None,
    default_model: str = DEFAULT_LOCAL_MODEL,
) -> LocalAssistRequest:
    """Map a LiveSmokeTaskSpec object into a validated LocalAssistRequest.

    Rejects unsafe mutation semantics. Does not invent formal workspace writes.
    """
    if not is_live_smoke_payload(payload):
        raise ValueError("not_live_smoke_schema")

    _require_false_or_absent(payload, "request_patch")
    _require_false_or_absent(payload, "formal_workspace_mutation_allowed")

    mutation = str(payload.get("mutation_policy") or "isolated_only").strip()
    if mutation != "isolated_only":
        raise ValueError("live_smoke_mutation_policy_must_be_isolated_only")

    policy = str(payload.get("local_assist_policy") or "advisor").strip().lower()
    # Live-smoke operator specs are advisor-oriented; candidate modes need full request.v1.
    if policy not in {"advisor", "shadow", "disabled"}:
        raise ValueError("live_smoke_unsupported_local_assist_policy")

    resolved_action = str(action or "advisor").strip().lower()
    if resolved_action not in {"advisor"}:
        # Smoke translator only emits advisor requests; other actions use request.v1.
        raise ValueError("live_smoke_action_must_be_advisor")

    allowed = tuple(str(x).strip() for x in (payload.get("allowed_files") or ()) if str(x).strip())
    if not allowed:
        raise ValueError("live_smoke_missing_allowed_files")

    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("live_smoke_missing_task_id")

    statement = str(payload.get("task_statement") or "").strip()
    if not statement:
        raise ValueError("live_smoke_missing_task_statement")

    revision = str(payload.get("workspace_revision") or "").strip()
    if not revision:
        raise ValueError("live_smoke_missing_workspace_revision")

    root = str(workspace_root or payload.get("workspace_root") or Path.cwd())
    role = str(payload.get("expected_local_role") or "advisor").strip().lower() or "advisor"
    if role != "advisor":
        raise ValueError("live_smoke_expected_local_role_must_be_advisor")

    evidence = tuple(
        str(x) for x in (payload.get("evidence_refs") or ()) if str(x).strip()
    )
    if not evidence:
        evidence = (
            f"live_smoke:{task_id}:spec",
            f"live_smoke:{task_id}:allowed_files",
        )

    snapshot = dict(payload.get("planner_snapshot") or {})
    model = str(
        snapshot.get("executor_model")
        or payload.get("local_model")
        or default_model
    ).strip()
    snapshot.setdefault("route_truth_source", "CapabilityPlanner")
    snapshot.setdefault("execution_topology", "single_local_model")
    snapshot.setdefault("protocol_mode", "unified_diff")
    snapshot.setdefault("model_call_allowed", True)
    snapshot.setdefault("executor_provider", "ollama")
    snapshot["executor_model"] = model

    target = str(payload.get("target_file") or allowed[0]).strip()
    timeout = float(payload.get("timeout_sec") or payload.get("time_budget") or 120.0)

    return LocalAssistRequest(
        schema=REQUEST_SCHEMA,
        task_id=task_id,
        parent_task_id=str(payload.get("parent_task_id") or task_id),
        workspace_root=str(Path(root).expanduser()),
        workspace_revision=revision,
        task_statement=statement,
        action=resolved_action,
        allowed_files=allowed,
        target_file=target,
        target_symbol=str(payload.get("target_symbol") or ""),
        evidence_refs=evidence,
        verifier_command=(),
        risk_budget=str(payload.get("risk_budget") or "low"),
        time_budget=timeout,
        requested_role="advisor",
        mutation_policy="isolated_only",
        planner_snapshot=snapshot,
        locked_search=str(payload.get("locked_search") or ""),
    )


def load_local_assist_payload(
    path: str | Path,
    *,
    workspace_root: str | Path | None = None,
    action: str | None = None,
) -> LocalAssistRequest:
    """Load either request.v1 or live_smoke_task.v1 from disk into LocalAssistRequest."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("request_must_be_object")
    if is_live_smoke_payload(payload):
        request = translate_live_smoke_to_request(
            payload,
            workspace_root=workspace_root,
            action=action,
        )
    else:
        from nexus.services.local_assist_service import LocalAssistRequest as LAR

        request = LAR.from_dict(payload)
        if workspace_root is not None:
            from dataclasses import replace

            request = replace(request, workspace_root=str(Path(workspace_root).expanduser()))
        if action is not None:
            from dataclasses import replace

            request = replace(
                request,
                action=str(action),
                requested_role="advisor" if str(action) == "advisor" else request.requested_role,
            )
    request.validate()
    return request
