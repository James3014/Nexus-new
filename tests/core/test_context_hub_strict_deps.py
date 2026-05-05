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
