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


def test_context_hub_runtime_lesson_writer_persists_physical_card(tmp_path):
    import json

    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    result = hub.record_crystal_lesson(
        "sig:runtime", "root cause", "lesson", {"task_id": "task-runtime"}
    )
    assert result is not None
    payload = json.loads(open(result, encoding="utf-8").read())
    assert payload["task_id"] == "task-runtime"
    assert payload["body"] == "Root Cause: root cause\nLesson: lesson"
    assert payload["extra"]["task_id"] == "task-runtime"


def test_context_hub_runtime_context_uses_bound_compactor(tmp_path):
    from dataclasses import replace

    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    calls = []
    original = hub.runtime_hub.deps.compactor

    def spy(value, confidence=0.5):
        calls.append((value, confidence))
        return original(value, confidence)

    hub.runtime_hub.deps = replace(hub.runtime_hub.deps, compactor=spy)
    hub.assemble_context("task-runtime", [0, 1], budget=4000)
    assert calls


def test_context_hub_public_operations_delegate_to_runtime(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    for name, args, expected in (
        ("assemble_diag_pack", ([{"file": "x.py"}], "bad"), {"source": "runtime"}),
        ("assemble_research_pack", ("q", []), {"source": "runtime"}),
        ("assemble_conversation_pack", (), {"source": "runtime"}),
        ("assemble_repair_pack", (type("D", (), {"summary": "s", "pseudo_flows": [], "hotspots": []})(), [], None), {"source": "runtime"}),
        ("assemble_context", ("task", [0, 1]), "runtime"),
    ):
        setattr(hub.runtime_hub, name, lambda *args, _value=expected, **kwargs: _value)
        assert getattr(hub, name)(*args) == expected
