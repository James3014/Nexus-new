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

from nexus.services import agy_operation_journal as agy_journal
from nexus.services import direct_operation_journal as direct_journal
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


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout.strip()


def _make_source_repo(tmp_path: Path) -> Path:
    root = tmp_path / "source-repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "attribution@example.invalid")
    _git(root, "config", "user.name", "Attribution Test")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-q", "-m", "base")
    return root


def _create_source_operation(journal: AgyOperationJournal, root: Path) -> str:
    operation_id = new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=new_attempt_id(),
        cwd=str(root),
        provider="agy",
        model="gemini-test",
        effort="low",
        prompt_sha256=hashlib.sha256(b"attribution prompt").hexdigest(),
        runtime_revision="b" * 40,
    )
    return operation_id


def test_dirty_unchanged_is_not_attributed(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    tracked = root / "tracked.txt"
    tracked.write_text("dirty-before\n", encoding="utf-8")
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = _create_source_operation(journal, root)

    record = journal.mark_terminal(
        operation_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )

    assert record["observed_changed_paths"] == []
    assert record["source_attribution_state"] == "ATTRIBUTED"
    assert record["source_baseline_sha256"]
    assert "source_baseline" not in direct_journal.public_operation_view(record)


def test_dirty_changed_again_is_attributed(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    tracked = root / "tracked.txt"
    tracked.write_text("dirty-before\n", encoding="utf-8")
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = _create_source_operation(journal, root)
    tracked.write_text("dirty-after\n", encoding="utf-8")

    record = journal.mark_terminal(
        operation_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )

    assert record["observed_changed_paths"] == ["tracked.txt"]


def test_untracked_unchanged_and_changed_are_distinguished(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    nested = root / "new" / "evidence.txt"
    nested.parent.mkdir()
    nested.write_text("before\n", encoding="utf-8")
    journal = AgyOperationJournal(tmp_path / "journal")

    unchanged_id = _create_source_operation(journal, root)
    unchanged = journal.mark_terminal(
        unchanged_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )
    assert unchanged["observed_changed_paths"] == []

    changed_id = _create_source_operation(journal, root)
    nested.write_text("after\n", encoding="utf-8")
    changed = journal.mark_terminal(
        changed_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )
    assert changed["observed_changed_paths"] == ["new/evidence.txt"]


def test_clean_to_changed_and_deleted_paths_are_attributed(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    journal = AgyOperationJournal(tmp_path / "journal")
    changed_id = _create_source_operation(journal, root)
    (root / "tracked.txt").write_text("after\n", encoding="utf-8")
    changed = journal.mark_terminal(
        changed_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )
    assert changed["observed_changed_paths"] == ["tracked.txt"]

    _git(root, "checkout", "--", "tracked.txt")
    deleted_id = _create_source_operation(journal, root)
    (root / "tracked.txt").unlink()
    deleted = journal.mark_terminal(
        deleted_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )
    assert deleted["observed_changed_paths"] == ["tracked.txt"]


def test_missing_source_baseline_fails_closed_for_attribution(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = _create_source_operation(journal, root)
    journal.update(
        operation_id,
        source_baseline=None,
        source_baseline_sha256=None,
        source_attribution_state="UNAVAILABLE",
    )
    (root / "tracked.txt").write_text("changed\n", encoding="utf-8")

    record = journal.mark_terminal(
        operation_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )

    assert record["observed_changed_paths"] == []
    assert record["source_attribution_state"] == "UNAVAILABLE"


def test_malformed_source_baseline_fails_closed(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = _create_source_operation(journal, root)
    malformed = {
        "schema": direct_journal.SOURCE_BASELINE_SCHEMA,
        "entries": {"tracked.txt": {"status": " M", "kind": "file", "sha256": "bad"}},
    }
    journal.update(
        operation_id,
        source_baseline=malformed,
        source_baseline_sha256="0" * 64,
        source_attribution_state="BASELINE_CAPTURED",
    )
    (root / "tracked.txt").write_text("changed\n", encoding="utf-8")

    record = journal.mark_terminal(
        operation_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
    )

    assert record["observed_changed_paths"] == []
    assert record["source_attribution_state"] == "UNAVAILABLE"


def test_source_baseline_is_secret_free_and_not_public(tmp_path: Path) -> None:
    root = _make_source_repo(tmp_path)
    (root / "tracked.txt").write_text("private-dirty-content\n", encoding="utf-8")
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id = _create_source_operation(journal, root)

    record = journal.read(operation_id)
    raw = journal.record_path(operation_id).read_text(encoding="utf-8")
    public = direct_journal.public_operation_view(record)

    assert "private-dirty-content" not in raw
    assert record["source_baseline_sha256"]
    assert record["source_attribution_state"] == "BASELINE_CAPTURED"
    assert "source_baseline" not in public
    assert public["source_baseline_sha256"] == record["source_baseline_sha256"]


def test_reconcile_dead_wrapper_with_live_provider_pid_terminates_exact_child(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)
    marker = str(journal.operation_dir(operation_id) / "agy.log")

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", marker],
    )
    try:
        journal.mark_started(operation_id, pid=999_999_998)
        journal.update(operation_id, provider_pid=child.pid)

        result = journal.reconcile(operation_id)

        assert result["status"] == "OUTCOME_UNKNOWN"
        assert result["reconciliation"]["result"] == "ORPHAN_PROVIDER_TERMINATED"
        assert result["reconciliation"]["provider_alive_before"] is True
        assert result["reconciliation"]["provider_alive_after"] is False
        assert not _process_group_alive(child.pid)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_reconcile_dead_wrapper_with_reused_provider_pid_does_not_kill_unverified_process(
    tmp_path: Path,
) -> None:
    journal = AgyOperationJournal(tmp_path / "journal")
    operation_id, _ = _create(journal, tmp_path)

    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "unrelated_payload"],
    )
    try:
        journal.mark_started(operation_id, pid=999_999_998)
        journal.update(operation_id, provider_pid=unrelated.pid)

        result = journal.reconcile(operation_id)

        assert result["status"] == "RUNNING"
        assert result["phase"] == "RECONCILE_REQUIRED"
        assert result["reconciliation"]["result"] == "ORPHAN_PROCESS_GROUP_UNVERIFIED"
        assert result["reconciliation"]["retry_permitted"] is False
        assert unrelated.poll() is None, "Unrelated process must not be killed"
    finally:
        unrelated.kill()
        unrelated.wait()


def test_stop_operation_processes_kills_verified_group_before_leader_marker_disappears(
    tmp_path: Path,
    monkeypatch,
) -> None:
    op_dir = tmp_path / "agyop_test"
    op_dir.mkdir()
    marker = str(op_dir / "agy.log")
    alive = {111: True, 222: True}
    calls: list[str] = []

    monkeypatch.setattr(
        agy_journal,
        "_process_group_process_rows",
        lambda pgid: (
            [
                (111, "S", f"agy --log-file {marker}"),
                (222, "S", "tool-child"),
            ]
            if pgid == 111 and (alive[111] or alive[222])
            else []
        ),
    )
    monkeypatch.setattr(
        agy_journal,
        "_process_alive",
        lambda pid: bool(alive.get(pid, False)),
    )
    monkeypatch.setattr(
        agy_journal,
        "_pid_has_operation_marker",
        lambda pid, *_args, **_kwargs: pid == 111 and alive[111],
    )
    monkeypatch.setattr(
        agy_journal,
        "_group_has_operation_marker",
        lambda pgid, *_args, **_kwargs: pgid == 111 and alive[111],
    )
    monkeypatch.setattr(
        agy_journal,
        "_process_group_alive",
        lambda pgid: pgid == 111 and (alive[111] or alive[222]),
    )

    def stop_group(pgid: int, **_kwargs) -> bool:
        assert pgid == 111
        assert alive[111] is True
        calls.append("group")
        alive[111] = False
        alive[222] = False
        return True

    def stop_pid(pid: int, **_kwargs) -> bool:
        calls.append(f"pid:{pid}")
        alive[pid] = False
        return True

    monkeypatch.setattr(agy_journal, "_stop_process_group", stop_group)
    monkeypatch.setattr(agy_journal, "_stop_process", stop_pid)

    result = agy_journal._stop_operation_processes(
        "agyop_test",
        op_dir,
        provider_pid=111,
        provider_pgid=111,
        grace_seconds=0.1,
    )

    assert result == (True, False, False)
    assert calls == ["group"]
