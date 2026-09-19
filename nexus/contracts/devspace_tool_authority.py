from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

TOOL_AUTHORITY_SCHEMA = "nexus.devspace.tool_authority.v1"
TOOL_AUTHORITY_POLICY_SCHEMA = "nexus.devspace.tool_authority_policy.v1"
TOOL_INTENT_NAMESPACE = "devspace.tool_intent.v1"
TOOL_PROJECTION_MANIFEST_SCHEMA = "devspace.tool_projection_manifest.v1"
CANONICAL_DISPATCH_ENVELOPE_SCHEMA = "nexus.canonical_dispatch_envelope.v1"

CANONICAL_TOOL_INTENTS = (
    "workspace.read",
    "workspace.search_text",
    "workspace.search_paths",
    "workspace.list",
    "workspace.mutate",
    "process.execute",
)

_EFFECT_TOOL_POLICY = {
    "READ_ONLY": CANONICAL_TOOL_INTENTS[:4],
    "WORKSPACE_MUTATION": CANONICAL_TOOL_INTENTS,
    "CANDIDATE": CANONICAL_TOOL_INTENTS,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_tool_authority_policy(policy: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(dict(policy)).encode("utf-8")).hexdigest()


def tool_authority_policy() -> dict[str, Any]:
    return {
        "schema": TOOL_AUTHORITY_POLICY_SCHEMA,
        "namespace": TOOL_INTENT_NAMESPACE,
        "effectCeilings": {
            name: list(values)
            for name, values in _EFFECT_TOOL_POLICY.items()
        },
    }


def tool_authority_policy_hash() -> str:
    return hash_tool_authority_policy(tool_authority_policy())


def _require_hex64(value: Any, field: str) -> str:
    text = str(value or "")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field}_invalid")
    return text


def _envelope_payload(envelope: Mapping[str, Any] | object) -> Mapping[str, Any]:
    if isinstance(envelope, Mapping):
        payload = envelope
    elif callable(getattr(envelope, "to_dict", None)):
        payload = getattr(envelope, "to_dict")()
    else:
        payload = {
            name: getattr(envelope, name, None)
            for name in ("schema", "task_id", "attempt_id", "planner_decision_hash", "planner_plan_hash")
        }
    if payload.get("schema") != CANONICAL_DISPATCH_ENVELOPE_SCHEMA:
        raise ValueError("canonical_dispatch_envelope_schema_invalid")
    if not str(payload.get("task_id") or "").strip():
        raise ValueError("canonical_dispatch_task_id_missing")
    if not str(payload.get("attempt_id") or "").strip():
        raise ValueError("canonical_dispatch_attempt_id_missing")
    _require_hex64(payload.get("planner_decision_hash"), "planner_decision_hash")
    _require_hex64(payload.get("planner_plan_hash"), "planner_plan_hash")
    return payload


def canonicalize_tool_intents(values: Iterable[str], *, field: str = "tool_intents") -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{field}_invalid")
    raw = [str(value) for value in values]
    if len(raw) != len(set(raw)):
        raise ValueError(f"{field}_duplicate")
    unknown = [value for value in raw if value not in CANONICAL_TOOL_INTENTS]
    if unknown:
        raise ValueError(f"{field}_unknown:{unknown[0]}")
    present = set(raw)
    return tuple(value for value in CANONICAL_TOOL_INTENTS if value in present)


def _validate_tool_authority(
    authority: Mapping[str, Any],
    *,
    envelope: Mapping[str, Any] | object | None = None,
) -> dict[str, Any]:
    payload = dict(authority)
    if payload.get("schema") != TOOL_AUTHORITY_SCHEMA:
        raise ValueError("tool_authority_schema_invalid")
    if payload.get("namespace") != TOOL_INTENT_NAMESPACE:
        raise ValueError("tool_authority_namespace_invalid")
    decision_hash = _require_hex64(payload.get("plannerDecisionHash"), "planner_decision_hash")
    plan_hash = _require_hex64(payload.get("plannerPlanHash"), "planner_plan_hash")
    policy_hash = _require_hex64(payload.get("policyHash"), "tool_authority_policy_hash")
    if policy_hash != tool_authority_policy_hash():
        raise ValueError("tool_authority_policy_hash_mismatch")
    ceiling = canonicalize_tool_intents(
        payload.get("authorizedToolCeiling") or (),
        field="authorized_tool_ceiling",
    )
    if ceiling not in set(_EFFECT_TOOL_POLICY.values()):
        raise ValueError("authorized_tool_ceiling_not_policy_derived")
    if envelope is not None:
        bound = _envelope_payload(envelope)
        if decision_hash != bound["planner_decision_hash"]:
            raise ValueError("tool_authority_planner_decision_mismatch")
        if plan_hash != bound["planner_plan_hash"]:
            raise ValueError("tool_authority_planner_plan_mismatch")
    return {
        "schema": TOOL_AUTHORITY_SCHEMA,
        "namespace": TOOL_INTENT_NAMESPACE,
        "plannerDecisionHash": decision_hash,
        "plannerPlanHash": plan_hash,
        "policyHash": policy_hash,
        "authorizedToolCeiling": list(ceiling),
    }


def build_governed_tool_authority(
    envelope: Mapping[str, Any] | object,
    effect_ceiling: str,
) -> dict[str, Any]:
    bound = _envelope_payload(envelope)
    if effect_ceiling not in _EFFECT_TOOL_POLICY:
        raise ValueError(f"effect_ceiling_unknown:{effect_ceiling}")
    authority = {
        "schema": TOOL_AUTHORITY_SCHEMA,
        "namespace": TOOL_INTENT_NAMESPACE,
        "plannerDecisionHash": bound["planner_decision_hash"],
        "plannerPlanHash": bound["planner_plan_hash"],
        "policyHash": tool_authority_policy_hash(),
        "authorizedToolCeiling": list(_EFFECT_TOOL_POLICY[effect_ceiling]),
    }
    return _validate_tool_authority(authority, envelope=bound)


def build_tool_projection_manifest(
    envelope: Mapping[str, Any] | object,
    authority: Mapping[str, Any],
    *,
    candidate_tools: Iterable[str],
    selected_tools: Iterable[str],
) -> dict[str, Any]:
    bound = _envelope_payload(envelope)
    normalized_authority = _validate_tool_authority(authority, envelope=bound)
    ceiling = tuple(normalized_authority["authorizedToolCeiling"])
    candidates = canonicalize_tool_intents(candidate_tools, field="candidate_tools")
    selected = canonicalize_tool_intents(selected_tools, field="selected_tools")
    if not set(candidates).issubset(ceiling):
        raise ValueError("candidate_tools_exceed_authorized_ceiling")
    if not set(selected).issubset(candidates):
        raise ValueError("selected_tools_exceed_candidate_tools")
    return {
        "schema": TOOL_PROJECTION_MANIFEST_SCHEMA,
        "namespace": TOOL_INTENT_NAMESPACE,
        "identity": {
            "taskId": str(bound["task_id"]),
            "attemptId": str(bound["attempt_id"]),
        },
        "authority": {"mode": "NEXUS_GOVERNED", "issuer": "nexus"},
        "authorizedToolCeiling": list(ceiling),
        "candidateTools": list(candidates),
        "selectedTools": list(selected),
        "orderingMode": "ORDER_INDEPENDENT",
    }


def build_tool_authority_fragment(authority: Mapping[str, Any]) -> dict[str, Any]:
    return {"toolAuthority": _validate_tool_authority(authority)}
