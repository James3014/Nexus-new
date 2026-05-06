from __future__ import annotations

from nexus.engine.capability_receipt_policy import (
    RECEIPT_BACKED_CAPABILITIES,
    is_public_claim_capability,
    is_receipt_backed_capability,
    is_route_quality_actionable_receipt,
    public_gate_ignored_reasons,
    public_safe_receipt_names,
    route_quality_ignored_reasons,
)
from nexus.engine.capability_receipt_adapters import RECEIPT_ADAPTERS
from nexus.engine.capability_aliases import normalize_capability_name


def test_receipt_backed_capabilities_match_adapter_registry_after_alias_normalization():
    adapter_capabilities = {normalize_capability_name(name) for name in RECEIPT_ADAPTERS}

    assert adapter_capabilities - RECEIPT_BACKED_CAPABILITIES == set()
    assert RECEIPT_BACKED_CAPABILITIES - adapter_capabilities == set()


def test_receipt_policy_normalizes_legacy_judge_panel_alias():
    assert is_public_claim_capability("llm_judge_panel") is True
    assert is_receipt_backed_capability("llm_judge_panel") is True
    assert "llm_judge_panel" not in RECEIPT_BACKED_CAPABILITIES


def test_route_quality_policy_ignores_known_non_actionable_public_capability_reason():
    receipt = {
        "name": "ddtree",
        "selected": True,
        "invoked": False,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "failure_reason": "selected_without_invocation",
    }

    assert "selected_without_invocation" in route_quality_ignored_reasons("ddtree")
    assert is_route_quality_actionable_receipt(receipt) is False


def test_route_quality_policy_counts_runtime_observed_receipt_even_when_not_public_safe():
    receipt = {
        "name": "research",
        "selected": True,
        "invoked": True,
        "evidence_present": False,
        "gate_passed": False,
        "outcome_contributed": False,
        "failure_reason": "invoked_without_evidence",
    }

    assert is_route_quality_actionable_receipt(receipt) is True


def test_public_gate_policy_has_extra_autoreason_grace_reason():
    assert "selected_without_invocation" in public_gate_ignored_reasons("autoreason")


def test_public_safe_receipt_names_returns_normalized_names_only():
    assert public_safe_receipt_names(
        [
            {"name": "llm_judge_panel", "public_claim_safe": True},
            {"name": "research", "public_claim_safe": False},
            {"name": "", "public_claim_safe": True},
        ]
    ) == {"judge_panel"}
