from __future__ import annotations

import hashlib
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from nexus.app import research_receipt_runtime
from nexus.app.research_receipt_runtime import build_capability_receipt_payloads
from nexus.learning import shared_playbook
from tests.learning.test_shared_playbook_g10_promotion import _create_canonical_acceptance_receipt

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _setup_diagnose_runtime(tmp_path: Path, monkeypatch) -> None:
    source = REPO_ROOT / ".agents" / "skills" / "diagnose"
    target = tmp_path / ".agents" / "skills" / "diagnose"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    _create_canonical_acceptance_receipt(target, set_active_status=True)
    monkeypatch.setattr(shared_playbook, "DEFAULT_REPO_ROOT", tmp_path)


class _Receipt:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


def _identity() -> dict[str, Any]:
    manifest_path = (
        shared_playbook.DEFAULT_REPO_ROOT / ".agents" / "skills" / "diagnose" / "playbook.yaml"
    )
    instructions_path = (
        shared_playbook.DEFAULT_REPO_ROOT / ".agents" / "skills" / "diagnose" / "SKILL.md"
    )
    return {
        "playbook_id": "diagnose",
        "version": "1.0.0",
        "status": "ACTIVE",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "instructions_sha256": hashlib.sha256(instructions_path.read_bytes()).hexdigest(),
        "manifest_path": ".agents/skills/diagnose/playbook.yaml",
        "instructions_path": ".agents/skills/diagnose/SKILL.md",
        "primary": True,
        "trace_authority": "DERIVED_ONLY",
        "promotion_record_path": ".agents/skills/diagnose/promotion_record.json",
    }


def _plan(shared_playbook: dict[str, Any] | None = None) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "skill_id": "diagnose",
        "skill_status": "nexus_curated_candidate",
        "capability_mount": "xray",
        "capability": "xray",
        "planner_selected_capability": True,
    }
    if shared_playbook is not None:
        contract["shared_playbook"] = shared_playbook
    return {
        "selected_capabilities": ["xray"],
        "signal_snapshot": {"planned_skill_mount_contracts": [contract]},
    }


def _receipt(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "xray",
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "public_claim_safe": False,
        "evidence_refs": ["xray:witness"],
    }
    payload.update(overrides)
    return payload


def _stub_receipts(monkeypatch, payloads: list[dict[str, Any]]) -> None:
    monkeypatch.setattr(
        research_receipt_runtime,
        "build_trace_receipts",
        lambda **_kwargs: [_Receipt(payload) for payload in payloads],
    )


def test_runtime_receipt_reverifies_and_binds_exact_shared_playbook_identity(monkeypatch) -> None:
    identity = _identity()
    plan = _plan(identity)
    original_plan = deepcopy(plan)
    _stub_receipts(monkeypatch, [_receipt()])

    receipts = build_capability_receipt_payloads(plan, {"capabilities": {}})

    assert plan == original_plan
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["playbook_id"] == identity["playbook_id"]
    assert receipt["playbook_version"] == identity["version"]
    assert receipt["playbook_manifest_sha256"] == identity["manifest_sha256"]
    assert receipt["playbook_instructions_sha256"] == identity["instructions_sha256"]
    assert receipt["playbook_gate_passed"] is True
    assert receipt["playbook_trace"]["authority"] == "DERIVED_ONLY"
    assert receipt["playbook_trace"]["selected_by"] == "CapabilityPlanner"


def test_runtime_receipt_fails_closed_on_hash_mismatch_even_if_public_claim_was_safe(
    monkeypatch,
) -> None:
    identity = _identity()
    identity["manifest_sha256"] = "0" * 64
    _stub_receipts(monkeypatch, [_receipt(public_claim_safe=True)])

    receipt = build_capability_receipt_payloads(_plan(identity), {"capabilities": {}})[0]

    assert receipt["playbook_gate_passed"] is False
    assert receipt["playbook_violation"] == "shared_playbook_runtime_identity_mismatch"
    assert receipt["public_claim_safe"] is False
    assert receipt["gate_passed"] is False
    assert receipt["outcome_contributed"] is False
    assert "playbook_id" not in receipt


