from __future__ import annotations

from pathlib import Path

from scripts.ops.nexus_p30_acceptance_gate import build_gate


def test_p30_acceptance_gate_can_block_only_on_required_flash():
    payload = build_gate(Path(".").resolve(), require_flash=False)

    assert payload["schema_version"] == "nexus_p30_acceptance_gate.v1"
    assert payload["checks"]["hallucination_guard_drift"] is True
    assert payload["checks"]["brain_hub_audit"] is True
    assert payload["checks"]["pipeline_composition_inventory"] is True
    assert "flash_public_claim_gate" in payload["checks"]
