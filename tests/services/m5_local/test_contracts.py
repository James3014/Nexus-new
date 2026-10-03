"""Unit tests for M5 Local Bridge contracts and schemas."""

from __future__ import annotations

from nexus.services.m5_local.contracts import (
    M5_LOCAL_ASSIST_REQUEST_SCHEMA,
    M5_LOCAL_ASSIST_RESPONSE_SCHEMA,
    M5_LOCAL_BOUNDED_PACKET_SCHEMA,
    M5_LOCAL_CLAIM_CEILING,
    M5_LOCAL_HANDOFF_SCHEMA,
    M5_LOCAL_WORKER_REQUEST_SCHEMA,
    M5_LOCAL_WORKER_RESPONSE_SCHEMA,
    RECOGNIZED_ESCALATION_REASONS,
    RECOGNIZED_ROLES,
    ROLE_BOUNDED_CODE_PATCH,
    ROLE_READ_ONLY_ASSIST,
    ROLE_REPO_RANKING,
    ROLE_TYPED_DECISION,
    BoundedEvidencePacket,
    CandidatePathEntry,
    HandoffPacket,
    SourceExcerpt,
)


def test_schema_identities_and_claim_ceiling():
    from nexus.services.m5_local.contracts import SERVICE_MODE_LOCAL

    assert M5_LOCAL_ASSIST_REQUEST_SCHEMA == "nexus.m5_local.assist_request.v1"
    assert M5_LOCAL_ASSIST_RESPONSE_SCHEMA == "nexus.m5_local.assist_response.v1"
    assert M5_LOCAL_BOUNDED_PACKET_SCHEMA == "nexus.m5_local.deterministic_fallback_packet.v1"
    assert M5_LOCAL_HANDOFF_SCHEMA == "nexus.m5_local.handoff_input.v1"
    assert M5_LOCAL_WORKER_REQUEST_SCHEMA == "nexus.m5_local.worker_request.v1"
    assert M5_LOCAL_WORKER_RESPONSE_SCHEMA == "nexus.m5_local.worker_response.v1"
    assert M5_LOCAL_CLAIM_CEILING == "LOCAL_NON_AUTHORITATIVE_EVIDENCE_ONLY"
    assert SERVICE_MODE_LOCAL == "LOCAL"
    assert ROLE_READ_ONLY_ASSIST in RECOGNIZED_ROLES
    assert ROLE_BOUNDED_CODE_PATCH in RECOGNIZED_ROLES
    assert ROLE_REPO_RANKING in RECOGNIZED_ROLES
    assert ROLE_TYPED_DECISION in RECOGNIZED_ROLES


def test_bounded_evidence_packet_deterministic_hash():
    p1 = BoundedEvidencePacket(
        task_id="t1",
        query="test query",
        repo_identity="Nexus-new",
        base_sha="abc1234",
        candidate_paths=[CandidatePathEntry(path="a.py", reason="hit", score=0.9)],
        source_excerpts=[
            SourceExcerpt(path="a.py", start_line=1, end_line=5, content="print('hello')")
        ],
    )
    p2 = BoundedEvidencePacket(
        task_id="t1",
        query="test query",
        repo_identity="Nexus-new",
        base_sha="abc1234",
        candidate_paths=[CandidatePathEntry(path="a.py", reason="hit", score=0.9)],
        source_excerpts=[
            SourceExcerpt(path="a.py", start_line=1, end_line=5, content="print('hello')")
        ],
    )
    assert p1.packet_hash() == p2.packet_hash()
    assert len(p1.packet_hash()) == 64


def test_handoff_packet_hash():
    h1 = HandoffPacket(
        task_id="t1",
        predecessor_attempt_id="att-1",
        repo_identity="Nexus-new",
        base_sha="abc1234",
        inspected_paths=["nexus/a.py"],
        evidence_refs=["ref:1"],
        diff="",
        escalation_reason="LOCAL_RESULT_INSUFFICIENT",
    )
    h2 = HandoffPacket(
        task_id="t1",
        predecessor_attempt_id="att-1",
        repo_identity="Nexus-new",
        base_sha="abc1234",
        inspected_paths=["nexus/a.py"],
        evidence_refs=["ref:1"],
        diff="",
        escalation_reason="LOCAL_RESULT_INSUFFICIENT",
    )
    assert h1.handoff_hash() == h2.handoff_hash()
    assert h1.durability == "EPHEMERAL_PROJECTION"
    assert h1.nature == "HANDOFF_INPUT"


def test_escalation_reasons():
    expected = {
        "LOCAL_RUNTIME_UNAVAILABLE",
        "LOCAL_MODEL_IDENTITY_MISMATCH",
        "LOCAL_ROLE_NOT_QUALIFIED",
        "LOCAL_CONTEXT_LIMIT",
        "LOCAL_TIMEOUT",
        "LOCAL_RESOURCE_PRESSURE",
        "LOCAL_RESULT_INSUFFICIENT",
    }
    assert expected.issubset(RECOGNIZED_ESCALATION_REASONS)
