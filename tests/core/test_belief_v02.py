from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nexus.core.belief_v02 import (
    ArtifactRecord,
    BeliefRecord,
    EdgeRecord,
    KnowledgeStore,
)

_REPO = Path(__file__).resolve().parents[2]


def _healing_engine(root: Path):
    spec = importlib.util.spec_from_file_location(
        "predictive_healing_v02", _REPO / "scripts/ops/predictive_healing.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PredictiveHealingEngine(repo_root=root)


def test_belief_and_artifact_schema_fields(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / ".nexusknowledge")
    store.write_belief(
        BeliefRecord("B1", "c", supported_by_artifacts=["A0"], invalidates_artifacts=["A1"])
    )
    store.write_artifact(
        ArtifactRecord("A1", "src/x.py", supersedes_id="A0", linked_beliefs=["B1"])
    )
    belief = store.load(store.beliefs_path)[0]
    artifact = store.load(store.artifacts_path)[0]
    assert {
        "id",
        "version",
        "type",
        "content",
        "status",
        "supported_by_artifacts",
        "invalidates_artifacts",
    } <= set(belief)
    assert {
        "id",
        "version",
        "type",
        "path_ref",
        "status",
        "supersedes_id",
        "linked_beliefs",
    } <= set(artifact)
    assert belief["supported_by_artifacts"] == ["A0"]
    assert artifact["linked_beliefs"] == ["B1"]


def test_writes_are_idempotent_and_dedupe(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path)
    assert store.write_belief(BeliefRecord("B1", "c")) is True
    assert store.write_belief(BeliefRecord("B1", "c")) is False
    assert store.write_belief(BeliefRecord("B1", "changed")) is True
    assert [r["content"] for r in store.load(store.beliefs_path)] == ["changed"]
    assert store.write_edge(EdgeRecord("B1", "A1")) is True
    assert store.write_edge(EdgeRecord("B1", "A1")) is False
    assert len(store.load(store.edges_path)) == 1


def test_upsert_collapses_existing_duplicates(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path)
    store.beliefs_path.write_text(
        '{"id": "B1", "status": "active"}\n{"id": "B1", "status": "active"}\n'
    )
    store.write_belief(BeliefRecord("B1", "c"))
    assert len(store.load(store.beliefs_path)) == 1


def test_validation_rejects_bad_status_and_edge_type(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path)
    with pytest.raises(ValueError):
        store.write_belief(BeliefRecord("B1", status="failed"))
    with pytest.raises(ValueError):
        store.write_artifact(ArtifactRecord("A1", status="bogus"))
    with pytest.raises(ValueError):
        store.write_edge(EdgeRecord("B1", "A1", "justification"))
    with pytest.raises(ValueError):
        store.write_belief(BeliefRecord(""))


def test_round_trip_through_existing_reader_and_invalidation(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / ".nexusknowledge")
    store.write_belief(BeliefRecord("B1", "premise"))
    store.write_artifact(ArtifactRecord("A1", "src/x.py"))
    store.link("B1", "A1")
    store.link("B1", "A1")
    belief = store.get_belief("B1")
    artifact = store.get_artifact("A1")
    assert belief is not None and belief.invalidates_artifacts == ["A1"]
    assert artifact is not None and artifact.linked_beliefs == ["B1"]

    engine = _healing_engine(tmp_path)
    assert [b["id"] for b in engine.load_jsonl(engine.beliefs_path)] == ["B1"]
    assert len(engine.load_jsonl(engine.edges_path)) == 1
    assert engine.predict_risks() == []  # belief still active

    assert store.set_belief_status("B1", "retracted", "bad premise") == ["A1"]
    stale = engine.load_jsonl(engine.artifacts_path)[0]
    assert stale["status"] == "stale"
    assert "B1" in stale["stale_reason"]
    assert engine.load_jsonl(engine.beliefs_path)[0]["status"] == "retracted"
    # stale artifacts are not re-staled
    assert store.set_belief_status("B1", "superseded") == []


def test_active_status_does_not_invalidate_and_edge_only_dependency(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path)
    store.write_belief(BeliefRecord("B1"))
    store.write_artifact(ArtifactRecord("A1"))
    store.write_edge(EdgeRecord("B1", "A1", "depends_on"))
    assert store.set_belief_status("B1", "active") == []
    assert store.set_belief_status("B1", "superseded") == ["A1"]
    with pytest.raises(KeyError):
        store.set_belief_status("missing", "retracted")
