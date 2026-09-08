import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.events.state_owner_manifest import (
    ABSENT,
    COMMITTED,
    COMMITTED_STATUS,
    NEVER_ROLLBACK,
    PREPARED,
    PREPARED_UNKNOWN,
    RECOVERY_ONLY,
    TAMPERED_OR_UNKNOWN,
    ManifestMalformed,
    ManifestTampered,
    NonRollbackableRole,
    OwnerConflict,
    RecoveryDenied,
    StateOwnerBinding,
    classify,
    commit_manifest,
    manifest_path,
    prepare_manifest,
    read_manifest,
    restore_previous_committed,
    StateOwnerSelection,
    owner_transaction_guard,
    commit_owner_transaction,
    assert_owner_write,
)
from nexus.events.writer_generation import (
    EventWriterGeneration,
    GenerationError,
    event_store_lock,
    install_generation,
    read_generation,
)


def binding(root: Path, tx: str = "tx-1", generation: int = 1) -> StateOwnerBinding:
    installed = read_generation(root)
    if installed is None:
        install_generation(root, EventWriterGeneration(generation, "w"))
    elif installed.generation < generation:
        install_generation(root, EventWriterGeneration(generation, "w"), expected_generation=installed.generation)
    return StateOwnerBinding("owner-a", root.resolve(), generation, tx)


def files(root: Path) -> dict[str, str]:
    (root / "state.json").write_text('{"status":"PENDING"}\n', encoding="utf-8")
    events = root / ".nexus/events"
    events.mkdir(parents=True, exist_ok=True)
    (events / "event_log.jsonl").write_text('{"event":"committed"}\n', encoding="utf-8")
    return {"task_state": "state.json", "event_log": ".nexus/events/event_log.jsonl"}


def test_prepare_commit_roundtrip_and_digest_chain(tmp_path):
    first = prepare_manifest(binding(tmp_path), writer_id="w", files=files(tmp_path))
    assert first.state == PREPARED
    assert classify(binding(tmp_path)).status == PREPARED_UNKNOWN
    committed = commit_manifest(binding(tmp_path), first)
    assert committed.state == COMMITTED
    assert read_manifest(tmp_path).manifest_sha256 == committed.manifest_sha256
    assert classify(binding(tmp_path)).status == COMMITTED_STATUS

    (tmp_path / "state.json").write_text('{"status":"NEXT"}\n', encoding="utf-8")
    second = prepare_manifest(
        binding(tmp_path, tx="tx-2", generation=2),
        writer_id="w",
        files=files(tmp_path),
        previous_manifest_sha256=committed.manifest_sha256,
    )
    assert second.previous_manifest_sha256 == committed.manifest_sha256
    assert (tmp_path / ".nexus/events/state_owner_manifests/tx-1.json").exists()


def test_commit_rehash_mismatch_fails_closed(tmp_path):
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files=files(tmp_path))
    (tmp_path / "state.json").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ManifestTampered):
        commit_manifest(binding(tmp_path), prepared)
    assert read_manifest(tmp_path).state == PREPARED


def test_commit_selected_file_fsync_failure_stays_prepared(tmp_path, monkeypatch):
    (tmp_path / "state.json").write_text("before\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    import nexus.events.state_owner_manifest as module

    def fail_fsync(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(module.os, "fsync", fail_fsync)
    with pytest.raises(ManifestTampered, match="durability fsync"):
        commit_manifest(binding(tmp_path), prepared)
    assert read_manifest(tmp_path).state == PREPARED


def test_atomic_history_parent_symlink_is_rejected(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    events = tmp_path / ".nexus/events"
    events.mkdir(parents=True, exist_ok=True)
    history = events / "state_owner_manifests"
    outside = tmp_path.parent / "state-owner-history-outside"
    outside.mkdir()
    history.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ManifestMalformed, match="atomic write parent"):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})


def test_commit_can_bind_post_prepare_final_observation(tmp_path):
    (tmp_path / "state.json").write_text("before\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("after\n", encoding="utf-8")
    committed = commit_manifest(
        binding(tmp_path), prepared, files={"task_state": "state.json"}
    )
    assert committed.state == COMMITTED
    assert committed.files[0].size == len(b"after\n")


def test_existing_transaction_cannot_be_overwritten(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    assert prepared.state == PREPARED
    with pytest.raises(OwnerConflict):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})


