from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexus.core.context_hub import ContextDependencies, ContextHub


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
