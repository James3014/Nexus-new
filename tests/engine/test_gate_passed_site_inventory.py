"""#1869: every adapter gate_passed is either a bound claim gate or a documented non-claim signal."""

from __future__ import annotations

import ast
import inspect

import pytest

from nexus.engine import capability_receipt_adapters as mod
from nexus.engine.capability_receipt_adapters import (
    BOUND_CLAIM_GATE_ADAPTERS,
    NON_CLAIM_GATE_ADAPTERS,
    RECEIPT_ADAPTERS,
    claim_gate_binding_reasons,
)

_BINDING = {"verifier_status": "pass", "source_hash": "sha256:" + "c" * 64}


def test_every_registered_adapter_is_classified_exactly_once() -> None:
    assert not (BOUND_CLAIM_GATE_ADAPTERS & set(NON_CLAIM_GATE_ADAPTERS))
    classified = BOUND_CLAIM_GATE_ADAPTERS | set(NON_CLAIM_GATE_ADAPTERS)
    assert set(RECEIPT_ADAPTERS) == classified, (
        "new/removed adapter must be added to BOUND_CLAIM_GATE_ADAPTERS or NON_CLAIM_GATE_ADAPTERS: "
        f"{sorted(set(RECEIPT_ADAPTERS) ^ classified)}"
    )


def _derives_gate_from_non_constant(cls: ast.ClassDef) -> bool:
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("gate_passed", "base_gate") for t in node.targets
        ):
            if not (isinstance(node.value, ast.Constant) and node.value.value is False):
                return True
        if isinstance(node, ast.keyword) and node.arg == "gate_passed":
            if not (isinstance(node.value, ast.Constant) and node.value.value is False):
                if not (isinstance(node.value, ast.Name) and node.value.id == "gate_passed"):
                    return True
    return False


def test_no_unclassified_adapter_class_derives_gate_passed() -> None:
    """AST scan: a class deriving gate_passed must belong to a classified registered adapter."""
    known = {type(a).__name__ for a in RECEIPT_ADAPTERS.values()}
    tree = ast.parse(inspect.getsource(mod))
    offenders = [
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and _derives_gate_from_non_constant(node)
        and node.name not in known
        and node.name not in {"CapabilityReceiptAdapter"}
        and not any(isinstance(b, ast.Name) and b.id in known for b in node.bases)
    ]
    assert offenders == [], f"gate_passed derived in unclassified adapter classes: {offenders}"


def test_non_claim_adapters_have_documented_reason() -> None:
    assert all(isinstance(r, str) and r for r in NON_CLAIM_GATE_ADAPTERS.values())


# name -> payload whose pre-binding condition passes for that adapter
_BOUND_PAYLOADS = {
    "bdd_acceptance_skill": {
        "bdd_acceptance_refs": ["bdd:1"],
        "bdd_acceptance_skill_gate_passed": True,
        "business_verified": True,
    },
    "formal_report": {
        "formal_report_path": "r.md",
        "formal_report_schema_version": "nexus_formal_report_v1",
        "formal_report_gate_passed": True,
    },
    "acceptance_check": {"acceptance_refs": ["acc:1"], "acceptance_check_gate_passed": True},
    "benchmark": {"benchmark_refs": ["bench:1"], "benchmark_gate_passed": True},
}


@pytest.mark.parametrize("name", sorted(_BOUND_PAYLOADS))
def test_bound_site_fails_closed_without_artifact_and_source_hash(name: str) -> None:
    adapter = RECEIPT_ADAPTERS[name]
    base = _BOUND_PAYLOADS[name]
    receipt = adapter.build(claim_verified=True, payload=dict(base))
    assert receipt.gate_passed is False
    assert "missing_verifier_artifact" in receipt.failure_reason
    assert "missing_source_hash" in receipt.failure_reason
    only_status = adapter.build(claim_verified=True, payload={**base, "verifier_status": "pass"})
    assert only_status.gate_passed is False and "missing_source_hash" in only_status.failure_reason
    only_hash = adapter.build(
        claim_verified=True, payload={**base, "source_hash": "sha256:" + "a" * 64}
    )
    assert (
        only_hash.gate_passed is False and "missing_verifier_artifact" in only_hash.failure_reason
    )


@pytest.mark.parametrize("name", sorted(_BOUND_PAYLOADS))
def test_bound_site_passes_with_artifact_and_source_hash(name: str) -> None:
    receipt = RECEIPT_ADAPTERS[name].build(
        claim_verified=True, payload={**_BOUND_PAYLOADS[name], **_BINDING}
    )
    assert receipt.gate_passed is True
    # contribution authority stays fail-closed (#453)
    assert receipt.outcome_contributed is False


@pytest.mark.parametrize("name", ["claim_gate", "artifact_gate", "delivery_gate", "mempalace_gate"])
def test_gate_adapters_report_binding_reasons_and_never_pass_unbound(name: str) -> None:
    payload = {
        "claim_refs": ["x"],
        "artifact_refs": ["x"],
        "delivery_refs": ["x"],
        "mempalace_refs": ["x"],
    }
    receipt = RECEIPT_ADAPTERS[name].build(claim_verified=True, payload=payload)
    assert receipt.gate_passed is False
    if name in ("claim_gate", "delivery_gate"):
        assert receipt.failure_reason == "missing_verifier_artifact;missing_source_hash"
    bound = RECEIPT_ADAPTERS[name].build(claim_verified=True, payload={**payload, **_BINDING})
    assert bound.gate_passed is False  # unauthenticated payload verifier still cannot pass (#453)


def test_binding_reasons_helper_is_public_and_content_validated() -> None:
    assert claim_gate_binding_reasons({}) == ["missing_verifier_artifact", "missing_source_hash"]
    assert claim_gate_binding_reasons(dict(_BINDING)) == []