def test_prepare_denies_physical_bytes_diverging_from_committed_final(tmp_path):
    (tmp_path / "state.json").write_text("a\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("b\n", encoding="utf-8")
    committed = commit_manifest(binding(tmp_path), prepared, files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("UNCOMMITTED-TAMPER\n", encoding="utf-8")
    with pytest.raises(ManifestTampered):
        prepare_manifest(
            binding(tmp_path, tx="tx-2", generation=2),
            writer_id="w",
            files={"task_state": "state.json"},
            previous_manifest_sha256=committed.manifest_sha256,
        )
    assert read_manifest(tmp_path).manifest_sha256 == committed.manifest_sha256


def test_prepare_denies_cross_owner_binding_before_snapshot(tmp_path):
    (tmp_path / "state.json").write_text("committed\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    committed = commit_manifest(binding(tmp_path), prepared)
    before = (tmp_path / "state.json").read_bytes()
    install_generation(tmp_path, EventWriterGeneration(2, "w"), expected_generation=1)
    with pytest.raises(OwnerConflict):
        prepare_manifest(
            StateOwnerBinding("owner-b", tmp_path.resolve(), 2, "tx-owner-b"),
            writer_id="w",
            files={"task_state": "state.json"},
            previous_manifest_sha256=committed.manifest_sha256,
        )
    assert (tmp_path / "state.json").read_bytes() == before


def test_prepare_denies_copied_root_before_snapshot(tmp_path):
    (tmp_path / "state.json").write_text("committed\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    committed = commit_manifest(binding(tmp_path), prepared)
    copied = tmp_path.parent / f"{tmp_path.name}-copy"
    shutil.copytree(tmp_path, copied)
    before = (copied / "state.json").read_bytes()
    install_generation(copied, EventWriterGeneration(2, "w"), expected_generation=1)
    with pytest.raises(OwnerConflict):
        prepare_manifest(
            StateOwnerBinding("owner-a", copied.resolve(), 2, "tx-copy"),
            writer_id="w",
            files={"task_state": "state.json"},
            previous_manifest_sha256=committed.manifest_sha256,
        )
    assert (copied / "state.json").read_bytes() == before


def test_commit_rejects_changed_selected_path(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "other.json").write_text("{}", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    with pytest.raises(ManifestMalformed):
        commit_manifest(binding(tmp_path), prepared, files={"task_state": "other.json"})


def test_classification_detects_committed_tamper(tmp_path):
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files=files(tmp_path))
    commit_manifest(binding(tmp_path), prepared)
    (tmp_path / ".nexus/events/event_log.jsonl").write_text("rewritten\n", encoding="utf-8")
    outcome = classify(binding(tmp_path))
    assert outcome.status == TAMPERED_OR_UNKNOWN
    assert outcome.reconcile_only is True


def test_classification_rejects_symlink_even_when_bytes_match(tmp_path):
    outside = tmp_path.parent / "state-owner-classify-outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    (tmp_path / "state.json").write_text("{}\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    commit_manifest(binding(tmp_path), prepared)
    (tmp_path / "state.json").unlink()
    (tmp_path / "state.json").symlink_to(outside)
    outcome = classify(binding(tmp_path))
    assert outcome.status == TAMPERED_OR_UNKNOWN
    assert outcome.reconcile_only is True


@pytest.mark.parametrize("generation", [True, 0, -1, "1"])
def test_binding_rejects_invalid_generation(tmp_path, generation):
    with pytest.raises(ManifestMalformed):
        StateOwnerBinding("owner", tmp_path.resolve(), generation, "tx")


def test_explicit_absolute_root_and_no_default_root(tmp_path):
    with pytest.raises(ManifestMalformed):
        StateOwnerBinding("owner", Path("relative"), 1, "tx")
    assert read_manifest(tmp_path) is None
    assert classify(StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "tx")).status == ABSENT
    assert not (tmp_path / ".nexus").exists()


@pytest.mark.parametrize("bad", ["/outside", "../outside", "./state.json", "state/../state.json"])
def test_path_fencing(tmp_path, bad):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestMalformed):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": bad})


def test_symlink_and_nonregular_file_rejected(tmp_path):
    outside = tmp_path.parent / "state-owner-outside.json"
    outside.write_text("{}", encoding="utf-8")
    (tmp_path / "state.json").symlink_to(outside)
    with pytest.raises(ManifestMalformed):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").unlink()
    os.mkfifo(tmp_path / "state.json")
    with pytest.raises(ManifestMalformed):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})


