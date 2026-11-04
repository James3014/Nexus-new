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


def test_3374_smoke_output_unchanged_without_key_and_signed_with_key(
    tmp_path: Path, monkeypatch
) -> None:
    from nexus.learning.zero_trust_v2_receipts import (
        REPORT_KIND_POST_APPLY_SMOKE,
        verify_report_signature,
    )
    from scripts.ops import build_heep_runtime_post_apply_smoke as module

    monkeypatch.delenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", raising=False)
    overlay = tmp_path / "overlay.json"
    overlay.write_text(
        json.dumps({"status": "PASS", "skill_assembly_by_capability": {}}), encoding="utf-8"
    )
    status_report = tmp_path / "status.json"
    status_report.write_text(json.dumps({"skills": []}), encoding="utf-8")
    base = ["--overlay", str(overlay), "--skill-status-report", str(status_report)]

    module.main([*base, "--output", str(tmp_path / "plain.json")])
    plain = json.loads((tmp_path / "plain.json").read_text(encoding="utf-8"))
    direct = module.build_heep_runtime_post_apply_smoke(
        overlay={"status": "PASS", "skill_assembly_by_capability": {}},
        overlay_path=str(overlay),
        skill_status_report=str(status_report),
    )
    assert "report_signature" not in plain
    assert set(plain) == set(direct)

    keyfile = tmp_path / "key"
    keyfile.write_text("k", encoding="utf-8")
    module.main([
        *base,
        "--output",
        str(tmp_path / "signed.json"),
        "--signing-secret-file",
        str(keyfile),
    ])
    signed = json.loads((tmp_path / "signed.json").read_text(encoding="utf-8"))
    assert verify_report_signature(signed, kind=REPORT_KIND_POST_APPLY_SMOKE, secret="k")
    assert {k: v for k, v in signed.items() if k not in {"report_signature", "created_at"}} == {
        k: v for k, v in plain.items() if k != "created_at"
    }
