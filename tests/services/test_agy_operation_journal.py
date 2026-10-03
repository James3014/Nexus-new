"""Durable operation-state tests for direct Agy background execution."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
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


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def test_reconcile_dead_wrapper_terminates_exact_surviving_provider_group(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    marker = str(journal.operation_dir(operation_id) / "agy.log")
    wrapper_code = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)',sys.argv[1]]);"
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", wrapper_code, marker],
        start_new_session=True,
    )
    wrapper.wait(timeout=3)
    assert _process_group_alive(wrapper.pid)

    try:
        journal.mark_started(operation_id, pid=wrapper.pid)

        result = journal.reconcile(operation_id)

        assert result["status"] == "OUTCOME_UNKNOWN"
        assert result["reconciliation"]["result"] == "ORPHAN_PROVIDER_TERMINATED"
        assert result["reconciliation"]["provider_alive_before"] is True
        assert result["reconciliation"]["provider_alive_after"] is False
        assert _process_group_alive(wrapper.pid) is False
    finally:
        if _process_group_alive(wrapper.pid):
            os.killpg(wrapper.pid, signal.SIGKILL)


def test_reconcile_dead_wrapper_does_not_kill_unverified_reused_group(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    wrapper_code = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)','unrelated']);"
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", wrapper_code],
        start_new_session=True,
    )
    wrapper.wait(timeout=3)
    assert _process_group_alive(wrapper.pid)

    try:
        journal.mark_started(operation_id, pid=wrapper.pid)

        result = journal.reconcile(operation_id)

        assert result["status"] == "RUNNING"
        assert result["phase"] == "RECONCILE_REQUIRED"
        assert result["reconciliation"]["result"] == "ORPHAN_PROCESS_GROUP_UNVERIFIED"
        assert result["reconciliation"]["retry_permitted"] is False
        assert _process_group_alive(wrapper.pid) is True
    finally:
        if _process_group_alive(wrapper.pid):
            os.killpg(wrapper.pid, signal.SIGKILL)


def test_outcome_unknown_can_reconcile_same_surviving_provider_group(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    marker = str(journal.operation_dir(operation_id) / "agy.log")
    wrapper_code = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)',sys.argv[1]]);"
    )
    wrapper = subprocess.Popen(
        [sys.executable, "-c", wrapper_code, marker],
        start_new_session=True,
    )
    wrapper.wait(timeout=3)
    assert _process_group_alive(wrapper.pid)

    try:
        journal.mark_started(operation_id, pid=wrapper.pid)
        journal.mark_terminal(
            operation_id,
            status="OUTCOME_UNKNOWN",
            exit_code=None,
            failure_kind="PROCESS_NOT_RUNNING_WITHOUT_TERMINAL_RECEIPT",
            cwd=str(tmp_path),
            reconciliation={
                "result": "OUTCOME_UNKNOWN",
                "retry_permitted": False,
            },
        )

        result = journal.reconcile(operation_id)

        assert result["status"] == "OUTCOME_UNKNOWN"
        assert result["reconciliation"]["result"] == "ORPHAN_PROVIDER_TERMINATED"
        assert result["reconciliation"]["provider_alive_after"] is False
        assert _process_group_alive(wrapper.pid) is False
    finally:
        if _process_group_alive(wrapper.pid):
            os.killpg(wrapper.pid, signal.SIGKILL)


def test_review_metadata_flows_through_agy_facade_and_public_view(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = new_operation_id()
    record = journal.create(
        operation_id=operation_id,
        attempt_id=new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="claude-sonnet-4-6",
        effort=None,
        prompt_sha256=hashlib.sha256(b"packet prompt").hexdigest(),
        runtime_revision="b" * 40,
        initial_fields={
            "review_profile_version": "nexus.rdc_agy_packet_review.v1",
            "review_effect_id": "c" * 64,
            "review_role": "independent-acceptance",
            "review_repository": "james3014/nexus-new",
            "review_base_revision": "d" * 40,
            "review_candidate_head": "e" * 40,
            "candidate_digest": "f" * 64,
            "acceptance_contract_sha256": "1" * 64,
            "review_packet_sha256": "2" * 64,
            "review_state": "PREPARED",
            "review_applicable": False,
            "private_review_secret": "must-not-project",
        },
    )

    public = public_operation_view(record)

    assert public["review_effect_id"] == "c" * 64
    assert public["candidate_digest"] == "f" * 64
    assert public["review_packet_sha256"] == "2" * 64
    assert public["review_state"] == "PREPARED"
    assert public["review_applicable"] is False
    assert "private_review_secret" not in public


def test_timeline_fields_project_through_public_view(tmp_path: Path) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)

    now = "2026-10-03T12:00:00+00:00"
    journal.update(
        operation_id,
        provider_started_at=now,
        first_stream_activity_at=now,
        provider_stream_last_activity_at=now,
        first_effect_at=now,
        time_to_first_effect_ms=1234,
        provider_pid=12345,
        provider_process_state="RUNNING",
    )

    record = journal.read(operation_id)
    public = public_operation_view(record)

    assert public["provider_started_at"] == now
    assert public["first_stream_activity_at"] == now
    assert public["provider_stream_last_activity_at"] == now
    assert public["first_effect_at"] == now
    assert public["time_to_first_effect_ms"] == 1234
    assert public["provider_pid"] == 12345
    assert public["provider_process_state"] == "RUNNING"


def test_detect_worktree_physical_effects_isolates_pre_existing_changes(tmp_path: Path) -> None:
    from nexus.services import direct_operation_journal as doj

    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
    (work / "initial.txt").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "initial.txt"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-m", "init"], check=True, capture_output=True)

    # Pre-existing change
    (work / "donor_change.txt").write_text("existing dirty", encoding="utf-8")

    baseline = doj.snapshot_worktree_physical_state(str(work))
    assert "donor_change.txt" in baseline

    # If nothing changes, effects should be empty
    assert doj.detect_worktree_physical_effects(str(work), baseline) == []

    # New file added
    (work / "new_change.txt").write_text("new", encoding="utf-8")
    assert doj.detect_worktree_physical_effects(str(work), baseline) == ["new_change.txt"]


def test_reconcile_checks_real_provider_pid_liveness(tmp_path: Path) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)

    # Dead PID
    journal.update(
        operation_id,
        provider_pid=999_999_999,
        provider_process_state="RUNNING",
    )

    reconciled = journal.reconcile(operation_id)
    assert reconciled["provider_process_state"] == "EXITED"
