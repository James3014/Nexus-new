from nexus.core.belief_contracts import HealingArtifact
from nexus.core.healing_artifacts import (
    artifact_from_packet,
    artifact_to_packet,
    healing_artifact_report_entry,
    quiet_moment_healing_packet,
    quiet_moment_report_entry,
    read_healing_artifact,
    write_healing_artifact,
)


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


def test_healing_artifact_packet_roundtrip_is_transport_only():
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Diagnose here, execute elsewhere after validation.",
    )

    packet = artifact_to_packet(artifact)

    assert packet["type"] == "healing_artifact"
    assert packet["schema_version"] == "nexus_healing_artifact.v1"
    assert artifact_from_packet(packet) == artifact


def test_healing_artifact_report_entry_cites_persisted_artifact(tmp_path):
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )
    path = write_healing_artifact(tmp_path, artifact)

    row = healing_artifact_report_entry(path)

    assert row["artifact_id"] == "heal-1"
    assert row["evidence_id"] == "EV-1"
    assert row["path"] == str(path)


def test_quiet_moment_healing_packet_is_report_safe_and_non_mutating():
    packet = quiet_moment_healing_packet(
        reason="swarm divergence",
        affected_nodes=["node-a"],
        resume_after_seconds=30,
        evidence_id="EV-QM-1",
    )

    row = quiet_moment_report_entry(packet)

    assert packet["production_writes_allowed"] is False
    assert packet["event"]["production_writes_allowed"] is False
    assert row == {
        "schema_version": "nexus_quiet_moment_report_entry.v1",
        "evidence_id": "EV-QM-1",
        "reason": "swarm divergence",
        "affected_nodes": ["node-a"],
        "resume_after_seconds": 30,
        "production_writes_allowed": False,
        "allowed_actions": ["observe", "report", "rollback"],
    }


def test_quiet_moment_report_entry_rejects_wrong_packet_type():
    try:
        quiet_moment_report_entry({"type": "healing_artifact"})
    except ValueError as exc:
        assert "not a quiet moment" in str(exc)
    else:
        raise AssertionError("quiet_moment_report_entry should reject wrong packets")
