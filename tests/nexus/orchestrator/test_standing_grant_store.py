from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nexus.orchestrator.standing_grant_store as standing_grant_store
from nexus.contracts.autonomy_goal import (
    AutonomyActionClass,
    RepositoryIdentity,
    StandingGrantContext,
)
from nexus.orchestrator.standing_grant_store import (
    DEFAULT_RECEIPT_PATH,
    StandingGrantReceipt,
    StandingGrantReceiptError,
    _check_dir,
    _load_receipt_at,
    _write_standing_grant_receipt_at,
    load_standing_grant_receipt,
    write_standing_grant_receipt,
)

NOW = datetime.now(timezone.utc)


def _repository() -> RepositoryIdentity:
    return RepositoryIdentity(
        repository_id="James3014/Nexus-new",
        canonical_remote="https://github.com/James3014/Nexus-new.git",
    )


def _make_context(**overrides) -> StandingGrantContext:
    values = dict(
        owner_id="owner-james",
        coordinator_id="coordinator-codex",
        repository=_repository(),
        thread_id="thread-163",
        goal_id="goal-163",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
    )
    values.update(overrides)
    return StandingGrantContext.issue(**values)


def _make_receipt(
    tmp_path: Path, *, grant_id="grant-test-1", **context_overrides
) -> tuple[StandingGrantReceipt, Path]:
    path = tmp_path / "authority" / f"{grant_id}.json"
    context = _make_context(**context_overrides)
    receipt = StandingGrantReceipt.issue(grant_id=grant_id, context=context)
    _write_standing_grant_receipt_at(receipt, path)
    return receipt, path


def test_red_default_receipt_path_is_canonical_machine_local(tmp_path):
    path = Path(DEFAULT_RECEIPT_PATH)
    assert path.is_absolute()
    assert "local" in path.parts or "state" in path.parts
    assert path.name == "standing-grant.json"


def test_default_receipt_is_absent_without_operator_issuance(tmp_path, monkeypatch):
    missing_path = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", missing_path)
    assert not missing_path.exists()
    outcome = load_standing_grant_receipt()
    assert outcome is None


