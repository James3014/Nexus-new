from __future__ import annotations

import json

from scripts.ops.check_route_context_seam_freeze import check_route_context_seam_freeze


def test_route_context_freeze_check_passes_clean_freeze(tmp_path):
    freeze_path = tmp_path / "freeze.json"
    output_path = tmp_path / "check.json"
    freeze_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "route_manifest_ref": "docs/reports/route.json",
                "context_receipt_ref": "docs/reports/context.json",
                "runtime_dispatch_changed": False,
                "preserved_l0_l1": True,
                "claim_read_model_status": "PASS",
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    payload = check_route_context_seam_freeze(freeze_path=freeze_path, output_path=output_path)

    assert payload["status"] == "PASS"
    assert payload["blockers"] == []
    assert output_path.exists()


def test_route_context_freeze_check_blocks_unlock_attempt(tmp_path):
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "route_manifest_ref": "docs/reports/route.json",
                "context_receipt_ref": "docs/reports/context.json",
                "runtime_dispatch_changed": False,
                "preserved_l0_l1": True,
                "claim_read_model_status": "PASS",
                "runtime_update_allowed": True,
                "public_benchmark_allowed": True,
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )

    payload = check_route_context_seam_freeze(freeze_path=freeze_path)

    assert payload["status"] == "RETURN"
    assert payload["blockers"] == [
        "freeze:freeze_contract_must_not_unlock_public_benchmark",
        "freeze:freeze_contract_must_not_update_runtime",
    ]


def test_route_context_freeze_check_blocks_existing_freeze_blockers(tmp_path):
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(
        json.dumps(
            {
                "status": "RETURN",
                "route_manifest_ref": "docs/reports/route.json",
                "context_receipt_ref": "docs/reports/context.json",
                "runtime_dispatch_changed": False,
                "preserved_l0_l1": False,
                "claim_read_model_status": "RETURN",
                "blockers": ["claim_read_model_not_pass"],
            }
        ),
        encoding="utf-8",
    )

    payload = check_route_context_seam_freeze(freeze_path=freeze_path)

    assert payload["status"] == "RETURN"
    assert "freeze:blockers_present" in payload["blockers"]
    assert "freeze:status_not_pass" in payload["blockers"]
