from nexus.core.belief_contracts import HealingArtifact
from nexus.core.healing_artifacts import (
    HealingArtifactKeyPolicy,
    audit_healing_artifact_key_policy,
    artifact_transport_receipt,
    artifact_from_packet,
    artifact_to_packet,
    healing_artifact_report_entry,
    read_healing_artifact,
    sign_healing_artifact,
    verify_healing_artifact_signature,
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
    assert packet["production_writes_allowed"] is False
    assert packet["allowed_actions"] == ["observe", "report"]
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


def test_healing_artifact_signature_verifies_and_survives_roundtrip(tmp_path):
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )

    signed = sign_healing_artifact(artifact, key="secret", key_id="test-key")
    path = write_healing_artifact(tmp_path, signed)
    loaded = read_healing_artifact(path)

    assert signed.signature.startswith("hmac-sha256:")
    assert signed.signature_key_id == "test-key"
    assert verify_healing_artifact_signature(loaded, key="secret") is True


def test_healing_artifact_signature_rejects_tampering():
    artifact = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="test-key",
    )
    tampered = HealingArtifact(
        task_id=artifact.task_id,
        artifact_id=artifact.artifact_id,
        artifact_type=artifact.artifact_type,
        created_at=artifact.created_at,
        evidence_id=artifact.evidence_id,
        summary="Run arbitrary repair",
        metadata=artifact.metadata,
        signature=artifact.signature,
        signature_key_id=artifact.signature_key_id,
    )

    assert verify_healing_artifact_signature(tampered, key="secret") is False


def test_healing_artifact_report_entry_can_require_valid_signature(tmp_path):
    artifact = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="test-key",
    )
    path = write_healing_artifact(tmp_path, artifact)

    row = healing_artifact_report_entry(path, verify_key="secret")

    assert row["artifact_id"] == "heal-1"


def test_healing_artifact_packet_rejects_invalid_signature_when_required():
    signed = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="test-key",
    )
    packet = artifact_to_packet(signed)
    packet["payload"]["summary"] = "Run arbitrary repair"

    try:
        artifact_from_packet(packet, verify_key="secret")
    except ValueError as exc:
        assert "signature" in str(exc)
    else:
        raise AssertionError("expected invalid signature rejection")


def test_healing_artifact_packet_rejects_production_write_permission():
    artifact = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )
    packet = artifact_to_packet(artifact)
    packet["production_writes_allowed"] = True

    try:
        artifact_from_packet(packet)
    except ValueError as exc:
        assert "production writes" in str(exc)
    else:
        raise AssertionError("expected production write rejection")


def test_healing_artifact_key_policy_requires_allowed_valid_signature():
    artifact = sign_healing_artifact(
        HealingArtifact(
            task_id="task-1",
            artifact_id="heal-1",
            artifact_type="repair_plan",
            created_at="2026-05-05T00:00:00Z",
            evidence_id="EV-1",
            summary="Use scoped storage",
        ),
        key="secret",
        key_id="node-a",
    )

    audit = audit_healing_artifact_key_policy(
        artifact,
        HealingArtifactKeyPolicy(
            allowed_key_ids=frozenset({"node-a"}),
            verification_keys={"node-a": "secret"},
        ),
    )

    assert audit["passed"] is True
    assert audit["failures"] == []


def test_healing_artifact_key_policy_fails_closed_for_unknown_or_unsigned_artifacts():
    unsigned = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )
    audit = audit_healing_artifact_key_policy(unsigned, HealingArtifactKeyPolicy(allowed_key_ids=frozenset({"node-a"})))

    assert audit["passed"] is False
    assert "missing_signature" in audit["failures"]
    assert "signature_key_id_not_allowed" in audit["failures"]


def test_healing_artifact_transport_receipt_is_fail_closed():
    unsigned = HealingArtifact(
        task_id="task-1",
        artifact_id="heal-1",
        artifact_type="repair_plan",
        created_at="2026-05-05T00:00:00Z",
        evidence_id="EV-1",
        summary="Use scoped storage",
    )

    receipt = artifact_transport_receipt(unsigned, HealingArtifactKeyPolicy(allowed_key_ids=frozenset({"node-a"})))

    assert receipt["passed"] is False
    assert receipt["production_writes_allowed"] is False
    assert receipt["event_type"] == "healing_artifact_announced"
    assert "missing_signature" in receipt["failure_reasons"]
