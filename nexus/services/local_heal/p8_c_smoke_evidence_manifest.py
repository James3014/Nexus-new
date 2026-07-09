from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class P8CSmokeEvidenceManifest:
    manifest_version: str = "1.0"
    approval_artifact_present: bool = False
    prompt_capsule_present: bool = False
    smoke_receipt_present: bool = False
    smoke_bundle_present: bool = False
    b1_report_present: bool = False
    b2_report_present: bool = False
    b3_report_present: bool = False
    b4_report_present: bool = False
    b5_report_present: bool = False
    b6_report_present: bool = False
    b7_report_present: bool = False
    final_seal_report_present: bool = False
    p7_final_seal_present: bool = False
    manifest_complete: bool = False
    missing_artifacts: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)


EXPECTED_A = [
    ("artifacts/effect_reports/p8_human_approval_artifact_v0.json", "approval_artifact_present"),
    ("artifacts/effect_reports/p8_smoke_prompt_capsule_v0.json", "prompt_capsule_present"),
    ("artifacts/effect_reports/p8_one_network_smoke_receipt_v1.json", "smoke_receipt_present"),
    ("artifacts/effect_reports/p8_approved_network_smoke_evidence_bundle_v1.json", "smoke_bundle_present"),
    ("docs/reports/p8_b1_human_approval_artifact_intake_v0.md", "b1_report_present"),
    ("docs/reports/p8_b2_approval_boundary_reconciliation_v0.md", "b2_report_present"),
    ("docs/reports/p8_b3_synthetic_smoke_prompt_capsule_v0.md", "b3_report_present"),
    ("docs/reports/p8_b4_one_smoke_preflight_gate_v0.md", "b4_report_present"),
    ("docs/reports/p8_b5_one_network_smoke_execution_v0.md", "b5_report_present"),
    ("docs/reports/p8_b6_post_smoke_safety_validator_v0.md", "b6_report_present"),
    ("docs/reports/p8_b7_approved_smoke_evidence_bundle_v0.md", "b7_report_present"),
    ("docs/reports/p8_final_approved_network_smoke_seal_report_v1.md", "final_seal_report_present"),
    ("docs/reports/p7_final_armor_integration_seal_report_v0.md", "p7_final_seal_present"),
]


def load_smoke_manifest(base_dir: str = ".") -> P8CSmokeEvidenceManifest:
    missing = []
    field_map = {}
    for rel, fname in EXPECTED_A:
        full = os.path.join(base_dir, rel)
        present = os.path.exists(full)
        field_map[fname] = present
        if not present:
            missing.append(rel)

    blocked = ["missing_artifacts"] if missing else []

    return P8CSmokeEvidenceManifest(
        approval_artifact_present=field_map.get("approval_artifact_present", False),
        prompt_capsule_present=field_map.get("prompt_capsule_present", False),
        smoke_receipt_present=field_map.get("smoke_receipt_present", False),
        smoke_bundle_present=field_map.get("smoke_bundle_present", False),
        b1_report_present=field_map.get("b1_report_present", False),
        b2_report_present=field_map.get("b2_report_present", False),
        b3_report_present=field_map.get("b3_report_present", False),
        b4_report_present=field_map.get("b4_report_present", False),
        b5_report_present=field_map.get("b5_report_present", False),
        b6_report_present=field_map.get("b6_report_present", False),
        b7_report_present=field_map.get("b7_report_present", False),
        final_seal_report_present=field_map.get("final_seal_report_present", False),
        p7_final_seal_present=field_map.get("p7_final_seal_present", False),
        manifest_complete=len(missing) == 0,
        missing_artifacts=missing,
        blocked_reasons=blocked,
    )
