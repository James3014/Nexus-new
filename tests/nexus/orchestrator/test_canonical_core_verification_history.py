"""#2776: a second Core verification of one session must not erase the first.

``verify_candidate`` used to ``INSERT OR REPLACE`` into a table keyed by
``session_id``, so a FAILED verdict followed by a VERIFIED one left no trace of
the failure. A crash resume of the same attempt (``RESUME_CANDIDATE_VERIFICATION``)
re-verifies the persisted session legitimately, so the fix keeps every verdict.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

import nexus.orchestrator.canonical_core_transport as transport

SESSION_ID = "cms_" + "7" * 32


def _sh(value) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@pytest.fixture
def core(monkeypatch):
    """Patch the pinned Core so each call returns the next scripted status."""
    monkeypatch.setattr(transport, "CORE_AVAILABLE", True, raising=False)
    for name in (
        "acceptance_contract_hash",
        "change_set_hash",
        "verification_plan_hash",
        "evidence_bundle_hash",
        "change_manifest_hash",
    ):
        monkeypatch.setattr(transport, name, _sh, raising=False)
    monkeypatch.setattr(
        transport,
        "read_observed_core_identity",
        lambda: {"available": False, "reason": "CORE_IDENTITY_UNREADABLE"},
        raising=False,
    )
    statuses: list[tuple[str, list[str]]] = []

    def fake_verify(request):
        status, reasons = statuses.pop(0)
        return (
            200,
            {
                "protocol_version": request["protocol_version"],
                "schema": transport.GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
                "verification": {"status": status, "reason_codes": reasons},
                "hashes": {},
                "certification": None,
            },
        )

    monkeypatch.setattr(transport, "verify_generic_changeset", fake_verify, raising=False)
    return statuses


def _verify(port, tmp_path: Path, state_hash: str):
    return port.verify_candidate(
        preparation={
            "session_id": SESSION_ID,
            "binding_hash": "sha256:" + "0" * 64,
            "source_revision": "git-commit:" + "a" * 40,
        },
        request={
            "contract_id": "contract-2776",
            "allowed_files": ["nexus/orchestrator/task_contract.py"],
            "verifier_commands": ["python3 -m pytest -q"],
            "deletion_policy": "FORBID",
        },
        candidate={"candidate_state_hash": state_hash},
        change_manifest={
            "source_tree": "git-tree:" + "a" * 40,
            "target_tree": "git-tree:" + "b" * 40,
            "entries": [
                {
                    "path": "nexus/orchestrator/task_contract.py",
                    "change_type": "MODIFY",
                    "before_oid": "a" * 40,
                    "after_oid": "b" * 40,
                    "before_mode": "100644",
                    "after_mode": "100644",
                }
            ],
        },
    )


def _seed_session(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO core_mutation_sessions (id, binding_id, binding_hash, operation_id,"
            " attempt_id, acceptance_contract_hash, source_revision, source_tree, status)"
            " VALUES (?, 'b', 'h', 'op', 'attempt-1', 'c', 'git-commit:x', 'git-tree:y', 'ACTIVE')",
            (SESSION_ID,),
        )


def test_failed_then_verified_on_one_session_keeps_the_failed_record(tmp_path, core):
    db_path = tmp_path / "core.sqlite"
    port = transport.CanonicalNexusCoreTransportPort(db_path=db_path)
    port._ensure_db()
    _seed_session(db_path)

    core.append(("FAILED_VERIFICATION", ["MISSING_REQUIRED_EVIDENCE"]))
    _verify(port, tmp_path, "sha256:" + "1" * 64)
    assert port.readback_session(SESSION_ID)["session_row"]["status"] == "FAILED"

    core.append(("VERIFIED", []))
    _verify(port, tmp_path, "sha256:" + "2" * 64)

    readback = port.readback_session(SESSION_ID)
    assert readback["session_row"]["status"] == "COMPLETED"
    assert readback["verification_row"]["core_status"] == "VERIFIED"
    assert readback["verification_count"] == 2
    assert readback["prior_core_statuses"] == ["FAILED_VERIFICATION"]
    first, second = readback["verification_history"]
    assert first["core_status"] == "FAILED_VERIFICATION"
    assert json.loads(first["core_reason_codes_json"]) == ["MISSING_REQUIRED_EVIDENCE"]
    assert first["candidate_state_hash"] == "sha256:" + "1" * 64
    assert second["candidate_state_hash"] == "sha256:" + "2" * 64
    assert first["id"] < second["id"]

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT core_status FROM core_mutation_verifications WHERE session_id = ? ORDER BY id",
            (SESSION_ID,),
        ).fetchall()
    assert rows == [("FAILED_VERIFICATION",), ("VERIFIED",)]


def test_unverified_session_reads_back_empty_history(tmp_path):
    port = transport.CanonicalNexusCoreTransportPort(db_path=tmp_path / "core.sqlite")
    readback = port.readback_session(SESSION_ID)
    assert readback["verification_row"] is None
    assert readback["verification_count"] == 0
    assert readback["verification_history"] == []
    assert readback["prior_core_statuses"] == []


def test_recorded_verifications_cannot_be_updated_or_deleted(tmp_path, core):
    db_path = tmp_path / "core.sqlite"
    port = transport.CanonicalNexusCoreTransportPort(db_path=db_path)
    core.append(("FAILED_VERIFICATION", ["X"]))
    _verify(port, tmp_path, "sha256:" + "1" * 64)
    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"):
            conn.execute("UPDATE core_mutation_verifications SET core_status = 'VERIFIED'")
        with pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"):
            conn.execute("DELETE FROM core_mutation_verifications")
    assert port.readback_session(SESSION_ID)["verification_row"]["core_status"] == (
        "FAILED_VERIFICATION"
    )


def test_pre_2776_database_is_migrated_without_losing_its_row(tmp_path, core):
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE core_mutation_verifications (
                session_id TEXT PRIMARY KEY,
                binding_hash TEXT NOT NULL,
                candidate_state_hash TEXT NOT NULL,
                core_status TEXT NOT NULL,
                change_set_hash TEXT NOT NULL,
                verification_plan_hash TEXT NOT NULL,
                evidence_bundle_hash TEXT NOT NULL,
                change_manifest_hash TEXT NOT NULL,
                projection_hash TEXT NOT NULL,
                core_reason_codes_json TEXT NOT NULL,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO core_mutation_verifications VALUES"
            " (?, 'bh', 'csh', 'FAILED_VERIFICATION', 'c', 'p', 'e', 'm', 'proj', '[\"OLD\"]',"
            " '2026-10-01 00:00:00')",
            (SESSION_ID,),
        )

    port = transport.CanonicalNexusCoreTransportPort(db_path=db_path)
    core.append(("VERIFIED", []))
    _verify(port, tmp_path, "sha256:" + "2" * 64)

    readback = port.readback_session(SESSION_ID)
    assert readback["prior_core_statuses"] == ["FAILED_VERIFICATION"]
    legacy = readback["verification_history"][0]
    assert legacy["candidate_state_hash"] == "csh"
    assert legacy["verified_at"] == "2026-10-01 00:00:00"
    assert readback["verification_row"]["core_status"] == "VERIFIED"
    with sqlite3.connect(db_path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "core_mutation_verifications_pre2776" not in names

    # Opening the migrated database again is a no-op.
    again = transport.CanonicalNexusCoreTransportPort(db_path=db_path)
    assert again.readback_session(SESSION_ID)["verification_count"] == 2


def test_verification_write_uses_no_conflict_resolution_clause():
    source = Path(transport.__file__).read_text(encoding="utf-8")
    assert "INSERT INTO core_mutation_verifications" in source
    assert not re.search(r"INSERT\s+OR\s+\w+\s+INTO\s+core_mutation_verifications", source)
