"""Final campaign evidence gate; never converts partial evidence into product claims."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


REQUIRED_FINAL_EVIDENCE = (
    "explicit_advisor",
    "explicit_candidate",
    "explicit_verified_subtask",
    "planner_advisor",
    "planner_candidate",
    "planner_verified_subtask",
    "local_only_fallback",
    "real_cloud_local_runtime",
    "quota_constrained_degradation",
    "provider_unavailable_fail_closed",
    "contribution_attribution",
    "value_measurement",
    "universal_agent_interface",
    "canonical_cli_integration",
    "all_focused_tests_pass",
    "critical_fail_closed_paths_pass",
    "receipt_lineage_complete",
    "no_route_split",
    "no_verifier_weakening",
    "no_candidate_isolation_bypass",
)


def evaluate_final_gate(
    evidence: Mapping[str, bool],
    *,
    blockers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    observed = {key: bool(evidence.get(key, False)) for key in REQUIRED_FINAL_EVIDENCE}
    blocking = [key for key, passed in observed.items() if not passed]
    status = "PASSED" if not blocking else "BLOCKED"
    return {
        "schema": "nexus.local_assist.final_gate.v1",
        "status": status,
        "terminal_claim": "NEXUS_UNIVERSAL_LOCAL_ASSIST_PRODUCTIZED" if status == "PASSED" else "",
        "required_evidence": observed,
        "blocking_requirements": blocking,
        "blocker_reasons": {key: str((blockers or {}).get(key, "evidence_missing")) for key in blocking},
        "claim_boundary": {
            "selected": observed.get("universal_agent_interface", False),
            "invoked": observed.get("explicit_advisor", False) or observed.get("planner_advisor", False),
            "outcome_contributed": observed.get("contribution_attribution", False),
            "value_measured": observed.get("value_measurement", False),
            "production_ready": False,
            "public_claim_allowed": False,
            "internal_only": True,
        },
    }


def write_final_gate(path: str | Path, result: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(dict(result), indent=2, sort_keys=True), encoding="utf-8")
    return destination
