"""C6: Local model armor receipt completeness gate with causality coverage.

Validates that LocalModelExecutorResponse.raw_model_metadata contains
all required fields and that every selected capability has a causality status.
"""
from __future__ import annotations

from typing import Any, Mapping


_REQUIRED_FIELDS = (
    "execution_topology",
    "selected_capabilities_used",
    "protocol_mode",
    "protocol_normalization",
    "source_anchor_present",
    "source_anchor_source",
    "source_anchor_hash",
    "target_file",
    "target_symbol",
    "locked_search_present",
    "failure_feedback_present",
    "final_authority",
)
# selected_capabilities is preferred when present; used must never silently equal selected.


def validate_local_model_armor_metadata(
    metadata: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Validate armor receipt completeness.

    Returns:
        (is_complete, missing_fields) where missing_fields lists failed checks.
    """
    missing: list[str] = []

    # 1. Required fields
    for field in _REQUIRED_FIELDS:
        if field not in metadata or metadata[field] is None:
            missing.append(field)

    # 2. final_authority must be NexusVerifier
    if metadata.get("final_authority") != "NexusVerifier":
        if "final_authority" not in missing:
            missing.append("final_authority_not_nexus_verifier")

    # 3. protocol_mode must be anchored_edit or unified_diff
    pm = metadata.get("protocol_mode", "")
    if pm not in ("anchored_edit", "unified_diff", ""):
        if "protocol_mode" not in missing:
            missing.append("protocol_mode_invalid")

    # 4. local_committee_only requires committee fields
    topo = metadata.get("execution_topology", "")
    if topo == "local_committee_only":
        if "committee_candidate_count" not in metadata:
            missing.append("committee_candidate_count_missing")
        if "selected_by" not in metadata:
            missing.append("selected_by_missing")

    # 5. source_anchor_present=True requires source and hash
    if metadata.get("source_anchor_present") is True:
        if not metadata.get("source_anchor_source"):
            missing.append("source_anchor_source_empty")
        if not metadata.get("source_anchor_hash"):
            missing.append("source_anchor_hash_empty")

    # 6. source_anchor_present=False requires reason
    if metadata.get("source_anchor_present") is False:
        if not metadata.get("source_anchor_missing") and not metadata.get("localization_missing"):
            missing.append("source_anchor_missing_reason_absent")

    # 7. llm_call_ledger completeness
    ledger = metadata.get("llm_call_ledger")
    if ledger:
        if not ledger.get("phase_complete", False) or ledger.get("unknown_call_count", 0) > 0:
            missing.append("ledger_phase_incomplete")
        if not ledger.get("attempt_context_complete", False) or ledger.get("missing_attempt_id_count", 0) > 0:
            missing.append("ledger_attempt_id_incomplete")
        if not ledger.get("profile_context_complete", False) or ledger.get("missing_execution_profile_count", 0) > 0:
            missing.append("ledger_profile_incomplete")

    return (len(missing) == 0, missing)


def validate_capability_causality(
    metadata: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Validate selected vs used causality.

    When both ``selected_capabilities`` and ``selected_capabilities_used`` are
    present without ``capability_usage_status``, a full equality copy is a
    false-green. Legacy receipts that only set ``selected_capabilities_used``
    still use physical invoke checks (memory/ddtree/gates/path-A).
    """
    issues: list[str] = []
    explicit_selected = list(metadata.get("selected_capabilities") or [])
    used = list(metadata.get("selected_capabilities_used") or [])
    usage_status = metadata.get("capability_usage_status")
    if not isinstance(usage_status, Mapping):
        usage_status = {}

    # Legacy: only used list present — treat as the selected set for invoke checks.
    legacy_mode = not explicit_selected and bool(used)
    selected = list(explicit_selected) if explicit_selected else list(used)

    if not selected:
        return (True, [])

    # New contract: selected + used present, equal, no status, multi-cap → reject copy.
    if (
        not legacy_mode
        and explicit_selected
        and used
        and set(explicit_selected) == set(used)
        and not usage_status
        and len(explicit_selected) > 1
    ):
        issues.append("selected_used_mismatch_copy_without_usage_status")

    gate_results = metadata.get("gate_results", {}) or {}
    ddtree_result = metadata.get("ddtree_result")
    autoreason_result = metadata.get("autoreason_result")

    for cap in selected:
        st = str(usage_status.get(cap) or "")
        if st == "used":
            if cap not in used and not legacy_mode:
                issues.append(f"{cap}_status_used_but_missing_from_used_list")
            continue
        if st in {"selected_not_consumed", "failed_not_used"}:
            if cap in used:
                issues.append(f"{cap}_selected_not_consumed_but_reported_used")
            continue

        # Physical invoke checks (legacy + when status absent).
        if cap == "local_model_executor":
            continue
        if cap == "ddtree":
            if not ddtree_result or not (
                isinstance(ddtree_result, Mapping) and ddtree_result.get("invoked")
            ):
                issues.append("ddtree_selected_but_not_invoked")
        elif cap == "autoreason":
            if not autoreason_result or not (
                isinstance(autoreason_result, Mapping) and autoreason_result.get("invoked")
            ):
                issues.append("autoreason_selected_but_not_invoked")
        elif cap in ("artifact_gate", "claim_gate", "delivery_gate"):
            gate = gate_results.get(cap) if isinstance(gate_results, Mapping) else None
            if not gate or not (isinstance(gate, Mapping) and gate.get("invoked")):
                issues.append(f"{cap}_selected_but_not_invoked")
        elif cap in (
            "swarm_multi_agent",
            "drone",
            "ultra_review",
            "hyper_sprint",
            "nightshift",
            "codeintel",
            "lancedb",
            "belief",
            "mempalace",
            "research",
            "ui_validator",
            "external_productivity",
        ):
            # External-only / context — expected without local invoke markers.
            pass
        elif cap == "memory":
            if not metadata.get("memory_retrieval_attempted", False):
                issues.append("memory_selected_but_not_invoked")
        elif cap == "repair_loop":
            actual_exec = metadata.get("localheal_pipeline_actual_execution", False)
            avail_only = metadata.get("localheal_pipeline_availability_only", False)
            if avail_only:
                issues.append("localheal_pipeline_availability_only")
            elif not actual_exec:
                issues.append("path_a_actual_execution_missing")
        elif not usage_status and not legacy_mode:
            issues.append(f"{cap}_selected_but_causality_unknown")

    if not legacy_mode:
        for cap in used:
            if cap not in selected:
                issues.append(f"{cap}_used_but_not_selected")

    # Path A: localheal_pipeline topology always requires actual execution evidence.
    topo = metadata.get("execution_topology", "")
    if topo == "localheal_pipeline":
        actual_exec = metadata.get("localheal_pipeline_actual_execution", False)
        avail_only = metadata.get("localheal_pipeline_availability_only", False)
        if avail_only:
            if "localheal_pipeline_availability_only" not in issues:
                issues.append("localheal_pipeline_availability_only")
        elif not actual_exec:
            if "path_a_actual_execution_missing" not in issues:
                issues.append("path_a_actual_execution_missing")

    return (len(issues) == 0, issues)
