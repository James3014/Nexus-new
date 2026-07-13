"""Nexus-owned Online execution authorization (product gate).

Environment variable NEXUS_EXTERNAL_RUNTIME_AUTHORIZED remains an emergency
override source only — never the sole product mechanism, and never implied by
provider credentials alone.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

ONLINE_POLICIES = frozenset({"deny", "auto", "require"})
AUTH_SOURCES = frozenset(
    {
        "cli_task_policy",
        "workspace_policy",
        "operator_environment_override",
        "injected_test_transport",
        "fail_closed_default",
    }
)

ONLINE_READY = "ONLINE_READY"
ONLINE_NOT_REQUESTED = "ONLINE_NOT_REQUESTED"
ONLINE_DENIED_BY_POLICY = "ONLINE_DENIED_BY_POLICY"
ONLINE_PROVIDER_UNAVAILABLE = "ONLINE_PROVIDER_UNAVAILABLE"
ONLINE_PROVIDER_UNAUTHENTICATED = "ONLINE_PROVIDER_UNAUTHENTICATED"
ONLINE_CONTEXT_TRANSFER_DENIED = "ONLINE_CONTEXT_TRANSFER_DENIED"
ONLINE_BUDGET_EXCEEDED = "ONLINE_BUDGET_EXCEEDED"
ONLINE_CONFIGURATION_INVALID = "ONLINE_CONFIGURATION_INVALID"

DEFAULT_APPROVED_PROVIDERS = ("gemini", "grok", "codex", "openai")
WORKSPACE_POLICY_RELATIVE = Path(".nexus") / "online_execution_policy.json"
ENV_OVERRIDE = "NEXUS_EXTERNAL_RUNTIME_AUTHORIZED"


@dataclass(frozen=True)
class OnlineExecutionDecision:
    online_policy: str
    online_execution_requested: bool
    online_execution_authorized: bool
    online_authorization_source: str
    approved_online_providers: tuple[str, ...]
    preflight_status: str
    reason: str = ""
    allow_external_context_transfer: bool = True
    maximum_provider_calls: int = 10
    maximum_retry_count: int = 3
    requested_provider: str = ""
    physical_invocation_allowed: bool = False
    claim_boundary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["approved_online_providers"] = list(self.approved_online_providers)
        return payload


def normalize_online_policy(policy: str | None) -> str:
    raw = str(policy or "").strip().lower()
    if not raw:
        return "deny"
    if raw not in ONLINE_POLICIES:
        raise ValueError("invalid_online_policy")
    return raw


def load_workspace_online_policy(project_root: str | Path) -> dict[str, Any]:
    path = Path(project_root).expanduser() / WORKSPACE_POLICY_RELATIVE
    if not path.is_file():
        return {
            "default_online_policy": "deny",
            "approved_online_providers": list(DEFAULT_APPROVED_PROVIDERS),
            "allow_external_context_transfer": True,
            "maximum_provider_calls": 10,
            "maximum_retry_count": 3,
            "policy_path": str(path),
            "policy_present": False,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "default_online_policy": "deny",
            "approved_online_providers": list(DEFAULT_APPROVED_PROVIDERS),
            "allow_external_context_transfer": True,
            "maximum_provider_calls": 10,
            "maximum_retry_count": 3,
            "policy_path": str(path),
            "policy_present": False,
            "policy_error": "invalid_json",
        }
    if not isinstance(data, Mapping):
        data = {}
    providers = data.get("approved_online_providers") or list(DEFAULT_APPROVED_PROVIDERS)
    return {
        "default_online_policy": str(data.get("default_online_policy") or "deny").strip().lower(),
        "approved_online_providers": [str(p).strip().lower() for p in providers if str(p).strip()],
        "allow_external_context_transfer": bool(data.get("allow_external_context_transfer", True)),
        "maximum_provider_calls": int(data.get("maximum_provider_calls", 10) or 10),
        "maximum_retry_count": int(data.get("maximum_retry_count", 3) or 3),
        "policy_path": str(path),
        "policy_present": True,
    }


def build_online_execution_context_fields(
    *,
    online_policy: str = "deny",
    project_root: str | Path = ".",
    task_id: str = "",
    workspace_revision: str = "",
    policy_source: str = "cli",
) -> dict[str, Any]:
    """Fields for TaskRequest.execution_context propagation."""
    policy = normalize_online_policy(online_policy)
    decision = resolve_online_execution_decision(
        task_online_policy=policy,
        project_root=project_root,
        planner_online_needed=policy in {"auto", "require"},
        injected_transport=False,
    )
    return {
        "online_policy": policy,
        "online_execution_requested": bool(decision.online_execution_requested),
        "online_execution_authorized": bool(decision.online_execution_authorized),
        "online_authorization_source": decision.online_authorization_source,
        "approved_online_providers": list(decision.approved_online_providers),
        "online_preflight_status": decision.preflight_status,
        "online_policy_source": str(policy_source or "cli"),
        "task_id": str(task_id or ""),
        "workspace_revision": str(workspace_revision or ""),
        "online_execution_decision": decision.to_dict(),
    }


def resolve_online_execution_decision(
    *,
    task_online_policy: str = "",
    project_root: str | Path = ".",
    workspace_policy: Mapping[str, Any] | None = None,
    planner_online_needed: bool = True,
    injected_transport: bool = False,
    requested_provider: str = "",
    provider_call_count_so_far: int = 0,
    environ: Mapping[str, str] | None = None,
    allow_context_transfer: bool | None = None,
) -> OnlineExecutionDecision:
    """Resolve Online authorization once (fail-closed).

    Precedence:
      explicit task deny
      > injected test transport (non-physical / fixture path only)
      > explicit task auto|require
      > workspace policy
      > emergency environment override
      > fail-closed default
    """
    env = dict(environ or os.environ)
    ws = dict(workspace_policy) if isinstance(workspace_policy, Mapping) else load_workspace_online_policy(project_root)
    approved = tuple(
        str(p).strip().lower()
        for p in (ws.get("approved_online_providers") or DEFAULT_APPROVED_PROVIDERS)
        if str(p).strip()
    )
    transfer_ok = (
        bool(allow_context_transfer)
        if allow_context_transfer is not None
        else bool(ws.get("allow_external_context_transfer", True))
    )
    max_calls = int(ws.get("maximum_provider_calls", 10) or 10)
    max_retries = int(ws.get("maximum_retry_count", 3) or 3)
    provider = str(requested_provider or "").strip().lower()
    claim = {
        "public_claim_allowed": False,
        "production_ready": False,
        "credentials_do_not_imply_authorization": True,
    }

    # 1) Task deny always wins.
    task_raw = str(task_online_policy or "").strip().lower()
    if task_raw == "deny":
        return OnlineExecutionDecision(
            online_policy="deny",
            online_execution_requested=False,
            online_execution_authorized=False,
            online_authorization_source="cli_task_policy",
            approved_online_providers=approved,
            preflight_status=ONLINE_DENIED_BY_POLICY,
            reason="task_online_policy_deny",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    # 2) Injected structured/test transport: authorize fixture path only.
    if injected_transport:
        return OnlineExecutionDecision(
            online_policy=task_raw if task_raw in ONLINE_POLICIES else "auto",
            online_execution_requested=True,
            online_execution_authorized=True,
            online_authorization_source="injected_test_transport",
            approved_online_providers=approved,
            preflight_status=ONLINE_READY,
            reason="injected_transport_authorized",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider or "injected",
            physical_invocation_allowed=False,  # fixtures only; real CLI still needs non-injected auth
            claim_boundary=claim,
        )

    # Resolve effective policy string (task > workspace > deny).
    source = "fail_closed_default"
    policy = "deny"
    if task_raw in {"auto", "require"}:
        policy = task_raw
        source = "cli_task_policy"
    else:
        ws_policy = str(ws.get("default_online_policy") or "deny").strip().lower()
        if ws_policy in ONLINE_POLICIES:
            policy = ws_policy
            source = "workspace_policy" if ws.get("policy_present") else "fail_closed_default"
        env_override = str(env.get(ENV_OVERRIDE, "") or "").strip() == "1"
        if env_override and policy == "deny":
            # Emergency override elevates to auto when no stronger task/workspace deny.
            policy = "auto"
            source = "operator_environment_override"

    env_override = str(env.get(ENV_OVERRIDE, "") or "").strip() == "1"
    if env_override and source == "fail_closed_default":
        policy = "auto"
        source = "operator_environment_override"

    requested = False
    if policy == "require":
        requested = True
    elif policy == "auto":
        requested = bool(planner_online_needed)
    else:
        requested = False

    if not requested:
        return OnlineExecutionDecision(
            online_policy=policy,
            online_execution_requested=False,
            online_execution_authorized=False,
            online_authorization_source=source,
            approved_online_providers=approved,
            preflight_status=ONLINE_NOT_REQUESTED,
            reason="online_not_requested_by_policy_or_planner",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    if not transfer_ok:
        return OnlineExecutionDecision(
            online_policy=policy,
            online_execution_requested=True,
            online_execution_authorized=False,
            online_authorization_source=source,
            approved_online_providers=approved,
            preflight_status=ONLINE_CONTEXT_TRANSFER_DENIED,
            reason="external_context_transfer_denied",
            allow_external_context_transfer=False,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    if provider_call_count_so_far >= max_calls:
        return OnlineExecutionDecision(
            online_policy=policy,
            online_execution_requested=True,
            online_execution_authorized=False,
            online_authorization_source=source,
            approved_online_providers=approved,
            preflight_status=ONLINE_BUDGET_EXCEEDED,
            reason="maximum_provider_calls_exceeded",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    if provider and provider not in approved and provider not in {"injected", "gateway", "fixture", "fixture_gateway"}:
        status = ONLINE_PROVIDER_UNAVAILABLE if policy == "require" else ONLINE_PROVIDER_UNAVAILABLE
        return OnlineExecutionDecision(
            online_policy=policy,
            online_execution_requested=True,
            online_execution_authorized=False,
            online_authorization_source=source,
            approved_online_providers=approved,
            preflight_status=status,
            reason=f"provider_not_approved:{provider}",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    # Physical real-provider invocation still requires a non-credential authorization
    # signal: task auto/require, workspace auto/require, or env override.
    physical_ok = source in {
        "cli_task_policy",
        "workspace_policy",
        "operator_environment_override",
    } and policy in {"auto", "require"}

    if not physical_ok:
        return OnlineExecutionDecision(
            online_policy=policy,
            online_execution_requested=True,
            online_execution_authorized=False,
            online_authorization_source=source,
            approved_online_providers=approved,
            preflight_status=ONLINE_DENIED_BY_POLICY,
            reason="no_online_authorization_signal",
            allow_external_context_transfer=transfer_ok,
            maximum_provider_calls=max_calls,
            maximum_retry_count=max_retries,
            requested_provider=provider,
            physical_invocation_allowed=False,
            claim_boundary=claim,
        )

    return OnlineExecutionDecision(
        online_policy=policy,
        online_execution_requested=True,
        online_execution_authorized=True,
        online_authorization_source=source,
        approved_online_providers=approved,
        preflight_status=ONLINE_READY,
        reason="online_execution_authorized",
        allow_external_context_transfer=transfer_ok,
        maximum_provider_calls=max_calls,
        maximum_retry_count=max_retries,
        requested_provider=provider,
        physical_invocation_allowed=True,
        claim_boundary=claim,
    )


def decision_from_context(context: Mapping[str, Any] | None) -> OnlineExecutionDecision | None:
    """Extract a previously resolved decision from invoker context / request route."""
    if not isinstance(context, Mapping):
        return None
    raw = context.get("online_execution_decision")
    if isinstance(raw, OnlineExecutionDecision):
        return raw
    if isinstance(raw, Mapping) and raw.get("online_policy"):
        try:
            return OnlineExecutionDecision(
                online_policy=str(raw.get("online_policy") or "deny"),
                online_execution_requested=bool(raw.get("online_execution_requested")),
                online_execution_authorized=bool(raw.get("online_execution_authorized")),
                online_authorization_source=str(raw.get("online_authorization_source") or "fail_closed_default"),
                approved_online_providers=tuple(raw.get("approved_online_providers") or DEFAULT_APPROVED_PROVIDERS),
                preflight_status=str(raw.get("preflight_status") or ONLINE_DENIED_BY_POLICY),
                reason=str(raw.get("reason") or ""),
                allow_external_context_transfer=bool(raw.get("allow_external_context_transfer", True)),
                maximum_provider_calls=int(raw.get("maximum_provider_calls", 10) or 10),
                maximum_retry_count=int(raw.get("maximum_retry_count", 3) or 3),
                requested_provider=str(raw.get("requested_provider") or ""),
                physical_invocation_allowed=bool(raw.get("physical_invocation_allowed")),
                claim_boundary=dict(raw.get("claim_boundary") or {}),
            )
        except (TypeError, ValueError):
            return None
    # Fallback fields on context/route
    if "online_execution_authorized" in context:
        authorized = bool(context.get("online_execution_authorized"))
        return OnlineExecutionDecision(
            online_policy=str(context.get("online_policy") or "deny"),
            online_execution_requested=bool(context.get("online_execution_requested", authorized)),
            online_execution_authorized=authorized,
            online_authorization_source=str(context.get("online_authorization_source") or "fail_closed_default"),
            approved_online_providers=tuple(context.get("approved_online_providers") or DEFAULT_APPROVED_PROVIDERS),
            preflight_status=str(context.get("online_preflight_status") or (ONLINE_READY if authorized else ONLINE_DENIED_BY_POLICY)),
            reason=str(context.get("online_auth_reason") or ""),
            physical_invocation_allowed=authorized and str(context.get("online_authorization_source") or "") != "injected_test_transport",
            claim_boundary={"public_claim_allowed": False},
        )
    return None


def physical_online_authorized(context: Mapping[str, Any] | None, *, injected_transport: bool = False) -> bool:
    """Adapter enforcement helper: real provider subprocesses only when physical allowed."""
    if injected_transport:
        return True
    decision = decision_from_context(context)
    if decision is not None:
        return bool(decision.online_execution_authorized and decision.physical_invocation_allowed)
    # Legacy emergency only — product path should always attach a decision.
    return os.environ.get(ENV_OVERRIDE, "").strip() == "1"
