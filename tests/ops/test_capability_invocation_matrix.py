from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.capability_invocation_matrix import ArmInput, build_invocation_matrix


def _receipt(name: str) -> dict[str, object]:
    return {
        "name": name,
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": True,
    }


def test_invocation_matrix_exposes_supporting_flow_selection_source(tmp_path: Path):
    flash = tmp_path / "flash.jsonl"
    hyper = _receipt("hyper")
    hyper["selection_source"] = "supporting_flow_forced_hyper_sprint"
    flash.write_text(
        json.dumps(
            {
                "task_id": "route-oracle-swarm-001",
                "route_decision_schema_version": "nexus_route_decision_v1",
                "expected_capability_receipt_coverage": {
                    "expected": ["swarm"],
                    "public_safe": ["swarm"],
                    "missing": [],
                    "failure_reasons": {},
                    "all_public_safe": True,
                },
                "capability_receipts": [_receipt("swarm"), hyper],
            }
        ),
        encoding="utf-8",
    )

    payload = build_invocation_matrix(arms=[ArmInput("flash", flash)], required={"swarm"})

    assert payload["passed"] is True
    assert payload["matrix"]["swarm"]["ever_public_safe"] is True
    assert payload["matrix"]["hyper"]["selection_sources"] == ["supporting_flow_forced_hyper_sprint"]
    assert payload["arms"][0]["capabilities"]["hyper"]["selection_sources"] == ["supporting_flow_forced_hyper_sprint"]


def test_invocation_matrix_accepts_smoke_plus_model_arms(tmp_path: Path):
    smoke = tmp_path / "capability_route_smoke_summary.json"
    smoke.write_text(
        json.dumps(
            {
                "passed": True,
                "suites": [
                    {
                        "suite": "route_oracles",
                        "tasks": 1,
                        "expected_capabilities": ["autoreason", "ddtree"],
                        "public_safe_capabilities": ["autoreason", "ddtree"],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    flash = tmp_path / "flash.jsonl"
    flash.write_text(
        json.dumps(
            {
                "task_id": "flash-autoreason",
                "route_decision_schema_version": "nexus_route_decision_v1",
                "expected_capability_receipt_coverage": {
                    "expected": ["autoreason"],
                    "public_safe": ["autoreason"],
                    "missing": [],
                    "failure_reasons": {},
                    "all_public_safe": True,
                },
                "capability_receipts": [_receipt("autoreason")],
            }
        ),
        encoding="utf-8",
    )
    pro = tmp_path / "pro.jsonl"
    pro.write_text(
        json.dumps(
            {
                "task_id": "pro-ddtree",
                "route_decision_schema_version": "nexus_route_decision_v1",
                "expected_capability_receipt_coverage": {
                    "expected": ["ddtree"],
                    "public_safe": ["ddtree"],
                    "missing": [],
                    "failure_reasons": {},
                    "all_public_safe": True,
                },
                "capability_receipts": [_receipt("ddtree")],
            }
        ),
        encoding="utf-8",
    )

    payload = build_invocation_matrix(
        arms=[ArmInput("codex", smoke), ArmInput("flash", flash), ArmInput("pro", pro)],
        required={"autoreason", "ddtree"},
    )

    assert payload["passed"] is True
    assert payload["matrix"]["autoreason"]["ever_public_safe"] is True
    assert payload["matrix"]["ddtree"]["ever_outcome"] is True


def test_invocation_matrix_fails_closed_on_missing_model_receipt(tmp_path: Path):
    smoke = tmp_path / "capability_route_smoke_summary.json"
    smoke.write_text(
        json.dumps(
            {
                "passed": True,
                "suites": [
                    {
                        "suite": "route_oracles",
                        "tasks": 1,
                        "expected_capabilities": ["autoreason"],
                        "public_safe_capabilities": ["autoreason"],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )
    flash = tmp_path / "flash.jsonl"
    flash.write_text(
        json.dumps(
            {
                "task_id": "flash-autoreason",
                "route_decision_schema_version": "nexus_route_decision_v1",
                "expected_capability_receipt_coverage": {
                    "expected": ["autoreason"],
                    "public_safe": [],
                    "missing": ["autoreason"],
                    "failure_reasons": {"autoreason": "missing_receipt"},
                    "all_public_safe": False,
                },
                "capability_receipts": [],
            }
        ),
        encoding="utf-8",
    )

    payload = build_invocation_matrix(
        arms=[ArmInput("codex", smoke), ArmInput("flash", flash)],
        required={"autoreason"},
    )

    assert payload["passed"] is False
    kinds = {failure["kind"] for failure in payload["failures"]}
    assert "arm_failed" in kinds
    arm_failure = next(f for f in payload["failures"] if f["kind"] == "arm_failed")
    assert arm_failure["failures"][0]["kind"] == "expected_capability_not_invoked_with_evidence"
    assert payload["matrix"]["autoreason"]["integrity_heatmap"]["severity"] == "red"
    assert "required_never_selected" in payload["matrix"]["autoreason"]["integrity_heatmap"]["reasons"]


def test_invocation_matrix_marks_invoked_without_evidence_as_heatmap_red(tmp_path: Path):
    flash = tmp_path / "flash.jsonl"
    receipt = _receipt("swarm")
    receipt["evidence_present"] = False
    flash.write_text(
        json.dumps(
            {
                "task_id": "flash-swarm",
                "route_decision_schema_version": "nexus_route_decision_v1",
                "expected_capability_receipt_coverage": {
                    "expected": [],
                    "public_safe": [],
                    "missing": [],
                    "failure_reasons": {},
                    "all_public_safe": False,
                },
                "capability_receipts": [receipt],
            }
        ),
        encoding="utf-8",
    )

    payload = build_invocation_matrix(arms=[ArmInput("flash", flash)], required=set())

    assert payload["matrix"]["swarm"]["integrity_heatmap"]["severity"] == "red"
    assert "invoked_no_evidence" in payload["matrix"]["swarm"]["integrity_heatmap"]["reasons"]


def test_invocation_matrix_exposes_runtime_backed_executor_claim_scope(tmp_path: Path):
    smoke = tmp_path / "capability_route_smoke_summary.json"
    smoke.write_text(
        json.dumps(
            {
                "passed": True,
                "suites": [
                    {
                        "suite": "route_oracles",
                        "tasks": 1,
                        "expected_capabilities": ["swarm"],
                        "public_safe_capabilities": ["swarm"],
                    }
                ],
                "failures": [],
            }
        ),
        encoding="utf-8",
    )

    payload = build_invocation_matrix(arms=[ArmInput("codex", smoke)], required={"swarm"})

    assert payload["passed"] is True
    assert payload["matrix"]["swarm"]["pending_executor"] is False
    assert payload["matrix"]["swarm"]["runtime_claim_allowed"] is True
    assert payload["matrix"]["swarm"]["allowed_claim_scope"] == "runtime_backed"
    assert payload["matrix"]["swarm"]["wiring_status"] == "runtime_backed"
    assert payload["diagnostics"] == []
