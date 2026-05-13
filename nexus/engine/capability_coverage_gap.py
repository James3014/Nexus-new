from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.engine.capability_planner import PENDING_EXECUTOR_CAPABILITIES, default_capability_nodes


RESERVED_CAPABILITIES = {
    "autonomic_router": "reserved_until_planner_ssot_migration",
    "learn_scheduler": "reserved_until_scheduler_freshness_signals",
}

RULED_CAPABILITIES = {
    "acceptance_check",
    "artifact_gate",
    "architecture_scout",
    "autoreason",
    "asi_constraint_extractor",
    "benchmark",
    "bdd_acceptance_skill",
    "belief",
    "claim_gate",
    "codeintel",
    "ddtree",
    "delivery_gate",
    "direct_mode",
    "drone",
    "external_doc_scout",
    "federation",
    "file_lock",
    "forecast_gate",
    "formal_report",
    "harness_preflight_sensor",
    "hyper",
    "integration_manager",
    "jit_validation",
    "judge_panel",
    "lancedb",
    "learn_mode",
    "learn_phase_slo",
    "llm_judge_panel",
    "memory",
    "mempalace_gate",
    "meta_opt",
    "metabolism",
    "msa_router",
    "multi_agent",
    "nightshift",
    "oracle_shadow",
    "plan_quality_gate",
    "pregate",
    "registry_sync",
    "repair_loop",
    "research",
    "research_control_plane",
    "research_route",
    "sandbox",
    "semantic_searcher",
    "semantic_failure_sensor",
    "stress_test",
    "swarm",
    "swarm_quiet_moment",
    "ui_validator",
    "ultra_review",
    "xray",
}


def build_capability_coverage_gap_report() -> dict[str, Any]:
    nodes = default_capability_nodes()
    unruled = sorted(set(nodes) - RULED_CAPABILITIES - set(RESERVED_CAPABILITIES))
    return {
        "schema_version": "nexus_capability_coverage_gap_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registered_count": len(nodes),
        "ruled_count": len([name for name in nodes if name in RULED_CAPABILITIES]),
        "reserved_count": len([name for name in nodes if name in RESERVED_CAPABILITIES]),
        "pending_executor_count": len([name for name in nodes if name in PENDING_EXECUTOR_CAPABILITIES]),
        "unruled_count": len(unruled),
        "unruled_capabilities": unruled,
        "reserved_capabilities": [
            {"capability": name, "reason": RESERVED_CAPABILITIES[name]}
            for name in sorted(set(nodes) & set(RESERVED_CAPABILITIES))
        ],
        "pending_executor_capabilities": sorted(set(nodes) & PENDING_EXECUTOR_CAPABILITIES),
    }


def write_capability_coverage_gap_report(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_capability_coverage_gap_report(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path
