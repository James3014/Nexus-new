from __future__ import annotations

import importlib

import pytest

from tests.architecture._planner_pairs import ALIASABLE_PAIRS


@pytest.mark.parametrize(("nexus_module", "runtime_module"), ALIASABLE_PAIRS)
def test_nexus_planner_module_is_runtime_module(nexus_module, runtime_module):
    assert importlib.import_module(nexus_module) is importlib.import_module(runtime_module)


def test_patch_through_nexus_name_reaches_runtime_module(monkeypatch):
    import nexus_runtime.planning.services.model_workforce_policy as runtime_mod

    def stub(*args, **kwargs):
        return None

    monkeypatch.setattr("nexus.services.model_workforce_policy.get_freshness_evidence", stub)
    assert runtime_mod.get_freshness_evidence is stub


@pytest.mark.xfail(
    strict=True,
    reason="capability_planner diverges: Nexus-new is ahead of nexus-runtime 0456b78 (#1737 mainchain gate)",
)
def test_capability_planner_identity():
    from nexus_runtime.planning.engine.capability_planner import CapabilityPlanner as B

    from nexus.engine.capability_planner import CapabilityPlanner as A

    assert A is B
