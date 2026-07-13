"""Canonical Nexus run policy selector for Local Assist."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.services.local_assist_universal_interface import AVAILABLE_ACTIONS, build_universal_agent_interface


POLICIES = {"planner", "explicit", "disabled"}


def build_canonical_policy_receipt(*, policy: str, task: Mapping[str, Any]) -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError("invalid_local_assist_policy")
    base = {
        "schema": "nexus.local_assist.canonical_policy.v1",
        "policy": policy,
        "task_id": str(task.get("task_id", "")),
        "workspace_revision": str(task.get("workspace_revision", "")),
        "available_actions": list(AVAILABLE_ACTIONS),
        "automatic_dispatch": False,
        "recommendation_visible_before_dispatch": policy == "planner",
        "runtime_behavior_changed": False,
        "formal_workspace_mutated": False,
        "route_truth_source": "CapabilityPlanner",
        "claim_boundary": {
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
        },
    }
    if policy == "planner":
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
