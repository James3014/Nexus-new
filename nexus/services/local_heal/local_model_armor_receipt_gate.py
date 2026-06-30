"""N3.11: Local model armor receipt completeness gate.

Validates that LocalModelExecutorResponse.raw_model_metadata contains
all required fields for a complete armor receipt. Missing fields -> incomplete.
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

    return (len(missing) == 0, missing)
