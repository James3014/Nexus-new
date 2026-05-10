from __future__ import annotations

import json
from pathlib import Path

from nexus.engine.runtime_capability_receipts import emit_harness_runtime_receipts


def test_runtime_capability_receipts_use_real_bdd_contract(tmp_path: Path):
    capabilities: dict[str, object] = {}

    emit_harness_runtime_receipts(
        repo_root=tmp_path,
        task_desc="Business acceptance repair",
        task_type="repair",
        receipt_slug="task-1",
        selected_capabilities={"bdd_acceptance_skill"},
        capabilities=capabilities,
        route={
            "bdd_acceptance": {
                "given": "a verified order exists",
                "when": "the user requests a receipt",
                "then": "the receipt is delivered with evidence",
            }
        },
        artifact_verified=True,
    )

    assert capabilities["business_verified"] is True
    receipt_path = tmp_path / str(capabilities["bdd_acceptance_report_path"])
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["given"] == "a verified order exists"
    assert payload["status"] == "PASS"


def test_runtime_capability_receipts_fail_closed_without_bdd_contract(tmp_path: Path):
    capabilities: dict[str, object] = {}

    emit_harness_runtime_receipts(
        repo_root=tmp_path,
        task_desc="Business acceptance repair",
        task_type="repair",
        receipt_slug="task-2",
        selected_capabilities={"bdd_acceptance_skill"},
        capabilities=capabilities,
        route={},
        artifact_verified=True,
    )

    assert capabilities["business_verified"] is False
    assert capabilities["bdd_acceptance_skill_gate_passed"] is False


def test_runtime_capability_receipts_can_parse_gwt_task_desc(tmp_path: Path):
    capabilities: dict[str, object] = {}

    emit_harness_runtime_receipts(
        repo_root=tmp_path,
        task_desc="Given a verified artifact, When Nexus closes the task, Then business evidence is present.",
        task_type="feature",
        receipt_slug="task-3",
        selected_capabilities={"bdd_acceptance_skill"},
        capabilities=capabilities,
        route={},
        artifact_verified=True,
    )

    assert capabilities["business_verified"] is True
    receipt_path = tmp_path / str(capabilities["bdd_acceptance_report_path"])
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert payload["given"].startswith("Given a verified artifact")
    assert payload["when"].startswith("When Nexus closes")
    assert payload["then"].startswith("Then business evidence")
