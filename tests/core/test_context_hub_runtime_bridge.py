from __future__ import annotations

from nexus.core.context_hub import ContextDependencies, ContextHub


def test_context_hub_assembly_delegates_to_runtime_hub(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    seen: dict[str, object] = {}

    def runtime_feature(plan=None):
        seen["plan"] = plan
        return {"source": "runtime"}

    hub.runtime_hub.assemble_feature_pack = runtime_feature
    assert hub.assemble_feature_pack({"steps": ["inspect"]}) == {"source": "runtime"}
    assert seen["plan"] == {"steps": ["inspect"]}
