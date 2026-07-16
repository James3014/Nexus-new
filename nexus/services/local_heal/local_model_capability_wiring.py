"""Local model capability wiring — projected from mainchain execution contract.

Independent Local 51-item truth is no longer an authority. Statuses for
planner capabilities are derived from PLANNER_EXECUTION_CONTRACTS via
project_local_execution_mode. SPXDRAC registry names remain listed for
crosswalk compatibility, but unknown/unsupported for planner nodes is 0.
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


class LocalContractMode(str, Enum):
    """Contract-derived Local modes (single authority from mainchain)."""

    EXECUTE_HERE = "EXECUTE_HERE"
    CONSUME_SHARED_EVIDENCE = "CONSUME_SHARED_EVIDENCE"
    CONTROLLED_BY_POSTFLIGHT = "CONTROLLED_BY_POSTFLIGHT"
    EXTERNAL_NOT_LOCAL = "EXTERNAL_NOT_LOCAL"


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


def _status_from_local_mode(mode: str) -> CapabilityWiringStatus:
    """Map contract local mode → legacy LocalModelCapabilityWiring status."""
    if mode == LocalContractMode.EXECUTE_HERE.value:
        return CapabilityWiringStatus.EXECUTABLE
    if mode == LocalContractMode.CONTROLLED_BY_POSTFLIGHT.value:
        return CapabilityWiringStatus.GATE_EXECUTABLE
    if mode == LocalContractMode.CONSUME_SHARED_EVIDENCE.value:
        return CapabilityWiringStatus.ADVISORY_EXECUTABLE
    return CapabilityWiringStatus.EXTERNAL_ONLY


def build_local_model_capability_wiring() -> dict[str, LocalModelCapabilityWiring]:
    """Build Local wiring map derived from mainchain execution contracts.

    SPXDRAC registry names are retained for crosswalk length compatibility.
    Planner nodes always receive a contract-derived status (never independent
    UNSUPPORTED truth when a planner contract exists).
    """
    from nexus.core.capability_registry import CapabilityRegistry
    from nexus.services.capability_registry import (
        PLANNER_EXECUTION_CONTRACTS,
        project_local_execution_mode,
    )

    registry = CapabilityRegistry()
    caps = {c.name: c for c in registry.list_all_capabilities()}
    # Also project planner-only names that are not in the SPXDRAC 51 surface.
    planner_only = {
        n: None for n in PLANNER_EXECUTION_CONTRACTS if n not in caps
    }

    wiring: dict[str, LocalModelCapabilityWiring] = {}

    # Capability name -> wiring definition (legacy hints; overridden by contract)
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
            "runtime_module": "nexus.services.local_heal.evidence_graph",
            "runtime_callable": "RuntimeASTExtractor.extract_from_file",
            "receipt_adapter": "",
            "local_model_supported": True,
            "local_model_phase": "D",
            "status": CapabilityWiringStatus.LOCALHEAL_EXECUTABLE,
            "reason": "C6AA: RuntimeASTExtractor exists locally; now wired into semantic retry prompt",
        },
        "memory": {
            "runtime_module": "nexus.services.local_heal.memory_retrieval_adapter",
            "runtime_callable": "MemoryRetrievalAdapter.retrieve_reranked",
            "receipt_adapter": "",
            "local_model_supported": True,
            "local_model_phase": "X",
            "status": CapabilityWiringStatus.ADVISORY_EXECUTABLE,
            "reason": "Executor actively retrieves provenance-backed lessons and injects them into prompt context",
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

    registry_names = set(caps.keys())
    all_names = sorted(set(caps.keys()) | set(planner_only.keys()))
    for name in all_names:
        defn = _DEFINITIONS.get(name, {
            "runtime_module": "",
            "runtime_callable": "",
            "receipt_adapter": "",
            "local_model_supported": False,
            "local_model_phase": "",
            "status": CapabilityWiringStatus.UNSUPPORTED,
            "reason": "Not defined in local model executor path",
        })
        # Contract projection is the authority for planner nodes.
        if name in PLANNER_EXECUTION_CONTRACTS:
            mode = project_local_execution_mode(name)
            status = _status_from_local_mode(mode)
            supported = mode != LocalContractMode.EXTERNAL_NOT_LOCAL.value
            reason = f"contract_projection:{mode}"
            runtime_module = str(defn.get("runtime_module") or "nexus.services.capability_registry")
            runtime_callable = str(
                defn.get("runtime_callable")
                or PLANNER_EXECUTION_CONTRACTS[name].get("physical_callable")
                or ""
            )
        else:
            status = defn["status"]
            supported = bool(defn["local_model_supported"])
            reason = str(defn["reason"])
            runtime_module = str(defn["runtime_module"])
            runtime_callable = str(defn["runtime_callable"])
            # Non-planner SPXDRAC names: never leave as independent UNSUPPORTED.
            if status == CapabilityWiringStatus.UNSUPPORTED:
                status = CapabilityWiringStatus.EXTERNAL_ONLY
                reason = "spxdrac_metadata_external_not_local"
                supported = False
        wiring[name] = LocalModelCapabilityWiring(
            name=name,
            registry_known=name in registry_names,
            planner_known=name in PLANNER_EXECUTION_CONTRACTS,
            runtime_module=runtime_module,
            runtime_callable=runtime_callable,
            receipt_adapter=str(defn.get("receipt_adapter") or ""),
            local_model_supported=supported,
            local_model_phase=str(defn.get("local_model_phase") or ""),
            status=status,
            reason=reason,
        )

    return wiring


def build_planner_local_contract_wiring() -> dict[str, LocalModelCapabilityWiring]:
    """Planner-only (57) Local wiring projection — contract authority, no SPXDRAC pad."""
    full = build_local_model_capability_wiring()
    from nexus.services.capability_registry import PLANNER_EXECUTION_CONTRACTS

    return {n: full[n] for n in PLANNER_EXECUTION_CONTRACTS if n in full}


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


# ---------------------------------------------------------------------------
# N30R-W1: Planner SSD → Executor Capability Projection
# ---------------------------------------------------------------------------

CONTROLLER_PLANE_CAPABILITIES = frozenset({
    "harness_preflight_sensor",
    "research_route",
    "mempalace_gate",
})

_DEFINITIONS_STANDALONE: dict[str, dict] = {
    "delivery_gate": {
        "runtime_module": "nexus.services.local_heal.claim_delivery_gate",
        "runtime_callable": "validate_context_claim_delivery",
        "receipt_adapter": "delivery_gate",
        "local_model_supported": True,
        "local_model_phase": "A",
        "status": CapabilityWiringStatus.GATE_EXECUTABLE,
        "reason": "Gate function exists; candidate for C4 gate execution",
    },
    "local_model_executor": {
        "runtime_module": "nexus.services.local_heal.local_model_executor",
        "runtime_callable": "LocalModelExecutor.run",
        "receipt_adapter": "local_model_executor",
        "local_model_supported": True,
        "local_model_phase": "R",
        "status": CapabilityWiringStatus.EXECUTABLE,
        "reason": "Direct executor invocation via _finalize_with_nexus_row",
    },
}


@dataclass(frozen=True)
class LocalExecutorCapabilityProjection:
    """Canonical projection from Planner SSD route map to Executor selected_capabilities."""
    selected_capabilities: tuple[str, ...]
    source: str
    planner_selected_count: int
    projected_count: int
    dropped_capabilities: tuple[str, ...]
    unknown_capabilities: tuple[str, ...]
    advisory_capabilities: tuple[str, ...]
    executable_capabilities: tuple[str, ...]
    control_plane_capabilities: tuple[str, ...]
    dependency_errors: tuple[str, ...]
    valid: bool
    failure_reason: str


def _classify_single_capability(
    cap_str: str,
    wiring_map: dict[str, LocalModelCapabilityWiring],
) -> tuple[str, str]:
    """Classify a single capability into its canonical category.

    Returns (category, canonical_name) where category is one of:
    'executable', 'advisory', 'control_plane', 'unknown'.

    Lookup order:
      1. wiring_map (registry-based, 34 entries)
      2. _DEFINITIONS_STANDALONE (non-registry capabilities with local support)
      3. CONTROLLER_PLANE_CAPABILITIES (known planner-level concepts)
      4. Unknown
    """
    if not cap_str:
        return "unknown", cap_str

    # 1. Registry-based wiring map
    wiring = wiring_map.get(cap_str)
    if wiring is not None:
        if wiring.local_model_supported:
            if wiring.status in (CapabilityWiringStatus.LOCALHEAL_EXECUTABLE,
                                 CapabilityWiringStatus.EXECUTABLE,
                                 CapabilityWiringStatus.GATE_EXECUTABLE):
                return "executable", cap_str
            elif wiring.status in (CapabilityWiringStatus.ADVISORY_EXECUTABLE,
                                   CapabilityWiringStatus.METADATA_ONLY):
                return "advisory", cap_str
            else:
                return "advisory", cap_str
        else:
            return "advisory", cap_str

    # 2. Standalone definitions (non-registry capabilities with local wiring)
    standalone_def = _DEFINITIONS_STANDALONE.get(cap_str)
    if standalone_def is not None:
        if standalone_def.get("local_model_supported", False):
            status = standalone_def.get("status")
            if status in (CapabilityWiringStatus.LOCALHEAL_EXECUTABLE,
                          CapabilityWiringStatus.EXECUTABLE,
                          CapabilityWiringStatus.GATE_EXECUTABLE):
                return "executable", cap_str
            elif status in (CapabilityWiringStatus.ADVISORY_EXECUTABLE,
                            CapabilityWiringStatus.METADATA_ONLY):
                return "advisory", cap_str
            else:
                return "advisory", cap_str
        return "advisory", cap_str

    # 3. Known control-plane capabilities
    if cap_str in CONTROLLER_PLANE_CAPABILITIES:
        return "control_plane", cap_str

    return "unknown", cap_str


def project_planner_capabilities_for_local_executor(
    signal_snapshot: dict[str, Any],
) -> LocalExecutorCapabilityProjection:
    """Project Planner SSD route map capabilities to Executor selected_capabilities.

    Priority 1: explicit top-level 'selected_capabilities' if present and non-empty.
    Priority 2: ssd_route_map.capability_reasons keys.
    Validates against local model executor wiring registry.

    Classification order per capability:
      1. Wiring registry lookup (executable / advisory)
      2. Known control-plane capability set (control_plane)
      3. Unknown (projection becomes invalid)
    """
    _empty_proj = lambda src="", fr="": LocalExecutorCapabilityProjection(
        selected_capabilities=(), source=src,
        planner_selected_count=0, projected_count=0,
        dropped_capabilities=(), unknown_capabilities=(),
        advisory_capabilities=(), executable_capabilities=(),
        control_plane_capabilities=(),
        dependency_errors=(), valid=False, failure_reason=fr,
    )

    # Priority 1: explicit top-level
    explicit_caps = signal_snapshot.get("selected_capabilities")
    if explicit_caps and isinstance(explicit_caps, (list, tuple)) and len(explicit_caps) > 0:
        source = "explicit_selected_capabilities"
        planner_caps = list(explicit_caps)
    else:
        # Priority 2: SSD route map
        ssd = signal_snapshot.get("ssd_route_map", {})
        if not isinstance(ssd, dict):
            return _empty_proj("ssd_missing", "ssd_route_map_not_dict")
        capability_reasons = ssd.get("capability_reasons", {})
        if not isinstance(capability_reasons, dict):
            return _empty_proj("ssd_capability_reasons_not_dict", "ssd_capability_reasons_not_dict")
        planner_caps = list(capability_reasons.keys())
        if not planner_caps:
            return _empty_proj("ssd_capability_reasons_empty", "ssd_capability_reasons_empty")
        source = "ssd_route_map_capability_reasons"

        declared_count = ssd.get("selected_capability_count", 0)
        if declared_count and declared_count != len(planner_caps):
            return LocalExecutorCapabilityProjection(
                selected_capabilities=(), source=source,
                planner_selected_count=declared_count, projected_count=0,
                dropped_capabilities=(), unknown_capabilities=(),
                advisory_capabilities=(), executable_capabilities=(),
                control_plane_capabilities=(),
                dependency_errors=(), valid=False,
                failure_reason=f"ssd_selected_count_mismatch:declared={declared_count},actual={len(planner_caps)}",
            )

    planner_selected_count = len(planner_caps)

    # Canonical deduplication and ordering: sort alphabetically, deduplicate, reject empty IDs
    seen: set[str] = set()
    canonical_caps: list[str] = []
    for cap in planner_caps:
        cap_str = str(cap).strip()
        if not cap_str:
            continue
        if cap_str not in seen:
            seen.add(cap_str)
            canonical_caps.append(cap_str)
    canonical_caps.sort()

    # Build wiring map for classification
    try:
        wiring_map = build_local_model_capability_wiring()
    except Exception:
        wiring_map = {}

    executable: list[str] = []
    advisory: list[str] = []
    control_plane: list[str] = []
    unknown: list[str] = []

    for cap_str in canonical_caps:
        category, _ = _classify_single_capability(cap_str, wiring_map)
        if category == "executable":
            executable.append(cap_str)
        elif category == "advisory":
            advisory.append(cap_str)
        elif category == "control_plane":
            control_plane.append(cap_str)
        else:
            unknown.append(cap_str)

    # Dependency validation: fail-closed on hard dependency errors
    ssd = signal_snapshot.get("ssd_route_map", {})
    deps = ssd.get("capability_dependencies", {}) if isinstance(ssd, dict) else {}
    dependency_errors: list[str] = []
    if isinstance(deps, dict):
        cap_set = set(canonical_caps)
        for cap, dep_list in deps.items():
            if cap not in cap_set:
                continue
            if isinstance(dep_list, (list, tuple)):
                for dep in dep_list:
                    if dep not in cap_set:
                        dependency_errors.append(f"{cap}_depends_on_{dep}_not_selected")

    # Fail-closed: unknown capabilities or hard dependency errors invalidate projection
    valid = True
    failure_reason = ""
    if unknown:
        valid = False
        failure_reason = f"unknown_capabilities_present:{','.join(sorted(unknown))}"
    if dependency_errors:
        valid = False
        dep_reason = f"dependency_errors_present:{','.join(sorted(dependency_errors))}"
        failure_reason = f"{failure_reason};{dep_reason}" if failure_reason else dep_reason

    # Executor-receivable subset: executable + advisory only
    # Control-plane capabilities are NOT passed to executor; they stay in projection provenance
    executor_selected = tuple(executable + advisory)

    return LocalExecutorCapabilityProjection(
        selected_capabilities=executor_selected,
        source=source,
        planner_selected_count=planner_selected_count,
        projected_count=len(executor_selected),
        dropped_capabilities=(),
        unknown_capabilities=tuple(unknown),
        advisory_capabilities=tuple(advisory),
        executable_capabilities=tuple(executable),
        control_plane_capabilities=tuple(control_plane),
        dependency_errors=tuple(dependency_errors),
        valid=valid,
        failure_reason=failure_reason,
    )
