"""#2991: reconcile never follows journal data or symlinks out of its roots.

The operation journal record is data anyone with write access to the
operation root can edit.  ``--reconcile`` (and ``--finalize-no-effect`` /
``--ack-unclean-sweep``, which reconcile) must therefore:

* accept ``account_alias_hash`` only in the pool's own format (12 lowercase
  hex) before building a lease path from it, and otherwise touch nothing;
* refuse an operation directory, ``operations`` directory, record or lock
  file that is a symlink, instead of locking or writing through it;
* refuse a lease lock or receipt that is a symlink.

Every case runs in ``tmp_path`` with the dispatcher's lease directory
monkeypatched; nothing reads or writes the real pool.
"""

from __future__ import annotations

import json
import os
import shutil
from importlib import import_module
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_reconcile_confinement_2991", str(DISPATCH_PATH)
).load_module()

VALID_ALIAS = "0123456789ab"
LEASE_HASH = "b" * 12
OWNER_PID = 4242


def _snapshot(root: Path) -> dict[str, object]:
    """Every path under ``root`` (symlinks not followed) with its bytes."""
    seen: dict[str, object] = {}
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_symlink():
            seen[rel] = ("link", os.readlink(path))
        elif path.is_file():
            seen[rel] = path.read_bytes()
        else:
            seen[rel] = "dir"
    return seen


def _write_receipt(path: Path, alias_hash: str) -> None:
    path.write_text(
        json.dumps({
            "account_alias_hash": alias_hash,
            "lease_id_hash": LEASE_HASH,
            "pid": OWNER_PID,
        })
        + "\n",
        encoding="utf-8",
    )


def _completed_operation(journal, cwd: Path, *, alias_hash: str) -> str:
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(cwd),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="a" * 64,
        runtime_revision="b" * 40,
    )
    journal.update(
        operation_id,
        status="COMPLETED",
        phase="TERMINAL",
        exit_code=0,
        provider_process_state="EXITED",
        has_unresolved_external_effect=False,
        account_alias_hash=alias_hash,
        lease_id_hash=LEASE_HASH,
        pid=OWNER_PID,
    )
    return operation_id


@pytest.fixture
def pool(tmp_path: Path, monkeypatch) -> Path:
    """A fake pool dir: leases/ plus a victim receipt one level above it."""
    pool_dir = tmp_path / "pool"
    leases = pool_dir / "leases"
    leases.mkdir(parents=True)
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    _write_receipt(pool_dir / "victim.receipt.json", "../victim")
    return pool_dir


# --- account_alias_hash format -------------------------------------------------


@pytest.mark.parametrize(
    "alias_hash",
    [
        "../victim",
        "../../pool/victim",
        "/abs/victim",
        "0123456789AB",
        "0123456789a",
        "0123456789abc",
        "0123456789a\n",
        VALID_ALIAS + "\n",
        "0123456789a/",
        "acct-finalize",
    ],
)
def test_cleanup_refuses_alias_hash_outside_pool_format(pool: Path, alias_hash: str) -> None:
    before = _snapshot(pool)
    record = {
        "account_alias_hash": alias_hash,
        "lease_id_hash": LEASE_HASH,
        "pid": OWNER_PID,
        "reconciliation": {"provider_alive_after": False},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result == {
        "result": "LEASE_ALIAS_HASH_INVALID_PRESERVED",
        "reason": "account_alias_hash is not 12 lowercase hex",
    }
    assert _snapshot(pool) == before  # no receipt removed, no lock created


def test_reconcile_with_escaping_alias_hash_leaves_outside_receipt(
    tmp_path: Path, pool: Path
) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = _completed_operation(journal, tmp_path, alias_hash="../victim")
    before = _snapshot(pool)

    reconciled = dispatch._reconcile_operation(journal, operation_id)

    cleanup = reconciled["reconciliation"]["lease_cleanup"]
    assert cleanup["result"] == "LEASE_ALIAS_HASH_INVALID_PRESERVED"
    assert _snapshot(pool) == before
    assert journal.read(operation_id)["reconciliation"]["lease_cleanup"] == cleanup


def test_reconcile_cli_with_escaping_alias_hash_leaves_outside_receipt(
    tmp_path: Path, pool: Path, capsys
) -> None:
    operation_root = tmp_path / "operations"
    journal = dispatch.AgyOperationJournal(operation_root)
    operation_id = _completed_operation(journal, tmp_path, alias_hash="../victim")
    before = _snapshot(pool)

    assert (
        dispatch.main(["--reconcile", operation_id, "--operation-root", str(operation_root)]) == 0
    )

    capsys.readouterr()
    assert _snapshot(pool) == before
    cleanup = journal.read(operation_id)["reconciliation"]["lease_cleanup"]
    assert cleanup["result"] == "LEASE_ALIAS_HASH_INVALID_PRESERVED"


def test_valid_alias_hash_still_removes_its_exact_receipt(tmp_path: Path, pool: Path) -> None:
    receipt = pool / "leases" / f"{VALID_ALIAS}.receipt.json"
    _write_receipt(receipt, VALID_ALIAS)
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = _completed_operation(journal, tmp_path, alias_hash=VALID_ALIAS)

    reconciled = dispatch._reconcile_operation(journal, operation_id)

    assert reconciled["reconciliation"]["lease_cleanup"] == {"result": "LEASE_RECEIPT_REMOVED"}
    assert not receipt.exists()
    assert (pool / "victim.receipt.json").exists()


def test_finalize_no_effect_with_escaping_alias_hash_fails_closed(
    tmp_path: Path, pool: Path
) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="a" * 64,
        runtime_revision="b" * 40,
    )
    journal.mark_started(operation_id, pid=999_999_998)
    journal.update(operation_id, account_alias_hash="../victim", lease_id_hash=LEASE_HASH)
    journal.mark_terminal(
        operation_id,
        status="OUTCOME_UNKNOWN",
        exit_code=None,
        failure_kind="TIMEOUT",
        cwd=str(tmp_path),
        reconciliation={
            "result": "PROVIDER_TURN_MAY_STILL_BE_RUNNING",
            "provider_alive_after": False,
            "retry_permitted": False,
        },
    )
    # The receipt owner pid must match the record for the old code to delete.
    _write_receipt(pool / "victim.receipt.json", "../victim")
    victim = json.loads((pool / "victim.receipt.json").read_text(encoding="utf-8"))
    victim["pid"] = 999_999_998
    (pool / "victim.receipt.json").write_text(json.dumps(victim) + "\n", encoding="utf-8")
    before = _snapshot(pool)

    with pytest.raises(
        dispatch.AgyOperationJournalError,
        match="NO_EFFECT_LEASE_NOT_SAFE:LEASE_ALIAS_HASH_INVALID_PRESERVED",
    ):
        dispatch._finalize_no_effect_operation(journal, operation_id)

    assert _snapshot(pool) == before
    assert journal.read(operation_id)["status"] == "OUTCOME_UNKNOWN"


