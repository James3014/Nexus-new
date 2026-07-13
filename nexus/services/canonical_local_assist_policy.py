"""Canonical Nexus run policy selector for Local Assist.

Gate 2 canonical modes: disabled | shadow | advisor.
Legacy aliases (receipt-recorded): planner→shadow, explicit→advisor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_universal_interface import AVAILABLE_ACTIONS, build_universal_agent_interface

CANONICAL_MODES = frozenset({"disabled", "shadow", "advisor"})
LEGACY_ALIASES: dict[str, str] = {
    "planner": "shadow",
    "explicit": "advisor",
}
# Accepted CLI / receipt inputs (canonical + legacy).
POLICIES = frozenset(set(CANONICAL_MODES) | set(LEGACY_ALIASES))


def normalize_local_assist_policy(policy: str) -> dict[str, Any]:
    """Normalize raw policy input to canonical task-level fields.

    Environment variables must not replace this explicit task policy.
    """
    raw = str(policy or "").strip().lower()
    if raw not in POLICIES:
        raise ValueError("invalid_local_assist_policy")
    legacy = raw if raw in LEGACY_ALIASES else ""
    canonical = LEGACY_ALIASES.get(raw, raw)
    migration_warning = (
        f"local_assist_policy '{legacy}' is a deprecated alias of '{canonical}'"
        if legacy
        else ""
    )
    return {
        "raw_policy": raw,
        "canonical_policy": canonical,
        "local_assist_mode": canonical,
        "legacy_policy_alias": legacy or None,
        "migration_warning": migration_warning,
        "local_assist_requested": canonical != "disabled",
        "local_assist_policy_source": "task_request",
        "automatic_dispatch": False,
        # Only advisor may change runtime behavior (Local stage invocation).
        "runtime_behavior_changed": canonical == "advisor",
        "formal_workspace_mutated": False,
    }


def build_execution_context_fields(
    *,
    policy: str,
    task_id: str,
    workspace_revision: str,
    policy_source: str = "cli",
) -> dict[str, Any]:
    """Fields to thread through TaskRequest.execution_context → engine metadata."""
    normalized = normalize_local_assist_policy(policy)
    return {
        "local_assist_mode": normalized["canonical_policy"],
        "local_assist_requested": bool(normalized["local_assist_requested"]),
        "local_assist_policy_source": str(policy_source or "cli"),
        "local_assist_policy_raw": normalized["raw_policy"],
        "legacy_policy_alias": normalized["legacy_policy_alias"],
        "migration_warning": normalized["migration_warning"],
        "automatic_dispatch": False,
        "runtime_behavior_changed": bool(normalized["runtime_behavior_changed"]),
        "task_id": str(task_id or ""),
        "workspace_revision": str(workspace_revision or ""),
    }


def build_canonical_policy_receipt(*, policy: str, task: Mapping[str, Any]) -> dict[str, Any]:
    """Build a durable Local Assist policy receipt for CLI / pipeline linkage."""
    normalized = normalize_local_assist_policy(policy)
    canonical = str(normalized["canonical_policy"])
    base: dict[str, Any] = {
        "schema": "nexus.local_assist.canonical_policy.v1",
        "policy": normalized["raw_policy"],
        "canonical_policy": canonical,
        "local_assist_mode": canonical,
        "legacy_policy_alias": normalized["legacy_policy_alias"],
        "migration_warning": normalized["migration_warning"],
        "task_id": str(task.get("task_id", "")),
        "workspace_revision": str(task.get("workspace_revision", "")),
        "available_actions": list(AVAILABLE_ACTIONS),
        "automatic_dispatch": False,
        "recommendation_visible_before_dispatch": canonical == "shadow",
        "runtime_behavior_changed": canonical == "advisor",
        "formal_workspace_mutated": False,
        "route_truth_source": "CapabilityPlanner",
        "claim_boundary": {
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }
    if canonical == "shadow":
        interface = build_universal_agent_interface(task)
        base["planner_recommendation"] = interface["planner_recommendation"]
        base["assist_envelope"] = interface["assist_envelope"]
    else:
        base["planner_recommendation"] = None
    return base


def write_canonical_policy_receipt(path: str | Path, receipt: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(receipt), indent=2, sort_keys=True), encoding="utf-8")
    return destination


def collect_bounded_allowed_files(metadata: Mapping[str, Any], task_desc: str = "") -> list[str]:
    """Derive non-empty allowed_files from existing task evidence only."""
    files: list[str] = []
    for key in ("target_files", "plan_target_files", "allowed_files"):
        value = metadata.get(key)
        if isinstance(value, (list, tuple)):
            files.extend(str(item).strip() for item in value if str(item).strip())
    single = metadata.get("target_file")
    if single:
        files.append(str(single).strip())
    if task_desc:
        try:
            from nexus.engine.direct_mode import extract_target_files

            files.extend(str(item).strip() for item in extract_target_files(task_desc) if str(item).strip())
        except Exception:
            pass
    # Relative paths only; drop empties and duplicates while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for item in files:
        raw = item.replace("\\", "/").strip()
        if not raw or raw.startswith("/"):
            continue
        # Reject parent traversal before any strip that would erase ".."
        parts = Path(raw).parts
        if ".." in parts or parts[:1] == ("/",):
            continue
        path = str(Path(*parts)) if parts else ""
        if path.startswith("./"):
            path = path[2:]
        if not path or path in seen:
            continue
        seen.add(path)
        ordered.append(path)
    return ordered
