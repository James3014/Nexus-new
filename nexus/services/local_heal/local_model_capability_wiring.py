"""C0: Local model capability wiring audit.

Lists all 34 capabilities and their real status in the LocalModelExecutor path.
No selected capability can silently become metadata-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable


class CapabilityWiringStatus(str, Enum):
    EXECUTABLE = "executable"
    ADVISORY_EXECUTABLE = "advisory_executable"
    GATE_EXECUTABLE = "gate_executable"
    LOCALHEAL_EXECUTABLE = "localheal_executable"
    EXTERNAL_ONLY = "external_only"
    UNSUPPORTED = "unsupported"
    METADATA_ONLY = "metadata_only"


@dataclass(frozen=True)
class LocalModelCapabilityWiring:
    name: str
    registry_known: bool
    planner_known: bool
    runtime_module: str
    runtime_callable: str
    receipt_adapter: str
    local_model_supported: bool
    local_model_phase: str
    status: CapabilityWiringStatus
    reason: str


def build_local_model_capability_wiring() -> dict[str, LocalModelCapabilityWiring]:
    """Build wiring map for all 34 capabilities in LocalModelExecutor path."""
    from nexus.core.capability_registry import CapabilityRegistry

    registry = CapabilityRegistry()
    caps = {c.name: c for c in registry.list_all_capabilities()}

    wiring: dict[str, LocalModelCapabilityWiring] = {}

    # Capability name -> wiring definition
    _DEFINITIONS = {
        "local_model_executor": {
            "runtime_module": "nexus.services.local_heal.local_model_executor",
            "runtime_callable": "LocalModelExecutor.run",
            "receipt_adapter": "local_model_executor",
            "local_model_supported": True,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXECUTABLE,
            "reason": "Direct executor invocation via _finalize_with_nexus_row",
        },
        "autoreason": {
            "runtime_module": "nexus.engine.autoreason_service",
            "runtime_callable": "AutoreasonService.run",
            "receipt_adapter": "autoreason",
            "local_model_supported": True,
            "local_model_phase": "D",
            "status": CapabilityWiringStatus.ADVISORY_EXECUTABLE,
            "reason": "Service exists but not yet invoked in local path; candidate for C3",
        },
        "ddtree": {
            "runtime_module": "nexus.engine.ddtree_adapter",
            "runtime_callable": "DDTreeAdapter.plan",
            "receipt_adapter": "ddtree",
            "local_model_supported": True,
            "local_model_phase": "D",
            "status": CapabilityWiringStatus.ADVISORY_EXECUTABLE,
            "reason": "Adapter exists but not yet invoked in local path; candidate for C3",
        },
        "artifact_gate": {
            "runtime_module": "nexus.engine.capability_receipt_adapters",
            "runtime_callable": "ArtifactGateReceiptAdapter",
            "receipt_adapter": "artifact_gate",
            "local_model_supported": True,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.GATE_EXECUTABLE,
            "reason": "Receipt adapter exists; candidate for C4 gate execution",
        },
        "claim_gate": {
            "runtime_module": "nexus.services.local_heal.claim_delivery_gate",
            "runtime_callable": "validate_context_claim_delivery",
            "receipt_adapter": "claim_gate",
            "local_model_supported": True,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.GATE_EXECUTABLE,
            "reason": "Gate function exists; candidate for C4 gate execution",
        },
        "delivery_gate": {
            "runtime_module": "nexus.services.local_heal.claim_delivery_gate",
            "runtime_callable": "validate_context_claim_delivery",
            "receipt_adapter": "delivery_gate",
            "local_model_supported": True,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.GATE_EXECUTABLE,
            "reason": "Gate function exists; candidate for C4 gate execution",
        },
        "repair_loop": {
            "runtime_module": "nexus.services.local_heal.isolated_local_solve_loop",
            "runtime_callable": "run_isolated_local_solve_loop",
            "receipt_adapter": "",
            "local_model_supported": True,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.LOCALHEAL_EXECUTABLE,
            "reason": "Already invoked via isolated solve loop",
        },
        "learning_closure": {
            "runtime_module": "nexus.services.local_heal.learning_closure_bridge",
            "runtime_callable": "write_candidate_learning_closures",
            "receipt_adapter": "",
            "local_model_supported": True,
            "local_model_phase": "C",
            "status": CapabilityWiringStatus.LOCALHEAL_EXECUTABLE,
            "reason": "Learning closure bridge exists; available for local path",
        },
        "codeintel": {
            "runtime_module": "nexus.engine.evidence_graph",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local runtime; requires cloud/planner integration",
        },
        "memory": {
            "runtime_module": "nexus.services.local_heal.memory_retrieval_adapter",
            "runtime_callable": "MemoryRetrievalAdapter.retrieve_reranked",
            "receipt_adapter": "",
            "local_model_supported": True,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.METADATA_ONLY,
            "reason": "Memory trace exists but passive; not active decision-making",
        },
        "lancedb": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local vector retrieval runtime",
        },
        "belief": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "D",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local belief engine runtime",
        },
        "mempalace": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "S",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local mempalace runtime",
        },
        "hyper_sprint": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local hyper sprint runtime",
        },
        "nightshift": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local nightshift runtime",
        },
        "swarm_multi_agent": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local swarm runtime",
        },
        "drone": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local drone runtime",
        },
        "ultra_review": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local ultra review runtime",
        },
        "research": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local research runtime",
        },
        "research_and_source_discipline": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local runtime",
        },
        "research_control_plane": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local runtime",
        },
        "sandbox_replay": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local runtime",
        },
        "ui_validator": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local UI validator runtime",
        },
        "external_productivity": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "External by definition",
        },
        "autonomic_router": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "P",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Router is planner-level, not executor-level",
        },
        "forecast_pregate": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "P",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Planner-level gate",
        },
        "governance_and_trust": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "S",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Planner-level governance",
        },
        "file_lock_security_gate": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "S",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Planner-level security gate",
        },
        "policy_capability_gate": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "S",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Planner-level policy gate",
        },
        "benchmark_meta_opt": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "C",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Meta-optimization is post-execution",
        },
        "learn_ask": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "C",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Learning ask is post-execution",
        },
        "registry_skills_sync": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "P",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Registry sync is planner-level",
        },
        "regression_guard": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "A",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local regression guard runtime",
        },
        "metabolism_resume": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "C",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "Metabolism is post-execution continuity",
        },
        "xray": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local xray runtime",
        },
        "direct_master_loop": {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "R",
            "status": CapabilityWiringStatus.EXTERNAL_ONLY,
            "reason": "No local direct master loop runtime",
        },
    }

    for name in sorted(caps.keys()):
        defn = _DEFINITIONS.get(name, {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "",
            "status": CapabilityWiringStatus.UNSUPPORTED,
            "reason": "Not defined in local model executor path",
        })
        wiring[name] = LocalModelCapabilityWiring(
            name=name,
            registry_known=True,
            planner_known=name in caps,
            runtime_module=defn["runtime_module"],
            runtime_callable=defn["runtime_callable"],
            receipt_adapter=defn["receipt_adapter"],
            local_model_supported=defn["local_model_supported"],
            local_model_phase=defn["local_model_phase"],
            status=defn["status"],
            reason=defn["reason"],
        )

    return wiring


def classify_selected_capabilities(
    selected: Iterable[str],
    wiring: dict[str, LocalModelCapabilityWiring] | None = None,
) -> dict[str, list[str]]:
    """Classify selected capabilities into execution categories.

    Returns dict with keys:
        selected_capabilities_seen, executable_capabilities, advisory_capabilities,
        gate_capabilities, localheal_capabilities, external_only_capabilities,
        unsupported_capabilities, metadata_only_capabilities
    """
    if wiring is None:
        wiring = build_local_model_capability_wiring()

    result: dict[str, list[str]] = {
        "selected_capabilities_seen": [],
        "executable_capabilities": [],
        "advisory_capabilities": [],
        "gate_capabilities": [],
        "localheal_capabilities": [],
        "external_only_capabilities": [],
        "unsupported_capabilities": [],
        "metadata_only_capabilities": [],
    }

    for name in selected:
        w = wiring.get(name)
        if w is None:
            result["unsupported_capabilities"].append(name)
            continue

        result["selected_capabilities_seen"].append(name)

        if w.status == CapabilityWiringStatus.EXECUTABLE:
            result["executable_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.ADVISORY_EXECUTABLE:
            result["advisory_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.GATE_EXECUTABLE:
            result["gate_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.LOCALHEAL_EXECUTABLE:
            result["localheal_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.EXTERNAL_ONLY:
            result["external_only_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.METADATA_ONLY:
            result["metadata_only_capabilities"].append(name)
        elif w.status == CapabilityWiringStatus.UNSUPPORTED:
            result["unsupported_capabilities"].append(name)

    return result