# --- lease lock / receipt symlinks ---------------------------------------------


def test_cleanup_refuses_symlinked_lease_lock(tmp_path: Path, pool: Path) -> None:
    leases = pool / "leases"
    _write_receipt(leases / f"{VALID_ALIAS}.receipt.json", VALID_ALIAS)
    outside_lock = tmp_path / "outside" / "planted.lock"
    outside_lock.parent.mkdir()
    (leases / f"{VALID_ALIAS}.lock").symlink_to(outside_lock)
    record = {
        "account_alias_hash": VALID_ALIAS,
        "lease_id_hash": LEASE_HASH,
        "pid": OWNER_PID,
        "reconciliation": {"provider_alive_after": False},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result["result"] == "LEASE_PATH_SYMLINK_PRESERVED"
    assert not outside_lock.exists()
    assert (leases / f"{VALID_ALIAS}.receipt.json").exists()


def test_cleanup_refuses_symlinked_lease_receipt(tmp_path: Path, pool: Path) -> None:
    leases = pool / "leases"
    outside_receipt = tmp_path / "outside.receipt.json"
    _write_receipt(outside_receipt, VALID_ALIAS)
    (leases / f"{VALID_ALIAS}.receipt.json").symlink_to(outside_receipt)
    record = {
        "account_alias_hash": VALID_ALIAS,
        "lease_id_hash": LEASE_HASH,
        "pid": OWNER_PID,
        "reconciliation": {"provider_alive_after": False},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result["result"] == "LEASE_PATH_SYMLINK_PRESERVED"
    assert (leases / f"{VALID_ALIAS}.receipt.json").is_symlink()
    assert outside_receipt.exists()


# --- symlinked operation paths ---------------------------------------------------


def _symlinked_operation(tmp_path: Path) -> tuple[Path, str, Path]:
    """A real operation under outside/, linked into root/operations/<id>."""
    outside_journal = dispatch.AgyOperationJournal(tmp_path / "outside")
    operation_id = _completed_operation(outside_journal, tmp_path, alias_hash=VALID_ALIAS)
    root = tmp_path / "root"
    (root / "operations").mkdir(parents=True)
    (root / "operations" / operation_id).symlink_to(
        outside_journal.operation_dir(operation_id), target_is_directory=True
    )
    return root, operation_id, tmp_path / "outside"


def test_reconcile_refuses_symlinked_operation_dir(tmp_path: Path, pool: Path) -> None:
    root, operation_id, outside = _symlinked_operation(tmp_path)
    before = _snapshot(outside)
    journal = dispatch.AgyOperationJournal(root)

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_SYMLINK"):
        dispatch._reconcile_operation(journal, operation_id)

    assert _snapshot(outside) == before  # no .lock created, record not rewritten


@pytest.mark.parametrize(
    "flag", ["--reconcile", "--finalize-no-effect", "--ack-unclean-sweep", "--status"]
)
def test_cli_maintenance_refuses_symlinked_operation_dir(
    tmp_path: Path, pool: Path, capsys, flag: str
) -> None:
    root, operation_id, outside = _symlinked_operation(tmp_path)
    before = _snapshot(outside)

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_SYMLINK"):
        dispatch.main([flag, operation_id, "--operation-root", str(root)])

    assert capsys.readouterr().out == ""
    assert _snapshot(outside) == before


def test_reconcile_refuses_symlinked_operations_dir(tmp_path: Path, pool: Path) -> None:
    outside_journal = dispatch.AgyOperationJournal(tmp_path / "outside")
    operation_id = _completed_operation(outside_journal, tmp_path, alias_hash=VALID_ALIAS)
    root = tmp_path / "root"
    root.mkdir()
    (root / "operations").symlink_to(tmp_path / "outside" / "operations", target_is_directory=True)
    before = _snapshot(tmp_path / "outside")
    journal = dispatch.AgyOperationJournal(root)

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_SYMLINK"):
        dispatch._reconcile_operation(journal, operation_id)

    assert _snapshot(tmp_path / "outside") == before


def test_update_refuses_symlinked_lock_file(tmp_path: Path) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "root")
    operation_id = _completed_operation(journal, tmp_path, alias_hash=VALID_ALIAS)
    lock = journal.operation_dir(operation_id) / ".lock"
    lock.unlink()
    planted = tmp_path / "planted.lock"
    lock.symlink_to(planted)
    record_before = journal.record_path(operation_id).read_bytes()

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_SYMLINK"):
        journal.update(operation_id, phase="RECONCILE_REQUIRED")

    assert not planted.exists()
    assert journal.record_path(operation_id).read_bytes() == record_before


def test_read_refuses_symlinked_record(tmp_path: Path) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "root")
    operation_id = _completed_operation(journal, tmp_path, alias_hash=VALID_ALIAS)
    record_path = journal.record_path(operation_id)
    outside = tmp_path / "outside-record.json"
    outside.write_bytes(record_path.read_bytes())
    record_path.unlink()
    record_path.symlink_to(outside)

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_SYMLINK"):
        journal.read(operation_id)