def test_unknown_role_and_caller_rollback_relabel_rejected(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestMalformed):
        prepare_manifest(binding(tmp_path), writer_id="w", files={"arbitrary": "state.json"})


def test_transaction_path_is_validated_before_snapshot_write(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ManifestMalformed):
        prepare_manifest(
            binding(tmp_path, tx="../escape"),
            writer_id="w",
            files={"task_state": "state.json"},
        )
    assert not (tmp_path.parent / "escape").exists()


def test_event_and_effect_roles_are_never_rollbackable(tmp_path):
    assert NEVER_ROLLBACK
    event_path = tmp_path / ".nexus/events/event_log.jsonl"
    event_path.parent.mkdir(parents=True, exist_ok=True)
    event_path.write_text("{}\n", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"event_log": ".nexus/events/event_log.jsonl"})
    commit_manifest(binding(tmp_path), prepared)
    with pytest.raises(RecoveryDenied):
        restore_previous_committed(binding(tmp_path), recovery_mode=RECOVERY_ONLY)


def test_restore_requires_recovery_only_and_restores_previous_mutable_snapshot(tmp_path):
    (tmp_path / "state.json").write_text("old\n", encoding="utf-8")
    first = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("committed\n", encoding="utf-8")
    first = commit_manifest(binding(tmp_path), first, files={"task_state": "state.json"})
    second = prepare_manifest(
        binding(tmp_path, tx="tx-2", generation=2),
        writer_id="w",
        files={"task_state": "state.json"},
        previous_manifest_sha256=first.manifest_sha256,
    )
    (tmp_path / "state.json").write_text("pending\n", encoding="utf-8")
    assert second.state == PREPARED
    with pytest.raises(RecoveryDenied):
        restore_previous_committed(binding(tmp_path, tx="tx-2", generation=2), recovery_mode="AUTO")
    outcome = restore_previous_committed(
        binding(tmp_path, tx="tx-2", generation=2), recovery_mode=RECOVERY_ONLY
    )
    assert outcome.reconcile_only is True
    assert outcome.restored_roles == ("task_state",)
    assert outcome.recovery_transaction_id
    assert (tmp_path / ".nexus/events/state_owner_recovery" / f"{outcome.recovery_transaction_id}.json").exists()
    assert (tmp_path / "state.json").read_text(encoding="utf-8") == "committed\n"


def test_restore_prevalidates_all_mutable_snapshots_before_any_write(tmp_path):
    (tmp_path / "a.json").write_text("a-old\n", encoding="utf-8")
    (tmp_path / "b.json").write_text("b-old\n", encoding="utf-8")
    first = prepare_manifest(
        binding(tmp_path), writer_id="w", files={"task_state": "a.json", "runtime_receipt": "b.json"}
    )
    (tmp_path / "a.json").write_text("a-committed\n", encoding="utf-8")
    (tmp_path / "b.json").write_text("b-committed\n", encoding="utf-8")
    first = commit_manifest(
        binding(tmp_path), first, files={"task_state": "a.json", "runtime_receipt": "b.json"}
    )
    prepare_manifest(
        binding(tmp_path, tx="tx-2", generation=2),
        writer_id="w",
        files={"task_state": "a.json", "runtime_receipt": "b.json"},
        previous_manifest_sha256=first.manifest_sha256,
    )
    (tmp_path / "a.json").write_text("a-pending\n", encoding="utf-8")
    (tmp_path / "b.json").write_text("b-pending\n", encoding="utf-8")
    snapshot = tmp_path / ".nexus/events/state_owner_snapshots/tx-2/runtime_receipt.snapshot"
    snapshot.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ManifestTampered):
        restore_previous_committed(binding(tmp_path, tx="tx-2", generation=2), recovery_mode=RECOVERY_ONLY)
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == "a-pending\n"
    assert (tmp_path / "b.json").read_text(encoding="utf-8") == "b-pending\n"


