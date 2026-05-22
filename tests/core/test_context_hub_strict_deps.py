from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexus.core.context_hub import ContextDependencies, ContextHub
from nexus.core.context_runtime_adapter import StatelessContextCoordinator, build_runtime_context_payload
from nexus.core.context_view import ContextDependencies as SplitContextDependencies
from nexus.core.context_view import StateView


def test_context_hub_reexports_split_context_view_contracts():
    assert ContextDependencies is SplitContextDependencies
    view = StateView(
        metadata={"task_type": "conversation"},
        route_receipts=[{"selected": True, "invoked": True, "evidence_present": True, "gate_passed": False}],
    )

    assert view.get_conversation_metadata() == {}
    assert view.receipt_summary() == {"selected": 1, "invoked": 1, "evidence": 1, "gate": 0}


def test_context_hub_strict_deps_requires_dependency_container(tmp_path):
    with pytest.raises(ValueError, match="strict_deps_requires_context_dependencies"):
        ContextHub(str(tmp_path), strict_deps=True)


def test_context_hub_strict_deps_uses_only_injected_dependencies(tmp_path):
    memory_service = SimpleNamespace(name="memory")
    wisdom_vault = SimpleNamespace(name="wisdom")
    belief_engine = SimpleNamespace(name="belief")
    knowledge_injector = SimpleNamespace(name="knowledge")
    prompt_builder = SimpleNamespace(name="prompt")
    deps = ContextDependencies(
        memory_service=memory_service,
        wisdom_vault=wisdom_vault,
        belief_engine=belief_engine,
        knowledge_injector=knowledge_injector,
        prompt_builder=prompt_builder,
    )

    hub = ContextHub(str(tmp_path), deps=deps, strict_deps=True)

    assert hub.memory_service is memory_service
    assert hub.wisdom_vault is wisdom_vault
    assert hub.belief_engine is belief_engine
    assert hub.knowledge_injector is knowledge_injector
    assert hub.prompt_builder is prompt_builder


