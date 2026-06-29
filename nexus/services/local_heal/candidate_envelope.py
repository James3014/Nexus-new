from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CandidateEnvelope:
    candidate_id: str
    task_id: str
    source: str          # "local" | "external" | "deterministic"
    model: str
    role: str            # "judge" | "primary_proposer" | "secondary_proposer" | "external_primary" | "deterministic_rewriter"
    patch_protocol: str  # "anchored_edit" | "unified_diff" | "search_replace" | "none"
    target_file: str
    target_symbol: str
    source_anchor_hash: str
    candidate_patch_hash: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    abstained: bool = False
    allowed_actions: tuple[str, ...] = field(default_factory=tuple)
    forbidden_actions: tuple[str, ...] = field(default_factory=tuple)
    candidate_patch: str = ""
    schema: str = "nexus.candidate_envelope.v1"

    def __post_init__(self) -> None:
        # Validate that role=judge and candidate_patch exists -> rejected
        if self.role == "judge" and self.candidate_patch.strip():
            raise ValueError("Role 'judge' cannot generate repair patches or have patch content.")
            
        # Validate missing evidence_refs -> rejected
        if not self.evidence_refs:
            raise ValueError("CandidateEnvelope is incomplete: evidence_refs must not be empty.")

        # Ensure correct values for enum-like fields
        valid_sources = {"local", "external", "deterministic"}
        if self.source not in valid_sources:
            raise ValueError(f"Invalid source: '{self.source}'. Must be one of {valid_sources}.")

        valid_roles = {
            "judge",
            "primary_proposer",
            "secondary_proposer",
            "external_primary",
            "deterministic_rewriter",
        }
        if self.role not in valid_roles:
            raise ValueError(f"Invalid role: '{self.role}'. Must be one of {valid_roles}.")

        valid_protocols = {"anchored_edit", "unified_diff", "search_replace", "none"}
        if self.patch_protocol not in valid_protocols:
            raise ValueError(f"Invalid patch_protocol: '{self.patch_protocol}'. Must be one of {valid_protocols}.")
