from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_runtime_post_apply_smoke import build_heep_runtime_post_apply_smoke


def test_heep_runtime_post_apply_smoke_passes_assembly_overlay(tmp_path: Path) -> None:
    overlay = {
        "status": "PASS",
        "skill_assembly_by_capability": {
            "codeintel": [
                {"role": "Scout", "skill_id": "code-scout"},
                {"role": "Audit", "skill_id": "code-audit"},
            ]
        },
    }
    overlay_path = tmp_path / "overlay.json"
    overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
    status_report = tmp_path / "status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "code-scout",
                        "path": ".agents/skills/code-scout/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    },
                    {
                        "name": "code-audit",
                        "path": ".agents/skills/code-audit/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "codeintel",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    smoke = build_heep_runtime_post_apply_smoke(
        overlay=overlay,
        overlay_path=str(overlay_path),
        skill_status_report=str(status_report),
    )

    assert smoke["status"] == "PASS"
    assert smoke["summary"]["runtime_update_allowed"] is True
    assert smoke["cases"][0]["requested_skill_ids"] == ["code-scout", "code-audit"]
    assert all(smoke["cases"][0]["runtime_final_receipt_chain_by_skill"]["code-scout"].values())
