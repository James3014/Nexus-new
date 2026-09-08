from __future__ import annotations

import inspect

from nexus.services import online_payload_contract as contract
from nexus.services import unified_runtime as legacy


def test_legacy_import_surface_reexports_exact_contract_objects() -> None:
    assert legacy.normalize_online_invoker_payload is contract.normalize_online_invoker_payload
    assert legacy.online_payload_indicates_non_delivery is contract.online_payload_indicates_non_delivery
    assert legacy._ONLINE_NON_DELIVERY_MARKERS is contract._ONLINE_NON_DELIVERY_MARKERS
    assert inspect.signature(legacy.normalize_online_invoker_payload) == inspect.signature(
        contract.normalize_online_invoker_payload
    )


def test_normalization_preserves_contract_and_extra_key_behavior() -> None:
    payload = contract.normalize_online_invoker_payload(
        provider="fixture",
        task_id="task-1",
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"ok": True},
        usage={"tokens": 2},
        evidence_refs=["e:1"],
        extra={"custom": "kept", "provider": "cannot-overwrite"},
    )
    assert payload["provider"] == "fixture"
    assert payload["usage"] == {"tokens": 2}
    assert payload["evidence_refs"] == ["e:1"]
    assert payload["custom"] == "kept"


def test_non_delivery_markers_fail_closed_in_nested_and_hostile_payloads() -> None:
    for payload in (
        None,
        {"response": {"raw_response": "HTTP Error 401"}},
        {"response": {"error": "authentication failed"}},
        {"status": "FAILED"},
    ):
        assert contract.online_payload_indicates_non_delivery(payload) is True
    result = contract.normalize_online_invoker_payload(
        provider="fixture",
        task_id="task-2",
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
        response={"status": "ERROR"},
    )
    assert result["output_delivered"] is False
    assert result["gate_passed"] is False
    assert result["error"] == "online_non_delivery_detected"


def test_new_definition_patchpoint_controls_legacy_reexport(monkeypatch) -> None:
    monkeypatch.setattr(contract, "online_payload_indicates_non_delivery", lambda payload: True)
    result = legacy.normalize_online_invoker_payload(
        provider="fixture",
        task_id="task-patchpoint",
        invoked=True,
        output_delivered=True,
        gate_passed=True,
        provider_call_count=1,
    )
    assert result["output_delivered"] is False
    assert result["gate_passed"] is False
    assert result["error"] == "online_non_delivery_detected"