def test_restore_denies_irreversible_event_progress_before_mutable_write(tmp_path):
    (tmp_path / "state.json").write_text("state-a\n", encoding="utf-8")
    events = tmp_path / ".nexus/events"
    events.mkdir(parents=True, exist_ok=True)
    event_path = events / "event_log.jsonl"
    event_path.write_text('{"event":"A"}\n', encoding="utf-8")
    first = prepare_manifest(
        binding(tmp_path),
        writer_id="w",
        files={"task_state": "state.json", "event_log": ".nexus/events/event_log.jsonl"},
    )
    (tmp_path / "state.json").write_text("state-b\n", encoding="utf-8")
    first = commit_manifest(
        binding(tmp_path), first,
        files={"task_state": "state.json", "event_log": ".nexus/events/event_log.jsonl"},
    )
    second = prepare_manifest(
        binding(tmp_path, tx="tx-2", generation=2),
        writer_id="w",
        files={"task_state": "state.json", "event_log": ".nexus/events/event_log.jsonl"},
        previous_manifest_sha256=first.manifest_sha256,
    )
    (tmp_path / "state.json").write_text("state-c\n", encoding="utf-8")
    event_path.write_text('{"event":"A"}\n{"event":"IRREVERSIBLE"}\n', encoding="utf-8")
    with pytest.raises(RecoveryDenied, match="immutable progress"):
        restore_previous_committed(binding(tmp_path, tx="tx-2", generation=2), recovery_mode=RECOVERY_ONLY)
    assert (tmp_path / "state.json").read_text(encoding="utf-8") == "state-c\n"
    assert "IRREVERSIBLE" in event_path.read_text(encoding="utf-8")


def test_cross_owner_generation_denied_before_restore(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files={"task_state": "state.json"})
    commit_manifest(binding(tmp_path), prepared)
    with pytest.raises(OwnerConflict):
        classify(StateOwnerBinding("other", tmp_path.resolve(), 1, "tx-1"))


def test_manifest_digest_tamper_rejected(tmp_path):
    prepared = prepare_manifest(binding(tmp_path), writer_id="w", files=files(tmp_path))
    commit_manifest(binding(tmp_path), prepared)
    path = manifest_path(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["owner_id"] = "other"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestTampered):
        read_manifest(tmp_path)


def test_same_transaction_supports_distinct_task_entries(tmp_path):
    token = EventWriterGeneration(1, "w")
    install_generation(tmp_path, token)
    selections = (
        StateOwnerSelection("task:a", "task_state", "a.json"),
        StateOwnerSelection("task:b", "task_state", "b.json"),
    )
    binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "multi")
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        (tmp_path / "a.json").write_text("a\n", encoding="utf-8")
        (tmp_path / "b.json").write_text("b\n", encoding="utf-8")
        commit_owner_transaction(context)
    manifest = read_manifest(tmp_path)
    assert {(item.entry_id, item.relative_path) for item in manifest.files} == {
        ("task:a", "a.json"), ("task:b", "b.json")
    }


