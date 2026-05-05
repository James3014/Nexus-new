from __future__ import annotations

from typing import Any

from nexus.engine.autoreason_service import AutoreasonService
from nexus.engine.capability_planner import default_capability_nodes
from nexus.engine.ddtree_adapter import DDTreeAdapter
from nexus.engine.ultra_review_service import UltraReviewService


CORE_CAPABILITIES = (
    "codeintel",
    "research",
    "hyper",
    "nightshift",
    "swarm",
    "drone",
    "ultra_review",
    "autoreason",
    "ddtree",
    "memory",
    "lancedb",
    "semantic_searcher",
    "belief",
    "swarm_quiet_moment",
    "mempalace_gate",
    "artifact_gate",
    "claim_gate",
    "delivery_gate",
)


def build_benchmark_capability_readiness(args: Any) -> dict[str, Any]:
    """Preflight whether a public benchmark can claim Nexus capability execution."""

    nodes = default_capability_nodes()
    missing_nodes = [name for name in CORE_CAPABILITIES if name not in nodes]
    executor_classes = {
        "autoreason": AutoreasonService.__name__,
        "ddtree": DDTreeAdapter.__name__,
        "ultra_review": UltraReviewService.__name__,
    }
    failures: list[str] = []
    warnings: list[str] = []
    failures.extend(f"missing_capability_node:{name}" for name in missing_nodes)

    with_llm_mode = str(getattr(args, "with_llm_mode", "off") or "off")
    provider = str(getattr(args, "with_model_provider", "gemini") or "gemini")
    runner = str(getattr(args, "with_nexus_runner", "inprocess") or "inprocess")
    public_model_benchmark = with_llm_mode in {"hard", "all"}
    if public_model_benchmark:
        if runner != "subprocess":
            failures.append("nexus_subprocess_runner_required_for_executor_evidence")
        if provider == "codex":
            warnings.append("direct_codex_provider_is_prompt_wearing_only_for_external_model_claims")
        if not bool(getattr(args, "enable_autoreason_executor", False)):
            failures.append("autoreason_executor_flag_missing")
        if not bool(getattr(args, "enable_ddtree_executor", False)):
            failures.append("ddtree_executor_flag_missing")
        if int(getattr(args, "llm_candidate_cap", 1) or 1) < 3:
            failures.append("llm_candidate_cap_below_ddtree_threshold")
        if not bool(getattr(args, "enable_ultra_review_dry_gate", False)):
            failures.append("ultra_review_dry_gate_flag_missing")
    else:
        warnings.append("model_benchmark_disabled")

    required_flags = {
        "with_nexus_runner": "subprocess",
        "enable_autoreason_executor": True,
        "enable_ddtree_executor": True,
        "enable_ultra_review_dry_gate": True,
        "llm_candidate_cap_min": 3,
    }
    return {
        "schema": "nexus_benchmark_capability_readiness_v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "capability_registry": {
            "core_capabilities": list(CORE_CAPABILITIES),
            "registered_count": len(nodes),
            "missing": missing_nodes,
        },
        "executor_contracts": executor_classes,
        "required_flags_for_public_model_benchmark": required_flags,
        "observed_flags": {
            "with_llm_mode": with_llm_mode,
            "with_model_provider": provider,
            "with_nexus_runner": runner,
            "enable_autoreason_executor": bool(getattr(args, "enable_autoreason_executor", False)),
            "enable_ddtree_executor": bool(getattr(args, "enable_ddtree_executor", False)),
            "enable_ultra_review_dry_gate": bool(getattr(args, "enable_ultra_review_dry_gate", False)),
            "llm_candidate_cap": int(getattr(args, "llm_candidate_cap", 1) or 1),
        },
    }
