"""Provider-neutral Agent-facing Local Assist interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from nexus.engine.capability_planner import CapabilityPlanner


AGENT_INTERFACE_SCHEMA = "nexus.local_assist.agent_interface.v1"
AVAILABLE_ACTIONS = ["skip", "advisor", "candidate", "verified-subtask"]


def build_universal_agent_interface(task: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(task or {})
    task_id = str(payload.get("task_id", "")).strip()
    workspace_revision = str(payload.get("workspace_revision", "")).strip()
    task_statement = str(payload.get("task_statement", "")).strip()
    task_type = str(payload.get("task_type", "")).strip()
    if not task_id:
        raise ValueError("task_id_missing")
    if not workspace_revision:
        raise ValueError("workspace_revision_missing")
    if not task_statement:
        raise ValueError("task_statement_missing")
    if not task_type:
        raise ValueError("task_type_missing")
    route = payload.get("route", {})
    if not isinstance(route, Mapping):
        raise ValueError("route_must_be_object")
    plan = CapabilityPlanner().plan(
        task_desc=task_statement,
        task_type=task_type,
        route=dict(route),
        pillars=dict(payload.get("pillars", {}) or {}),
        codeintel=dict(payload.get("codeintel", {}) or {}),
        budget={"max_cost": 100},
    )
    recommendation = dict(plan.signal_snapshot["local_assist_recommendation"])
    return {
        "schema": AGENT_INTERFACE_SCHEMA,
        "provider_neutral": True,
        "task_identity": {
            "task_id": task_id,
            "parent_task_id": str(payload.get("parent_task_id", "")),
            "workspace_revision": workspace_revision,
            "task_type": task_type,
        },
        "planner_recommendation": recommendation,
        "available_actions": list(AVAILABLE_ACTIONS),
        "assist_envelope": {
            "schema": "nexus.local_assist.envelope.v1",
            "task_statement": task_statement,
            "allowed_files": [str(item) for item in (payload.get("allowed_files", []) or [])],
            "target_file": str(payload.get("target_file", "")),
            "target_symbol": str(payload.get("target_symbol", "")),
            "evidence_refs": [str(item) for item in (payload.get("evidence_refs", []) or [])],
            "receipt_paths": [],
            "candidate_identities": [],
            "verification_result": {"status": "not_run"},
        },
        "consumption_contract": {
            "schema": "nexus.local_assist.consumption.v1",
            "required_receipt_fields": ["task_id", "output_hash", "terminal_status"],
            "direct_output_evidence_required": True,
            "receipt_only_insufficient": True,
            "output_consumed": False,
        },
        "contribution_contract": {
            "schema": "nexus.local_assist.contribution.v1",
            "outcome_contributed": False,
            "contribution_type": "",
            "evidence_refs": [],
            "accepted_content_hashes": [],
            "counterfactual_available": False,
            "confidence": 0.0,
        },
        "claim_boundary": {
            "selected": True,
            "invoked": False,
            "output_delivered": False,
            "output_consumed": False,
            "outcome_contributed": False,
            "value_measured": False,
            "production_ready": False,
            "public_claim_allowed": False,
            "internal_only": True,
        },
        "route_truth_source": "CapabilityPlanner",
    }


def load_universal_agent_task(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_universal_agent_interface(payload)


def render_machine_readable_interface(interface: Mapping[str, Any]) -> str:
    return json.dumps(dict(interface), indent=2, sort_keys=True, ensure_ascii=False)


def write_universal_agent_interface(path: str | Path, interface: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_machine_readable_interface(interface) + "\n", encoding="utf-8")
    return destination