def test_same_generation_crash_then_explicit_new_generation_recovery(tmp_path):
    token = EventWriterGeneration(1, "w")
    install_generation(tmp_path, token)
    first_binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "tx-1")
    (tmp_path / "state.json").write_text("initial\n", encoding="utf-8")
    first = prepare_manifest(first_binding, writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("committed\n", encoding="utf-8")
    first = commit_manifest(first_binding, first, files={"task_state": "state.json"})
    second_binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "tx-2")
    prepare_manifest(second_binding, writer_id="w", files={"task_state": "state.json"}, previous_manifest_sha256=first.manifest_sha256)
    crash_script = "from pathlib import Path; import os, sys; Path(sys.argv[1]).write_text('pending-before-crash\\n'); os._exit(37)"
    child = subprocess.run([sys.executable, "-c", crash_script, str(tmp_path / "state.json")], timeout=3)
    assert child.returncode == 37
    recovery_token = EventWriterGeneration(2, "recovery-w")
    install_generation(tmp_path, recovery_token, expected_generation=1)
    recovery_binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 2, "recovery-tx")
    outcome = restore_previous_committed(
        second_binding, recovery_binding=recovery_binding, writer_generation=recovery_token,
        recovery_mode=RECOVERY_ONLY
    )
    assert outcome.reconcile_only is True
    assert (tmp_path / "state.json").read_text(encoding="utf-8") == "committed\n"
    assert list((tmp_path / ".nexus/events/state_owner_recovery").glob("tx-2.recovery.*.json"))
    classified = classify(
        second_binding,
        recovery_binding=recovery_binding,
        recovery_writer_generation=recovery_token,
    )
    assert classified.status == PREPARED_UNKNOWN


def test_recovery_classification_requires_exact_token_and_bound_marker(tmp_path):
    token = EventWriterGeneration(1, "w")
    install_generation(tmp_path, token)
    failed = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "failed")
    (tmp_path / "state.json").write_text("a\n", encoding="utf-8")
    first = prepare_manifest(failed, writer_id="w", files={"task_state": "state.json"})
    (tmp_path / "state.json").write_text("b\n", encoding="utf-8")
    commit_manifest(failed, first, files={"task_state": "state.json"})
    with pytest.raises(RecoveryDenied):
        classify(failed, recovery_binding=StateOwnerBinding("owner-a", tmp_path.resolve(), 2, "r"))


def test_recovery_classification_rejects_unbound_committed_manifest(tmp_path):
    token = EventWriterGeneration(1, "w")
    install_generation(tmp_path, token)
    binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "committed")
    (tmp_path / "state.json").write_text("a\n", encoding="utf-8")
    prepared = prepare_manifest(binding, writer_id="w", files={"task_state": "state.json"})
    commit_manifest(binding, prepared)
    recovery = StateOwnerBinding("owner-a", tmp_path.resolve(), 2, "recovery")
    recovery_token = EventWriterGeneration(2, "w2")
    install_generation(tmp_path, recovery_token, expected_generation=1)
    with pytest.raises(RecoveryDenied):
        classify(binding, recovery_binding=recovery, recovery_writer_generation=recovery_token)


def test_child_cannot_reuse_owner_context_or_inherited_lock(tmp_path):
    token = EventWriterGeneration(1, "w")
    install_generation(tmp_path, token)
    binding = StateOwnerBinding("owner-a", tmp_path.resolve(), 1, "fork-tx")
    selections = (StateOwnerSelection("task:fork", "task_state", "state.json"),)
    read_fd, write_fd = os.pipe()
    with owner_transaction_guard(binding, writer_generation=token, selections=selections) as context:
        pid = os.fork()
        if pid == 0:
            try:
                try:
                    assert_owner_write(context, role="task_state", relative_path="state.json")
                except OwnerConflict:
                    os.write(write_fd, b"OWNER_CONFLICT\n")
                except BaseException as exc:
                    os.write(write_fd, ("ERROR:" + type(exc).__name__ + ":" + str(exc) + "\n").encode())
                try:
                    with event_store_lock(tmp_path, timeout=0.05):
                        os.write(write_fd, b"UNEXPECTED_LOCK\n")
                except GenerationError:
                    os.write(write_fd, b"LOCK_TIMEOUT\n")
                except BaseException as exc:
                    os.write(write_fd, ("ERROR2:" + type(exc).__name__ + "\n").encode())
            finally:
                os._exit(0)
        _, status = os.waitpid(pid, 0)
        os.close(write_fd)
        observed = os.read(read_fd, 4096).decode().splitlines()
        os.close(read_fd)
        assert os.waitstatus_to_exitcode(status) == 0
        assert observed == ["OWNER_CONFLICT", "LOCK_TIMEOUT"]