def test_write_is_atomic_durable_with_restrictive_modes(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["grant_id"] == "grant-test-1"
    assert data["receipt_hash"]
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode & 0o077 == 0
    assert mode == 0o600


def test_receipt_binds_validated_nested_context_not_flat_duplicates(tmp_path):
    receipt, _path = _make_receipt(tmp_path)
    assert receipt.context.owner_id == "owner-james"
    assert receipt.context.coordinator_id == "coordinator-codex"
    # No top-level flattened duplicate authority fields.
    dumped = receipt.model_dump(mode="json")
    assert "context" in dumped
    assert "owner" not in dumped
    assert "primary_coordinator" not in dumped


def test_raw_writer_is_rejected(tmp_path):
    with pytest.raises(TypeError):
        write_standing_grant_receipt({"grant_id": "self-auth"}, expected_receipt_hash=None)


def test_receipt_hash_covers_context_and_supersedes(tmp_path):
    base = _make_context()
    a = StandingGrantReceipt.issue(grant_id="grant-a", context=base)
    b = StandingGrantReceipt.issue(
        grant_id="grant-b", context=base, supersedes_grant_hash=a.receipt_hash
    )
    assert a.receipt_hash != b.receipt_hash
    payload = b.model_dump(mode="json", exclude={"receipt_hash"})
    # Tampering with a nested context field changes the receipt hash.
    tampered = {**payload, "context": {**payload["context"], "goal_id": "other"}}
    with pytest.raises(Exception):
        StandingGrantReceipt.model_validate({
            **tampered,
            "receipt_hash": "0" * 64,
        })


def test_supersedes_hash_is_sha256_hex_and_self_reference_is_documented_limitation():
    base = _make_context()
    with pytest.raises(Exception, match="SUPERSEDES_HASH_INVALID"):
        StandingGrantReceipt.issue(
            grant_id="grant-a", context=base, supersedes_grant_hash="not-a-hash"
        )
    # Self-reference by hash is not detectable without a competitor store; the
    # writer CAS bounds successor/predessor lineage instead.
    receipt = StandingGrantReceipt.issue(
        grant_id="grant-a", context=base, supersedes_grant_hash="0" * 64
    )
    assert receipt.supersedes_grant_hash == "0" * 64


def test_loader_rejects_symlink_and_non_regular_file(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    target = path
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(StandingGrantReceiptError, match="NOT_REGULAR_FILE"):
        _load_receipt_at(link)
    directory = tmp_path / "dir.json"
    directory.mkdir()
    with pytest.raises(StandingGrantReceiptError, match="NOT_REGULAR_FILE"):
        _load_receipt_at(directory)

    dangling = tmp_path / "dangling.json"
    dangling.symlink_to(tmp_path / "does-not-exist.json")
    with pytest.raises(StandingGrantReceiptError, match="NOT_REGULAR_FILE"):
        _load_receipt_at(dangling)


def test_loader_rejects_unsafe_file_permissions(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    os.chmod(path, 0o644)
    with pytest.raises(StandingGrantReceiptError, match="UNSAFE_PERMISSIONS"):
        _load_receipt_at(path)


def test_parent_symlink_and_world_writable_rejected(tmp_path):
    receipt = StandingGrantReceipt.issue(grant_id="grant-t", context=_make_context())
    # Symlink parent.
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    link_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(StandingGrantReceiptError, match="PARENT_SYMLINK"):
        _write_standing_grant_receipt_at(receipt, link_parent / "standing-grant.json")
    # A world-writable intermediate ancestor (not the authority leaf) is rejected.
    ww = tmp_path / "ww-intermediate"
    ww.mkdir()
    os.chmod(ww, 0o777)  # mkdir mode is subject to umask; force it.
    leaf = ww / "authority"
    leaf.mkdir(mode=0o700)
    with pytest.raises(StandingGrantReceiptError, match="PARENT_GROUP_OR_WORLD_WRITABLE"):
        _write_standing_grant_receipt_at(receipt, leaf / "standing-grant.json")


def test_root_owned_sticky_generic_ancestor_is_allowed():
    candidate = Path("/tmp")
    st = candidate.stat()
    if candidate.is_symlink() or st.st_uid != 0 or not st.st_mode & stat.S_ISVTX:
        pytest.skip("host has no standard root-owned sticky /tmp")
    _check_dir(candidate, strict_leaf=False)


def test_loader_rejects_duplicate_keys_and_noncanonical_bytes(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    text = path.read_text(encoding="utf-8")
    # Simpler direct check: duplicate key via JSON is hard to craft; verify exact
    # canonical serialization is required (trailing garbage).
    garbage = tmp_path / "garbage.json"
    garbage.write_text(text + "garbage", encoding="utf-8")
    os.chmod(garbage, 0o600)
    with pytest.raises(StandingGrantReceiptError, match="NONCANONICAL_SERIALIZATION"):
        _load_receipt_at(garbage)

    duplicate = tmp_path / "duplicate.json"
    valid = json.dumps(
        receipt.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    marker = '"grant_id":"grant-test-1",'
    assert marker in valid
    duplicate.write_text(valid.replace(marker, marker + marker, 1), encoding="utf-8")
    os.chmod(duplicate, 0o600)
    with pytest.raises(StandingGrantReceiptError, match="MALFORMED") as raised:
        _load_receipt_at(duplicate)
    assert raised.value.__cause__ is not None
    assert "DUPLICATE_KEY" in str(raised.value.__cause__)


def test_loader_validates_receipt_hash_and_rejects_tamper(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    # Tamper a top-level binding field without touching the nested context so the
    # outer receipt-hash check (not context validation) is what rejects.
    parsed["grant_id"] = "tampered-grant"
    # Keep canonical serialization so the hash check (not serialization) rejects.
    path.write_text(
        json.dumps(parsed, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    with pytest.raises(StandingGrantReceiptError, match="TAMPERED|RECEIPT_HASH_INVALID"):
        _load_receipt_at(path)


def test_loader_rejects_malformed_json_and_missing_file(tmp_path):
    path = tmp_path / "standing-grant.json"
    path.write_text("{not json", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(StandingGrantReceiptError, match="MALFORMED"):
        _load_receipt_at(path)
    with pytest.raises(StandingGrantReceiptError, match="RECEIPT_MISSING"):
        _load_receipt_at(tmp_path / "missing.json")


def test_fresh_process_loader_returns_same_validated_receipt(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    code = (
        "import json, sys;"
        "from pathlib import Path;"
        "from nexus.orchestrator.standing_grant_store import _load_receipt_at;"
        "r = _load_receipt_at(Path(sys.argv[1]));"
        "print(json.dumps(r.model_dump(mode='json'), sort_keys=True))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3])
    result = subprocess.run(
        [os.sys.executable, "-c", code, str(path)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    fresh = json.loads(result.stdout)
    assert fresh["grant_id"] == "grant-test-1"
    assert fresh["context"]["context_hash"]


def test_two_requests_and_fresh_reader_reuse_same_grant_without_mutation(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    before = path.read_text(encoding="utf-8")
    first = _load_receipt_at(path)
    second = _load_receipt_at(path)
    assert first == second
    assert path.read_text(encoding="utf-8") == before


def test_expired_or_revoked_receipt_fails_closed_without_mutation(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing-authority" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", missing_path)
    _receipt, expired_path = _make_receipt(
        tmp_path, grant_id="expired", expires_at=(NOW - timedelta(minutes=1))
    )
    with pytest.raises(StandingGrantReceiptError, match="EXPIRED"):
        _load_receipt_at(expired_path, now=NOW)
    _receipt2, revoked_path = _make_receipt(
        tmp_path,
        grant_id="revoked",
        revoked_at=NOW,
        revocation_reason="owner revoked",
    )
    with pytest.raises(StandingGrantReceiptError, match="REVOKED"):
        _load_receipt_at(revoked_path)
    # Evaluation over a missing/default path mutates nothing and yields None.
    assert load_standing_grant_receipt(now=NOW) is None


def test_superseded_receipt_returns_rebinding_pointer(tmp_path):
    base = _make_context()
    first = StandingGrantReceipt.issue(grant_id="grant-0", context=base)
    second = StandingGrantReceipt.issue(
        grant_id="grant-1", context=base, supersedes_grant_hash=first.receipt_hash
    )
    path = tmp_path / "authority" / "standing-grant.json"
    _write_standing_grant_receipt_at(first, path)
    _write_standing_grant_receipt_at(second, path, expected_receipt_hash=first.receipt_hash)
    loaded = _load_receipt_at(path)
    assert loaded.supersedes_grant_hash == first.receipt_hash
    assert loaded.grant_id == "grant-1"


def test_stale_writer_cas_rejects_revive_overwrite(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    base = _make_context()
    replacement = StandingGrantReceipt.issue(
        grant_id="grant-new", context=base, supersedes_grant_hash=receipt.receipt_hash
    )
    with pytest.raises(StandingGrantReceiptError, match="SUPERSEDES_CAS_MISMATCH"):
        _write_standing_grant_receipt_at(replacement, path, expected_receipt_hash="0" * 64)
    # Correct CAS (predecessor receipt hash) allows the write.
    _write_standing_grant_receipt_at(replacement, path, expected_receipt_hash=receipt.receipt_hash)
    loaded = _load_receipt_at(path)
    assert loaded.grant_id == "grant-new"
    assert replacement.receipt_hash != receipt.receipt_hash


def test_supersedes_hash_binds_current_cas_on_write(tmp_path):
    base = _make_context()
    predecessor = StandingGrantReceipt.issue(grant_id="grant-p", context=base)
    successor = StandingGrantReceipt.issue(
        grant_id="grant-s", context=base, supersedes_grant_hash=predecessor.receipt_hash
    )
    path = tmp_path / "authority" / "standing-grant.json"
    # Writing the successor requires the predecessor's current hash as CAS.
    _write_standing_grant_receipt_at(predecessor, path)
    _write_standing_grant_receipt_at(
        successor, path, expected_receipt_hash=predecessor.receipt_hash
    )
    loaded = _load_receipt_at(path)
    assert loaded.grant_id == "grant-s"
    assert loaded.supersedes_grant_hash == predecessor.receipt_hash


def test_write_requires_cas_when_file_exists(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    replacement = StandingGrantReceipt.issue(
        grant_id="grant-new-2", context=_make_context(), supersedes_grant_hash=receipt.receipt_hash
    )
    with pytest.raises(StandingGrantReceiptError, match="EXISTS_NO_CAS"):
        _write_standing_grant_receipt_at(replacement, path)


def test_initial_write_rejects_predecessor_or_cas(tmp_path):
    context = _make_context()
    successor = StandingGrantReceipt.issue(
        grant_id="grant-initial-successor",
        context=context,
        supersedes_grant_hash="0" * 64,
    )
    with pytest.raises(StandingGrantReceiptError, match="INITIAL_WRITE_NO_SUPERSEDES"):
        _write_standing_grant_receipt_at(
            successor,
            tmp_path / "authority" / "standing-grant.json",
            expected_receipt_hash="0" * 64,
        )


def test_replacement_rejects_predecessor_cas_mismatch(tmp_path):
    predecessor, path = _make_receipt(tmp_path)
    successor = StandingGrantReceipt.issue(
        grant_id="grant-cas-mismatch",
        context=_make_context(),
        supersedes_grant_hash=predecessor.receipt_hash,
    )
    with pytest.raises(StandingGrantReceiptError, match="SUPERSEDES_CAS_MISMATCH"):
        _write_standing_grant_receipt_at(successor, path, expected_receipt_hash="0" * 64)


def test_interprocess_cas_race_allows_exactly_one_successor(tmp_path):
    predecessor, path = _make_receipt(tmp_path, grant_id="race-predecessor")
    successors = []
    for name in ("race-a", "race-b"):
        successor = StandingGrantReceipt.issue(
            grant_id=name,
            context=_make_context(),
            supersedes_grant_hash=predecessor.receipt_hash,
        )
        payload = tmp_path / f"{name}.json"
        payload.write_text(json.dumps(successor.model_dump(mode="json")), encoding="utf-8")
        successors.append(payload)
    code = (
        "import json,sys; from pathlib import Path; "
        "from nexus.orchestrator.standing_grant_store import StandingGrantReceipt,_write_standing_grant_receipt_at; "
        "r=StandingGrantReceipt.model_validate(json.loads(Path(sys.argv[2]).read_text())); "
        "_write_standing_grant_receipt_at(r,Path(sys.argv[1]),expected_receipt_hash=sys.argv[3]); print(r.grant_id)"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[3]))
    processes = [
        subprocess.Popen(
            [os.sys.executable, "-c", code, str(path), str(payload), predecessor.receipt_hash],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for payload in successors
    ]
    results = [process.communicate(timeout=10) for process in processes]
    assert sum(process.returncode == 0 for process in processes) == 1
    assert sum(process.returncode != 0 for process in processes) == 1
    assert any(
        "SUPERSEDES_CAS_MISMATCH" in stderr or "STALE_WRITER_CAS_MISMATCH" in stderr
        for (_stdout, stderr) in results
    )
    winner = _load_receipt_at(path)
    assert winner.grant_id in {"race-a", "race-b"}


def test_exact_mode_and_size(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    size = os.stat(path).st_size
    assert 0 < size < 16 * 1024
