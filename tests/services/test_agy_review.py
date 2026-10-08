"""Regression tests for the canonical RDC/Agy packet reviewer wrapper."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from nexus.services.agy_operation_journal import AgyOperationJournal

ROOT = Path(__file__).resolve().parents[2]
REVIEW_PATH = ROOT / "scripts" / "ops" / "nexus-agy-review"
INSTALLER_PATH = ROOT / "scripts" / "ops" / "install_nexus_agy_review.sh"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
review = SourceFileLoader("nexus_agy_review_canonical", str(REVIEW_PATH)).load_module()


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


def make_repo(tmp_path: Path) -> tuple[Path, str, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "review@example.invalid")
    _git(root, "config", "user.name", "Review Test")
    (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-m", "base")
    _git(root, "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git")
    base = _git(root, "rev-parse", "HEAD")
    (root / "a.py").write_text("VALUE = 2\n", encoding="utf-8")
    contract = tmp_path / "contract.md"
    contract.write_text("exact review contract\n", encoding="utf-8")
    return root, base, contract


def args_for(root: Path, base: str, contract: Path, operation_root: Path):
    return argparse.Namespace(
        cwd=str(root),
        repository="James3014/Nexus-new",
        base_revision=base,
        contract_file=str(contract),
        review_role="independent-acceptance",
        verification_receipt_file=[],
        authority_excerpt_file=[],
        model="claude-sonnet-4-6",
        effort=None,
        packet_mode="full",
        compact_max_bytes=1_000_000,
        timeout=60,
        max_calls=1,
        pool_wait_timeout=1.0,
        operation_root=str(operation_root),
    )


class FakeSpawner:
    calls: list[list[str]] = []
    next_pid = 4300

    @classmethod
    def spawn(cls, argv, **kwargs):
        cls.calls.append(list(argv))
        pid = cls.next_pid
        cls.next_pid += 1
        return pid


def test_identical_review_dispatch_is_deduplicated(monkeypatch, tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    first = review.launch_review(args)
    second = review.launch_review(args)

    assert first["action"] == "DISPATCHED"
    assert second["action"] == "OBSERVE_EXISTING"
    assert len(FakeSpawner.calls) == 1
    assert first["operation"]["operation_id"] == second["operation"]["operation_id"]
    argv = FakeSpawner.calls[0]
    assert "--mode" in argv and argv[argv.index("--mode") + 1] == "plan"
    assert "--model" in argv and argv[argv.index("--model") + 1] == "claude-sonnet-4-6"
    assert "--effort" not in argv
    assert first["operation"]["review_launch_profile_id"] == "claude-sonnet-4-6.packet-review.v2"
    assert first["operation"]["review_launch_mode"] == "plan"
    assert ["--deny", "command(*)"] == argv[argv.index("--deny") : argv.index("--deny") + 2]
    assert "--write-path" not in argv


def test_outcome_unknown_never_redispatches(monkeypatch, tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    first = review.launch_review(args)
    opid = first["operation"]["operation_id"]
    journal = AgyOperationJournal(op_root)
    journal.mark_terminal(
        opid,
        status="OUTCOME_UNKNOWN",
        exit_code=None,
        failure_kind="TEST_UNKNOWN",
        cwd=str(root),
        reconciliation={"result": "OUTCOME_UNKNOWN", "retry_permitted": False},
    )

    second = review.launch_review(args)

    assert second["action"] == "RECONCILE_EXISTING"
    assert len(FakeSpawner.calls) == 1


def test_terminal_review_receipt_is_reused_and_later_drift_blocks_applicability(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    launched = review.launch_review(args)
    opid = launched["operation"]["operation_id"]
    journal = AgyOperationJournal(op_root)
    journal.mark_terminal(
        opid,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
        observed_provider="agy",
        observed_model="claude-sonnet-4-6",
        provider_session_id="session-1",
    )
    journal.stdout_path(opid).write_text(
        "No material defects.\nACCEPT\n",
        encoding="utf-8",
    )

    first_status = review.status_review(opid, operation_root=str(op_root))
    assert first_status["receipt"]["verdict"] == "ACCEPT"
    assert first_status["receipt"]["review_applicable"] is True
    assert (
        first_status["receipt"]["review_launch_profile_id"] == "claude-sonnet-4-6.packet-review.v2"
    )
    assert first_status["receipt"]["review_launch_mode"] == "plan"
    assert first_status["operation"]["review_applicable"] is True

    (root / "a.py").write_text("VALUE = 3\n", encoding="utf-8")
    second_status = review.status_review(opid, operation_root=str(op_root))

    assert second_status["receipt"]["verdict"] == "ACCEPT"
    assert second_status["operation"]["subject_stable"] is False
    assert second_status["operation"]["review_applicable"] is False
    assert second_status["operation"]["review_state"] == "STALE_SUBJECT"


def test_malformed_terminal_verdict_never_becomes_accept(monkeypatch, tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    launched = review.launch_review(args)
    opid = launched["operation"]["operation_id"]
    journal = AgyOperationJournal(op_root)
    journal.mark_terminal(opid, status="COMPLETED", exit_code=0, cwd=str(root))
    journal.stdout_path(opid).write_text("Looks good but no terminal token.\n", encoding="utf-8")

    status = review.status_review(opid, operation_root=str(op_root))

    assert status["receipt"] is None
    assert status["operation"]["review_state"] == "INVALID_VERDICT"
    assert status["operation"]["review_applicable"] is False


def test_changed_contract_uses_new_semantic_operation(monkeypatch, tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    first = review.launch_review(args)
    contract.write_text("materially changed review contract\n", encoding="utf-8")
    second = review.launch_review(args)

    assert first["operation"]["operation_id"] != second["operation"]["operation_id"]
    assert len(FakeSpawner.calls) == 2


def test_installer_deploys_exact_canonical_review_entrypoint(tmp_path: Path) -> None:
    target = tmp_path / "nexus-agy-review"
    env = os.environ.copy()
    env.update({
        "NEXUS_AGY_REPO_ROOT": str(ROOT),
        "NEXUS_AGY_SNAPSHOT": str(ROOT),
        "NEXUS_AGY_REVIEW_TARGET": str(target),
    })

    proc = subprocess.run(
        ["bash", str(INSTALLER_PATH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == REVIEW_PATH.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_same_semantic_review_from_different_physical_root_fails_closed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    clone = tmp_path / "clone"
    proc = subprocess.run(
        ["git", "clone", str(root), str(clone)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    _git(clone, "remote", "set-url", "origin", "https://github.com/James3014/Nexus-new.git")
    (clone / "a.py").write_text("VALUE = 2\n", encoding="utf-8")

    op_root = tmp_path / "operations"
    first_args = args_for(root, base, contract, op_root)
    second_args = args_for(clone, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    first = review.launch_review(first_args)
    with pytest.raises(
        review.AgyReviewError,
        match="REVIEW_EXISTING_PACKET_MISMATCH",
    ):
        review.launch_review(second_args)

    assert first["action"] == "DISPATCHED"
    assert len(FakeSpawner.calls) == 1


def test_failed_terminal_review_is_reused_without_redispatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    launched = review.launch_review(args)
    opid = launched["operation"]["operation_id"]
    journal = AgyOperationJournal(op_root)
    journal.mark_terminal(
        opid,
        status="FAILED",
        exit_code=1,
        failure_kind="TEST_FAILURE",
        cwd=str(root),
    )

    repeated = review.launch_review(args)

    assert repeated["action"] == "TERMINAL_NON_ACCEPTING"
    assert repeated["receipt"] is None
    assert len(FakeSpawner.calls) == 1


def test_unknown_reviewer_model_fails_before_operation_creation(tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    args.model = "unknown-reviewer-model"

    with pytest.raises(
        review.AgyReviewerProfileError,
        match="REVIEW_MODEL_PROFILE_UNKNOWN",
    ):
        review.launch_review(args)

    assert not op_root.exists()


def test_unsupported_effort_fails_before_operation_creation(tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    args.effort = "high"

    with pytest.raises(
        review.AgyReviewerProfileError,
        match="REVIEW_EFFORT_UNSUPPORTED",
    ):
        review.launch_review(args)

    assert not op_root.exists()


def test_transport_profile_change_does_not_duplicate_semantic_review(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    first_args = args_for(root, base, contract, op_root)
    second_args = args_for(root, base, contract, op_root)
    second_args.model = "gemini-3.8-flash-low"
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    first = review.launch_review(first_args)
    second = review.launch_review(second_args)

    assert first["operation"]["operation_id"] == second["operation"]["operation_id"]
    assert second["action"] == "OBSERVE_EXISTING"
    assert len(FakeSpawner.calls) == 1
    assert first["operation"]["model"] == "claude-sonnet-4-6"
    assert second["operation"]["model"] == "claude-sonnet-4-6"


def test_full_and_compact_requests_share_one_semantic_operation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    lines = [f"line {index}\n" for index in range(100)]
    (root / "a.py").write_text("".join(lines), encoding="utf-8")
    _git(root, "add", "a.py")
    _git(root, "commit", "-m", "packet-mode-base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "a.py").write_text(
        "".join(lines[:50] + ["changed\n"] + lines[51:]),
        encoding="utf-8",
    )

    op_root = tmp_path / "operations"
    full_args = args_for(root, base, contract, op_root)
    compact_args = args_for(root, base, contract, op_root)
    compact_args.packet_mode = "compact"
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    full = review.launch_review(full_args)
    compact = review.launch_review(compact_args)

    assert full["operation"]["operation_id"] == compact["operation"]["operation_id"]
    assert compact["action"] == "OBSERVE_EXISTING"
    assert len(FakeSpawner.calls) == 1


def test_compact_launch_records_bounded_compaction_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    args.packet_mode = "compact"
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    result = review.launch_review(args)

    assert result["action"] == "DISPATCHED"
    assert result["operation"]["review_packet_mode"] == "compact"
    assert result["operation"]["review_compaction_schema"] == "nexus.agy_review_compaction.v1"
    assert len(result["operation"]["review_compact_payload_sha256"]) == 64


def test_gemini_flash_dispatch_argv_carries_default_effort(monkeypatch, tmp_path: Path) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    args.model = "gemini-3.8-flash"
    args.effort = None
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    result = review.launch_review(args)
    record = AgyOperationJournal(op_root).read(result["operation"]["operation_id"])
    assert record["effort"] == "medium"
    assert record["review_launch_effective_effort"] == "medium"

    assert len(FakeSpawner.calls) == 1
    argv = FakeSpawner.calls[0]
    assert "--effort" in argv
    assert argv[argv.index("--effort") + 1] == "medium"


def test_gemini_flash_terminal_receipt_carries_effective_effort(
    monkeypatch, tmp_path: Path
) -> None:
    root, base, contract = make_repo(tmp_path)
    op_root = tmp_path / "operations"
    args = args_for(root, base, contract, op_root)
    args.model = "gemini-3.8-flash"
    args.effort = None
    FakeSpawner.calls = []
    monkeypatch.setattr(review, "_dispatcher_path", lambda: Path("/fake/nexus-agy-dispatch"))
    monkeypatch.setattr(review, "_spawn_dispatch", FakeSpawner.spawn)

    launched = review.launch_review(args)
    opid = launched["operation"]["operation_id"]
    journal = AgyOperationJournal(op_root)
    journal.mark_terminal(
        opid,
        status="COMPLETED",
        exit_code=0,
        cwd=str(root),
        observed_provider="agy",
        observed_model="gemini-3.8-flash",
        provider_session_id="session-1",
    )
    journal.stdout_path(opid).write_text("No material defects.\nACCEPT\n", encoding="utf-8")

    status = review.status_review(opid, operation_root=str(op_root))
    assert status["receipt"]["verdict"] == "ACCEPT"
    assert status["receipt"]["review_launch_effective_effort"] == "medium"
