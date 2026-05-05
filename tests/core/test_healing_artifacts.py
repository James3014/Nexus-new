from nexus.core.belief_contracts import HealingArtifact
from nexus.core.healing_artifacts import read_healing_artifact, write_healing_artifact


def test_healing_artifact_roundtrip_persists_json(tmp_path):
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal/unsafe id",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
        metadata={"risk": "low"},
    )

    path = write_healing_artifact(tmp_path, artifact)
    loaded = read_healing_artifact(path)

    assert path.name == "heal-unsafe-id.json"
    assert loaded == artifact
