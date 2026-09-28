"""Durable operation-state tests for direct Agy background execution."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from nexus.services.agy_operation_journal import (
    AgyOperationJournal,
    new_attempt_id,
    new_operation_id,
    public_operation_view,
)


def _create(journal: AgyOperationJournal, tmp_path: Path) -> tuple[str, dict]:
    operation_id = new_operation_id()
    record = journal.create(
        operation_id=operation_id,
        attempt_id=new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256=hashlib.sha256(b"secret prompt").hexdigest(),
        runtime_revision="a" * 40,
    )
    return operation_id, record


def test_journal_persists_secret_free_operation_record(tmp_path: Path) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, record = _create(journal, tmp_path)

    raw = journal.record_path(operation_id).read_text(encoding="utf-8")
    assert "secret prompt" not in raw
    assert record["status"] == "QUEUED"
    assert record["operation_id"] == operation_id
    assert public_operation_view(record).get("prompt_sha256") is None

    mode = stat.S_IMODE(journal.record_path(operation_id).stat().st_mode)
    assert mode == 0o600


def test_heartbeat_and_terminal_receipt_survive_new_reader(tmp_path: Path) -> None:
    root = tmp_path / "journal"
    journal = AgyOperationJournal(root)
    operation_id, _ = _create(journal, tmp_path)

    journal.mark_started(operation_id, pid=os.getpid())
    journal.heartbeat(
        operation_id,
        phase="EXECUTING",
        attempts=1,
        rotations=0,
        account_alias_hash="acct-hash",
        lease_id_hash="lease-hash",
    )
    journal.mark_terminal(
        operation_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(tmp_path),
        attempts=1,
        rotations=0,
    )

    reread = AgyOperationJournal(root).read(operation_id)
    assert reread["status"] == "COMPLETED"
    assert reread["phase"] == "TERMINAL"
    assert reread["last_heartbeat_at"]
    assert reread["finished_at"]
    assert reread["exit_code"] == 0


def test_reconcile_dead_nonterminal_process_becomes_outcome_unknown(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    journal.mark_started(operation_id, pid=999_999_999)

    result = journal.reconcile(operation_id)

    assert result["status"] == "OUTCOME_UNKNOWN"
    assert result["failure_kind"] == "PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT"
    assert result["reconciliation"]["retry_permitted"] is False
    assert result["reconciliation"]["pid_alive"] is False


def test_reconcile_live_process_never_grants_retry(tmp_path: Path) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    journal.mark_started(operation_id, pid=os.getpid())

    result = journal.reconcile(operation_id, heartbeat_stale_seconds=120)

    assert result["status"] == "RUNNING"
    assert result["reconciliation"]["result"] == "ACTIVE"
    assert result["reconciliation"]["retry_permitted"] is False


def test_record_is_valid_json_after_repeated_updates(tmp_path: Path) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)

    for index in range(20):
        journal.heartbeat(operation_id, phase=f"PHASE_{index}", attempts=index)

    payload = json.loads(journal.record_path(operation_id).read_text(encoding="utf-8"))
    assert payload["phase"] == "PHASE_19"
    assert payload["attempts"] == 19