def test_context_hub_strict_deps_allows_explicit_none_without_fallback(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    assert hub.memory_service is None
    assert hub.wisdom_vault is None
    assert hub.belief_engine is None
    assert hub.knowledge_injector is None
    assert hub.prompt_builder is None


def test_context_hub_strict_deps_can_be_forced_by_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_CONTEXT_STRICT_DEPS", "1")

    with pytest.raises(ValueError, match="strict_deps_requires_context_dependencies"):
        ContextHub(str(tmp_path))


def test_context_hub_builds_read_only_context_budget_receipt(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    receipt = hub.build_context_budget_receipt(
        task_id="ctx-budget",
        token_budget=120,
        extra_sources=[
            {"source_id": "research:expensive", "kind": "research", "estimated_tokens": 500, "priority": 10}
        ],
    )

    assert receipt["status"] == "PASS"
    assert receipt["task_id"] == "ctx-budget"
    assert receipt["preserved_L0_L1"] is True
    assert [source["kind"] for source in receipt["kept_sources"][:2]] == ["L0", "L1"]
    assert receipt["dropped_sources"] == [
        {
            "source_id": "research:expensive",
            "kind": "research",
            "estimated_tokens": 500,
            "drop_reason_code": "budget_exhausted",
        }
    ]


def test_context_hub_context_budget_receipt_returns_when_core_context_exceeds_budget(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    receipt = hub.build_context_budget_receipt(task_id="ctx-budget", token_budget=1)

    assert receipt["status"] == "RETURN"
    assert "required_context_over_budget" in receipt["blockers"]


def test_context_hub_builds_context_assembly_contract(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    contract = hub.build_context_assembly_contract(
        task_id="ctx-contract",
        token_budget=120,
        extra_sources=[
            {"source_id": "research:expensive", "kind": "research", "estimated_tokens": 500, "priority": 10}
        ],
    )

    assert contract["status"] == "PASS"
    assert contract["task_id"] == "ctx-contract"
    assert contract["preserved_L0_L1"] is True
    assert contract["receipt"]["dropped_sources"][0]["drop_reason_code"] == "budget_exhausted"
    assert contract["claim_boundary"][0] == "Context assembly contracts select context under budget only."


def test_context_hub_context_assembly_contract_returns_when_core_context_exceeds_budget(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    contract = hub.build_context_assembly_contract(task_id="ctx-contract", token_budget=1)

    assert contract["status"] == "RETURN"
    assert "receipt_not_pass" in contract["blockers"]


def test_context_hub_runtime_context_adapter_receipt_is_read_only(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    receipt = hub.build_runtime_context_adapter_receipt(task_id="ctx-runtime", token_budget=120)

    assert receipt["schema"] == "nexus.runtime_context_adapter_receipt.v1"
    assert receipt["status"] == "PASS"
    assert receipt["runtime_dispatch_changed"] is False
    assert receipt["runtime_update_allowed"] is False
    assert receipt["public_benchmark_allowed"] is False
    assert receipt["contract"]["task_id"] == "ctx-runtime"


def test_context_hub_runtime_context_payload_assembles_only_after_receipt_pass(tmp_path, monkeypatch):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    called = {"assemble": False}

    def fake_assemble_context(*, task_id, layers, budget=4000, bayesian_params=None):
        called["assemble"] = True
        assert task_id == "ctx-runtime"
        assert layers == [0, 1]
        assert budget == 120
        return "assembled context"

    monkeypatch.setattr(hub, "assemble_context", fake_assemble_context)

    payload = hub.assemble_context_with_runtime_contract("ctx-runtime", [0, 1], budget=120)

    assert called["assemble"] is True
    assert payload["schema"] == "nexus.runtime_context_payload.v1"
    assert payload["status"] == "PASS"
    assert payload["context"] == "assembled context"
    assert payload["adapter_receipt"]["status"] == "PASS"
    assert payload["runtime_dispatch_changed"] is False
    assert payload["runtime_update_allowed"] is False
    assert payload["public_benchmark_allowed"] is False


def test_context_hub_runtime_context_payload_returns_before_assembly_when_receipt_fails(tmp_path, monkeypatch):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("assemble_context should not run after receipt RETURN")

    monkeypatch.setattr(hub, "assemble_context", fail_if_called)

    payload = hub.assemble_context_with_runtime_contract("ctx-runtime", [0, 1], budget=1)

    assert payload["schema"] == "nexus.runtime_context_payload.v1"
    assert payload["status"] == "RETURN"
    assert payload["context"] == ""
    assert payload["adapter_receipt"]["status"] == "RETURN"
    assert "receipt_not_pass" in payload["blockers"]
    assert payload["runtime_dispatch_changed"] is False
    assert payload["runtime_update_allowed"] is False
    assert payload["public_benchmark_allowed"] is False


def test_context_hub_runtime_context_payload_blocks_quarantined_skill_before_assembly(tmp_path, monkeypatch):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("assemble_context should not run with quarantined skill context")

    monkeypatch.setattr(hub, "assemble_context", fail_if_called)

    payload = hub.assemble_context_with_runtime_contract(
        "ctx-runtime",
        [0, 1],
        budget=120,
        extra_sources=[
            {
                "source_id": "candidate-skill-from-example",
                "kind": "skill",
                "estimated_tokens": 10,
                "skill_tier": "candidate_inbox",
            }
        ],
    )

    assert payload["status"] == "RETURN"
    assert payload["context"] == ""
    assert payload["adapter_receipt"]["status"] == "RETURN"
    assert "quarantined_skill_context:candidate-skill-from-example" in payload["blockers"]


def test_context_runtime_adapter_returns_without_calling_assembler_when_receipt_fails():
    def fail_if_called(*args, **kwargs):
        raise AssertionError("assembler should not run")

    payload = build_runtime_context_payload(
        task_id="ctx-runtime",
        layers=[0, 1],
        budget=1,
        adapter_receipt={
            "schema": "nexus.runtime_context_adapter_receipt.v1",
            "status": "RETURN",
            "blockers": ["receipt_not_pass"],
        },
        assembler=fail_if_called,
    )

    assert payload["schema"] == "nexus.runtime_context_payload.v1"
    assert payload["status"] == "RETURN"
    assert payload["context"] == ""
    assert payload["blockers"] == ["receipt_not_pass"]


def test_context_runtime_adapter_blocks_cross_boundary_receipts():
    def fail_if_called(*args, **kwargs):
        raise AssertionError("assembler should not run")

    payload = build_runtime_context_payload(
        task_id="ctx-runtime",
        layers=[0, 1],
        budget=120,
        adapter_receipt={
            "schema": "nexus.runtime_context_adapter_receipt.v1",
            "status": "PASS",
            "runtime_dispatch_changed": True,
            "runtime_update_allowed": True,
            "public_benchmark_allowed": True,
            "blockers": [],
        },
        assembler=fail_if_called,
    )

    assert payload["status"] == "RETURN"
    assert payload["context"] == ""
    assert "adapter_attempted_runtime_dispatch_change" in payload["blockers"]
    assert "adapter_attempted_runtime_update" in payload["blockers"]
    assert "adapter_attempted_public_benchmark_unlock" in payload["blockers"]


def test_stateless_context_coordinator_wires_receipt_builder_and_assembler():
    calls = {"receipt": False, "assemble": False}

    def receipt_builder(*, task_id, token_budget, state_view=None, extra_sources=None):
        calls["receipt"] = True
        assert task_id == "ctx-runtime"
        assert token_budget == 99
        assert state_view == {"state": "view"}
        assert extra_sources == [{"source_id": "x"}]
        return {"schema": "nexus.runtime_context_adapter_receipt.v1", "status": "PASS", "blockers": []}

    def assembler(*, task_id, layers, budget, bayesian_params=None):
        calls["assemble"] = True
        assert task_id == "ctx-runtime"
        assert layers == [0, 1]
        assert budget == 99
        assert bayesian_params == {"confidence": 0.8}
        return "context"

    coordinator = StatelessContextCoordinator(receipt_builder=receipt_builder, assembler=assembler)

    payload = coordinator.assemble(
        task_id="ctx-runtime",
        layers=[0, 1],
        budget=99,
        bayesian_params={"confidence": 0.8},
        state_view={"state": "view"},
        extra_sources=[{"source_id": "x"}],
    )

    assert calls == {"receipt": True, "assemble": True}
    assert payload["status"] == "PASS"
    assert payload["context"] == "context"