def test_operation_dir_that_is_a_file_is_refused(tmp_path: Path) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "root")
    operation_id = dispatch.new_operation_id()
    (tmp_path / "root" / "operations").mkdir(parents=True)
    (tmp_path / "root" / "operations" / operation_id).write_text("x", encoding="utf-8")

    with pytest.raises(dispatch.AgyOperationJournalError, match="OPERATION_PATH_NOT_DIRECTORY"):
        journal.read(operation_id)


def _open_fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def test_directory_planted_as_record_raises_without_leaking_an_fd(tmp_path: Path) -> None:
    journal = dispatch.AgyOperationJournal(tmp_path / "root")
    operation_id = _completed_operation(journal, tmp_path, alias_hash=VALID_ALIAS)
    record_path = journal.record_path(operation_id)
    record_path.unlink()
    record_path.mkdir()
    before = _open_fd_count()

    for _ in range(5):
        with pytest.raises(IsADirectoryError):
            journal.read(operation_id)

    assert _open_fd_count() == before


def test_directory_planted_as_lease_receipt_is_preserved_without_leaking_an_fd(
    pool: Path,
) -> None:
    receipt = pool / "leases" / f"{VALID_ALIAS}.receipt.json"
    receipt.mkdir()
    record = {
        "account_alias_hash": VALID_ALIAS,
        "lease_id_hash": LEASE_HASH,
        "pid": OWNER_PID,
        "reconciliation": {"provider_alive_after": False},
    }
    before = _open_fd_count()

    for _ in range(5):
        result = dispatch._cleanup_reconciled_lease(record)
        assert result == {"result": "LEASE_RECEIPT_UNREADABLE_PRESERVED"}

    assert _open_fd_count() == before
    assert receipt.is_dir()


@pytest.mark.parametrize("swap", ["operation_dir", "operations_dir"])
def test_update_writes_into_the_directory_it_opened_when_swapped_mid_update(
    tmp_path: Path, monkeypatch, swap: str
) -> None:
    """A directory swapped for a symlink after the checks cannot redirect the write."""
    doj = import_module("nexus.services.direct_operation_journal")
    journal = dispatch.AgyOperationJournal(tmp_path / "root")
    operation_id = _completed_operation(journal, tmp_path, alias_hash=VALID_ALIAS)
    op_dir = journal.operation_dir(operation_id)
    swapped = op_dir if swap == "operation_dir" else op_dir.parent
    decoy = tmp_path / "decoy"
    shutil.copytree(swapped, decoy, symlinks=True)
    decoy_before = _snapshot(decoy)
    moved = tmp_path / "moved"
    original_validate = doj._validate_continuity_fields
    calls = []

    def swap_then_validate(record):
        if not calls:
            os.rename(swapped, moved)
            swapped.symlink_to(decoy, target_is_directory=True)
        calls.append(1)
        return original_validate(record)

    monkeypatch.setattr(doj, "_validate_continuity_fields", swap_then_validate)

    journal.update(operation_id, phase="RECONCILE_REQUIRED")

    assert calls
    assert _snapshot(decoy) == decoy_before
    moved_record = moved / operation_id if swap == "operations_dir" else moved
    record = json.loads((moved_record / "operation.json").read_text(encoding="utf-8"))
    assert record["phase"] == "RECONCILE_REQUIRED"
