from __future__ import annotations

from pathlib import Path

from scripts.ops.nexus_p30_acceptance_gate import _latest_flash_bundle, build_gate


def test_p30_acceptance_gate_can_block_only_on_required_flash():
    payload = build_gate(Path(".").resolve(), require_flash=False)

    assert payload["schema_version"] == "nexus_p30_acceptance_gate.v1"
    assert payload["checks"]["hallucination_guard_drift"] is True
    assert payload["checks"]["brain_hub_audit"] is True
    assert payload["checks"]["pipeline_composition_inventory"] is True
    assert "flash_public_delivery_gate" in payload["checks"]
    assert "flash_public_cost_claim_gate" in payload["checks"]
    assert "flash_public_claim_gate" in payload["checks"]


def test_latest_flash_bundle_accepts_delivery_when_cost_claim_is_blocked(tmp_path: Path):
    out_dir = tmp_path / ".nexus" / "reports" / "bench_flash"
    out_dir.mkdir(parents=True)
    (out_dir / "evidence_bundle.json").write_text(
        """
{
  "public_claim_gate": {"verdict": "FAIL", "failures": ["with_token_measured_below_threshold"]},
  "public_delivery_gate": {"verdict": "PASS", "failures": []},
  "public_cost_claim_gate": {"verdict": "FAIL", "failures": ["with_token_measured_below_threshold"]}
}
""".strip(),
        encoding="utf-8",
    )

    payload = _latest_flash_bundle(tmp_path)

    assert payload["passed"] is True
    assert payload["cost_claim_passed"] is False
    assert payload["public_delivery_gate"]["verdict"] == "PASS"
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
