from pathlib import Path

from nexus.delivery.receipt import build_delivery_receipt
from nexus.delivery.receipt import load_delivery_receipt
from nexus.delivery.receipt import write_delivery_receipt


def test_build_delivery_receipt_populates_acceptance_and_artifact_hashes(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    baseline = tmp_path / "baseline.json"
    acceptance = tmp_path / "acceptance.json"
    evidence.write_text("{}", encoding="utf-8")
    baseline.write_text("{}", encoding="utf-8")
    acceptance.write_text("{}", encoding="utf-8")

    payload = build_delivery_receipt(
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="dev",
        acceptance_exit_code=0,
        acceptance_status="PASS",
        acceptance_gate=True,
        acceptance_primary="none",
        branch="feat/x",
        head="abc123",
    )

    assert payload["branch"] == "feat/x"
    assert payload["head"] == "abc123"
    assert payload["acceptance_result"]["gate_passed"] is True
    assert payload["artifacts"]["evidence"]["sha256"] is not None


def test_write_and_load_delivery_receipt_round_trip(tmp_path: Path) -> None:
    receipt = tmp_path / "delivery_gate.json"
    evidence = tmp_path / "evidence.json"
    baseline = tmp_path / "baseline.json"
    acceptance = tmp_path / "acceptance.json"
    evidence.write_text("{}", encoding="utf-8")
    baseline.write_text("{}", encoding="utf-8")
    acceptance.write_text("{}", encoding="utf-8")

    write_delivery_receipt(
        receipt_path=receipt,
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="dev",
        acceptance_exit_code=0,
        acceptance_status="PASS",
        acceptance_gate=True,
        acceptance_primary="none",
    )

    payload = load_delivery_receipt(receipt)
    assert payload["delivery_gate_passed"] is True
    assert payload["acceptance_result"]["status"] == "PASS"