def test_runtime_receipt_strips_unselected_playbook_injection(monkeypatch) -> None:
    plan = {
        "selected_capabilities": ["xray"],
        "signal_snapshot": {"planned_skill_mount_contracts": []},
    }
    _stub_receipts(
        monkeypatch,
        [
            _receipt(
                playbook_id="injected",
                playbook_version="9.9.9",
                playbook_manifest_sha256="f" * 64,
                playbook_gate_passed=True,
            )
        ],
    )

    receipt = build_capability_receipt_payloads(plan, {"capabilities": {}})[0]

    assert "playbook_id" not in receipt
    assert "playbook_version" not in receipt
    assert "playbook_manifest_sha256" not in receipt
    assert "playbook_gate_passed" not in receipt


def test_runtime_receipt_rejects_second_primary_playbook(monkeypatch) -> None:
    identity = _identity()
    plan = _plan(identity)
    second = {
        "skill_id": "diagnose-alt",
        "skill_status": "nexus_curated_candidate",
        "capability_mount": "drone",
        "capability": "drone",
        "planner_selected_capability": True,
        "shared_playbook": dict(identity),
    }
    plan["selected_capabilities"].append("drone")
    plan["signal_snapshot"]["planned_skill_mount_contracts"].append(second)
    _stub_receipts(monkeypatch, [_receipt(), _receipt(name="drone")])

    receipts = build_capability_receipt_payloads(plan, {"capabilities": {}})

    assert {receipt["name"] for receipt in receipts} == {"xray", "drone"}
    assert all(receipt["playbook_gate_passed"] is False for receipt in receipts)
    assert all(
        receipt["playbook_violation"] == "shared_playbook_second_primary" for receipt in receipts
    )


def test_runtime_receipt_fails_closed_when_required_playbook_contract_is_missing(
    monkeypatch,
) -> None:
    _stub_receipts(monkeypatch, [_receipt(public_claim_safe=True)])

    receipt = build_capability_receipt_payloads(_plan(), {"capabilities": {}})[0]

    assert receipt["playbook_gate_passed"] is False
    assert receipt["playbook_violation"] == "shared_playbook_runtime_contract_missing"
    assert receipt["public_claim_safe"] is False
    assert receipt["gate_passed"] is False
    assert receipt["outcome_contributed"] is False


def test_runtime_receipt_fails_closed_when_playbook_is_not_planner_selected(
    monkeypatch,
) -> None:
    identity = _identity()
    plan = _plan(identity)
    plan["signal_snapshot"]["planned_skill_mount_contracts"][0]["planner_selected_capability"] = (
        False
    )
    _stub_receipts(monkeypatch, [_receipt(public_claim_safe=True)])

    receipt = build_capability_receipt_payloads(plan, {"capabilities": {}})[0]

    assert receipt["playbook_gate_passed"] is False
    assert receipt["playbook_violation"] == "shared_playbook_not_planner_selected"
    assert receipt["public_claim_safe"] is False
    assert receipt["gate_passed"] is False
    assert receipt["outcome_contributed"] is False


def test_runtime_receipt_fails_closed_on_planner_playbook_violation_without_contract(
    monkeypatch,
) -> None:
    plan = {
        "selected_capabilities": ["xray"],
        "signal_snapshot": {
            "planned_skill_mount_contracts": [],
            "skill_mount_violations": [
                {
                    "skill_name": "diagnose",
                    "path": ".agents/skills/diagnose/SKILL.md",
                    "reason": "shared_playbook_missing",
                    "capability_mount": "xray",
                    "capability": "xray",
                }
            ],
        },
    }
    _stub_receipts(monkeypatch, [_receipt(public_claim_safe=True)])

    receipt = build_capability_receipt_payloads(plan, {"capabilities": {}})[0]

    assert receipt["playbook_gate_passed"] is False
    assert receipt["playbook_violation"] == "shared_playbook_missing"
    assert receipt["public_claim_safe"] is False
    assert receipt["gate_passed"] is False
    assert receipt["outcome_contributed"] is False


def test_runtime_receipt_does_not_infer_capability_from_skill_name_only(monkeypatch) -> None:
    plan = {
        "selected_capabilities": ["xray"],
        "signal_snapshot": {
            "planned_skill_mount_contracts": [],
            "skill_mount_violations": [
                {
                    "skill_name": "diagnose",
                    "reason": "shared_playbook_missing",
                }
            ],
        },
    }
    _stub_receipts(monkeypatch, [_receipt()])

    receipt = build_capability_receipt_payloads(plan, {"capabilities": {}})[0]

    assert "playbook_gate_passed" not in receipt
    assert "playbook_violation" not in receipt
    assert receipt["gate_passed"] is True
    assert receipt["outcome_contributed"] is True
