from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class P7ArmorEvidenceManifest:
    manifest_version: str = "1.0"
    p3_final_status_present: bool = False
    p3_synthetic_trace_artifact_present: bool = False
    p3_authority_coupled_trace_present: bool = False
    p3_closeout_bundle_present: bool = False
    p6_final_status_present: bool = False
    p6_closeout_bundle_present: bool = False
    p6_handoff_trace_present: bool = False
    p2_hash_truth_required: bool = True
    p2_anchor_truth_required: bool = True
    p4_verifier_required: bool = True
    p4_claim_gate_required: bool = True
    p5_selection_metadata_required: bool = True
    manifest_complete: bool = False
    missing_artifacts: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)


EXPECTED_ARTIFACTS = [
    ("docs/reports/p3_final_seal_report_v0.md", "p3_final_status_present"),
    ("artifacts/effect_reports/p3_synthetic_e2e_trace_v0.jsonl", "p3_synthetic_trace_artifact_present"),
    ("artifacts/effect_reports/p3_authority_coupled_synthetic_trace_v0.jsonl", "p3_authority_coupled_trace_present"),
    ("artifacts/effect_reports/p3_closeout_evidence_bundle_v0.json", "p3_closeout_bundle_present"),
    ("docs/reports/p6_final_seal_report_v0.md", "p6_final_status_present"),
    ("artifacts/effect_reports/p6_closeout_evidence_bundle_v0.json", "p6_closeout_bundle_present"),
    ("artifacts/effect_reports/p6_p3_handoff_trace_v0.jsonl", "p6_handoff_trace_present"),
]


def load_armor_manifest(base_dir: str = ".") -> P7ArmorEvidenceManifest:
    """Check presence of expected P3/P6 artifacts."""
    missing = []
    field_map = {}
    for rel_path, field_name in EXPECTED_ARTIFACTS:
        full = os.path.join(base_dir, rel_path)
        present = os.path.exists(full)
        field_map[field_name] = present
        if not present:
            missing.append(rel_path)

    blocked = []
    if missing:
        blocked.append("missing_artifacts")

    complete = len(missing) == 0

    return P7ArmorEvidenceManifest(
        p3_final_status_present=field_map.get("p3_final_status_present", False),
        p3_synthetic_trace_artifact_present=field_map.get("p3_synthetic_trace_artifact_present", False),
        p3_authority_coupled_trace_present=field_map.get("p3_authority_coupled_trace_present", False),
        p3_closeout_bundle_present=field_map.get("p3_closeout_bundle_present", False),
        p6_final_status_present=field_map.get("p6_final_status_present", False),
        p6_closeout_bundle_present=field_map.get("p6_closeout_bundle_present", False),
        p6_handoff_trace_present=field_map.get("p6_handoff_trace_present", False),
        manifest_complete=complete,
        missing_artifacts=missing,
        blocked_reasons=blocked,
    )
