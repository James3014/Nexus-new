import pytest

from nexus.core.belief_contracts import HealingArtifact


def test_healing_artifact_is_frozen_and_has_independent_metadata():
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Patch config fallback",
    )
    other = HealingArtifact(
        task_id="task-2",
        artifact_id="heal-2",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-2",
        summary="Patch storage fallback",
    )

    artifact.metadata["k"] = "v"
    assert other.metadata == {}
    with pytest.raises(Exception):
        artifact.task_id = "mutated"
