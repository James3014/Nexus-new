from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sf_current_overlay_runtime_smoke import build_smoke


def test_current_overlay_runtime_smoke_confirms_receipt_chain(tmp_path: Path) -> None:
    overlay = tmp_path / "overlay.json"
    overlay.write_text(
        json.dumps(
            {
                "status": "PASS",
                "primary_skill_by_capability": {"repair_loop": "tdd"},
            }
        ),
        encoding="utf-8",
    )
    status = tmp_path / "status.json"
    status.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_status.v1",
                "skills": [
                    {
                        "name": "tdd",
                        "path": "/repo/.agents/skills/tdd/SKILL.md",
                        "root": "nexus_repo",
                        "skill_status": "nexus_curated_candidate",
                        "test_level": "runtime_reviewed",
                        "action": "runtime_policy_overlay_only",
                        "capability_mount": "repair_loop",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_smoke(overlay_path=overlay, skill_status_report=status)

    assert report["status"] == "PASS"
    assert report["summary"] == {"case_count": 1, "pass_count": 1, "return_count": 0}
    chain = report["cases"][0]["runtime_final_receipt_chain"]
    assert all(chain.values())
