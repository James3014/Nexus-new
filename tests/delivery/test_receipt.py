import json
from pathlib import Path

from nexus.delivery.receipt import build_delivery_receipt
from nexus.delivery.receipt import load_delivery_receipt
from nexus.delivery.receipt import write_delivery_receipt


def _write_gate_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    evidence = tmp_path / "evidence.json"
    baseline = tmp_path / "baseline.json"
    acceptance = tmp_path / "acceptance.json"
    evidence.write_text(
        json.dumps({"evidence_bundle": {"test_artifacts": ["verified"]}}),
        encoding="utf-8",
    )
    baseline.write_text(json.dumps({"version": "1", "generated_by_sha": "abc123"}), encoding="utf-8")
    acceptance.write_text(
        json.dumps(
            {
                "status": "PASS",
                "gate_passed": True,
                "criteria": [
                    {
                        "name": "report_claim_integrity",
                        "passed": True,
                        "detail": {"passed": True, "checks": []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return evidence, baseline, acceptance


def test_build_delivery_receipt_populates_acceptance_and_artifact_hashes(tmp_path: Path) -> None:
    evidence, baseline, acceptance = _write_gate_inputs(tmp_path)

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
    assert payload["delivery_evidence"]["status"] == "PASS"
    assert payload["delivery_gate_passed"] is True


def test_write_and_load_delivery_receipt_round_trip(tmp_path: Path) -> None:
    receipt = tmp_path / "delivery_gate.json"
    evidence, baseline, acceptance = _write_gate_inputs(tmp_path)

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


def test_delivery_receipt_fails_closed_when_claim_evidence_is_missing(tmp_path: Path) -> None:
    evidence, baseline, acceptance = _write_gate_inputs(tmp_path)
    acceptance.write_text(json.dumps({"status": "PASS", "gate_passed": True}), encoding="utf-8")

    payload = build_delivery_receipt(
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="prod",
        acceptance_exit_code=0,
        acceptance_status="PASS",
        acceptance_gate=True,
        acceptance_primary="none",
        branch="feat/x",
        head="abc123",
    )

    assert payload["delivery_gate_passed"] is False
    assert payload["delivery_evidence"]["blockers"] == ["claim_integrity_passed"]


def test_delivery_receipt_fails_closed_when_report_disagrees_with_arguments(tmp_path: Path) -> None:
    evidence, baseline, acceptance = _write_gate_inputs(tmp_path)
    report = json.loads(acceptance.read_text(encoding="utf-8"))
    report["gate_passed"] = False
    report["status"] = "FAIL"
    acceptance.write_text(json.dumps(report), encoding="utf-8")

    payload = build_delivery_receipt(
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="prod",
        acceptance_exit_code=0,
        acceptance_status="PASS",
        acceptance_gate=True,
        acceptance_primary="none",
        branch="feat/x",
        head="abc123",
    )

    assert payload["delivery_gate_passed"] is False
    assert payload["delivery_evidence"]["checks"]["acceptance_inputs_match_report"] is False
    assert payload["delivery_evidence"]["checks"]["acceptance_report_gate_passed"] is False


def test_delivery_receipt_fails_closed_when_artifact_is_malformed(tmp_path: Path) -> None:
    evidence, baseline, acceptance = _write_gate_inputs(tmp_path)
    evidence.write_text("not-json", encoding="utf-8")

    payload = build_delivery_receipt(
        evidence_path=evidence,
        baseline_path=baseline,
        acceptance_report=acceptance,
        acceptance_policy="prod",
        acceptance_exit_code=0,
        acceptance_status="PASS",
        acceptance_gate=True,
        acceptance_primary="none",
        branch="feat/x",
        head="abc123",
    )

    assert payload["delivery_gate_passed"] is False
    assert payload["delivery_evidence"]["checks"]["evidence_json_valid"] is False
