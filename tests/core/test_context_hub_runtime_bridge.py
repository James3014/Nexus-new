from __future__ import annotations

import pytest

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
    assert result is None
    paths = list(tmp_path.rglob("*.json"))
    assert paths
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["task_id"] == "task-runtime"
    assert payload["body"] == "Root Cause: root cause\nLesson: lesson"
    assert payload["extra"]["task_id"] == "task-runtime"


def test_context_hub_lesson_wrapper_passes_payload_and_returns_none(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    seen = {}

    def writer(*, failure_signature, root_cause, lesson, metadata):
        seen.update(
            failure_signature=failure_signature,
            root_cause=root_cause,
            lesson=lesson,
            metadata=metadata,
        )
        return tmp_path / "captured-card.json"

    from dataclasses import replace

    hub.runtime_hub.deps = replace(hub.runtime_hub.deps, learning_writer=writer)
    assert hub.record_crystal_lesson("sig", "cause", "lesson", {"task_id": "t"}) is None
    assert seen == {
        "failure_signature": "sig",
        "root_cause": "cause",
        "lesson": "lesson",
        "metadata": {"task_id": "t"},
    }


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
        (
            "assemble_repair_pack",
            (type("D", (), {"summary": "s", "pseudo_flows": [], "hotspots": []})(), [], None),
            {"source": "runtime"},
        ),
        ("assemble_context", ("task", [0, 1]), "runtime"),
    ):
        setattr(hub.runtime_hub, name, lambda *args, _value=expected, **kwargs: _value)
        assert getattr(hub, name)(*args) == expected


def test_context_hub_assembly_uses_fail_closed_memory_and_wiki_bound_methods(tmp_path):
    class BrokenMemory:
        def cached_search(self, _key):
            raise RuntimeError("memory unavailable")

    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(memory_service=BrokenMemory()),
        strict_deps=True,
    )
    diag = hub.assemble_diag_pack([], "diagnostic")
    research = hub.assemble_research_pack("query", [])
    assert diag["memory_reminders"] == {"reminders": [], "total_sources": 0}
    assert diag["wiki_retrieval"]["retrieval_receipt"]["blockers"] == [
        "wiki_runtime_not_configured"
    ]
    assert research["memory_reminders"] == {"reminders": [], "total_sources": 0}


def test_context_hub_wiki_exception_keeps_structured_receipt(tmp_path):
    class BrokenWiki:
        def retrieve(self, _query, max_results=3):
            raise RuntimeError("wiki unavailable")

    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(wiki_knowledge_agent=BrokenWiki()),
        strict_deps=True,
    )
    pack = hub.assemble_diag_pack([], "diagnostic")
    assert pack["wiki_retrieval"]["retrieval_receipt"]["blockers"] == ["wiki_runtime_exception"]


def test_runtime_context_bridge_accepts_explicit_reader_callbacks(tmp_path):
    from nexus.core.context_runtime_bridge import build_runtime_context_hub

    memory_calls = []
    wiki_calls = []

    def memory(phase):
        memory_calls.append(phase)
        return {"reminders": [phase], "total_sources": 1}

    def wiki(query, max_results=3):
        wiki_calls.append((query, max_results))
        return {"context": "callback", "selected_sources": []}

    state = type("State", (), {"task_id": "t", "steps_history": []})()
    runtime = build_runtime_context_hub(
        project_root=tmp_path,
        state_reader=lambda: state,
        text_reader=lambda *_args: "rules",
        memory_reader=memory,
        wiki_reader=wiki,
    )
    assert runtime.assemble_research_pack("q", [])["memory_reminders"] == {
        "reminders": ["X"],
        "total_sources": 1,
    }
    assert runtime.assemble_diag_pack([], "d")["wiki_context"] == "callback"
    assert memory_calls == ["X", "D"]
    assert wiki_calls == [("d", 3)]


def test_context_hub_feature_uses_aggregate_memory_once(tmp_path):
    class Memory:
        def __init__(self):
            self.aggregate_calls = 0
            self.cached_calls = 0

        def aggregate_memory(self):
            self.aggregate_calls += 1
            return {"aggregate": True}

        def cached_search(self, _key):
            self.cached_calls += 1
            return {"cached": True}

    memory = Memory()
    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(memory_service=memory),
        strict_deps=True,
    )
    assert hub.assemble_feature_pack()["memory"] == {"aggregate": True}
    assert memory.aggregate_calls == 1
    assert memory.cached_calls == 0


def test_context_hub_feature_without_memory_returns_empty_mapping(tmp_path):
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    assert hub.assemble_feature_pack()["memory"] == {}


def test_context_hub_feature_aggregate_exception_propagates(tmp_path):
    class BrokenMemory:
        def aggregate_memory(self):
            raise RuntimeError("aggregate unavailable")

    hub = ContextHub(
        str(tmp_path),
        deps=ContextDependencies(memory_service=BrokenMemory()),
        strict_deps=True,
    )
    import pytest

    with pytest.raises(RuntimeError, match="aggregate unavailable"):
        hub.assemble_feature_pack()


@pytest.mark.parametrize(
    ("citations", "expected"),
    [
        ([{"claim": "claim one"}, {"claim": "claim two"}], ["claim one", "claim two"]),
        ([], None),
    ],
)
def test_context_hub_diag_pack_preserves_learn_mode_citations(
    tmp_path, monkeypatch, citations, expected
):
    class LearnMode:
        def __init__(self, _root):
            pass

        def ask(self, **_kwargs):
            return {"citations": citations}

    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", LearnMode)
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    pack = hub.assemble_diag_pack([], "diagnostic")
    if expected is None:
        assert "claims_diag_hints" not in pack
    else:
        assert pack["claims_diag_hints"] == expected


def test_context_hub_diag_pack_survives_learn_mode_exception(tmp_path, monkeypatch):
    class BrokenLearnMode:
        def __init__(self, _root):
            pass

        def ask(self, **_kwargs):
            raise RuntimeError("learn mode unavailable")

    monkeypatch.setattr("nexus.research.learn_mode.LearnModeService", BrokenLearnMode)
    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    pack = hub.assemble_diag_pack([], "diagnostic")
    assert pack["failure_summary"] == "diagnostic"
    assert "claims_diag_hints" not in pack


@pytest.mark.parametrize("confidence", [0.2, 0.8])
def test_context_hub_diag_pack_belief_warning_threshold(tmp_path, confidence):
    class Belief:
        def get_confidence(self, key):
            assert key == "AUDIT_FAILURE_1"
            return confidence

    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    hub.belief_engine = Belief()
    pack = hub.assemble_diag_pack([], "diagnostic")
    if confidence < 0.5:
        assert "belief_warning" in pack
    else:
        assert "belief_warning" not in pack


def test_context_hub_diag_pack_propagates_belief_exception(tmp_path):
    class BrokenBelief:
        def get_confidence(self, _key):
            raise RuntimeError("belief unavailable")

    hub = ContextHub(str(tmp_path), deps=ContextDependencies(), strict_deps=True)
    hub.belief_engine = BrokenBelief()
    with pytest.raises(RuntimeError, match="belief unavailable"):
        hub.assemble_diag_pack([], "diagnostic")
