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
    _authorize_durable_standing_grant_effect_at,
    _check_dir,
    _load_receipt_at,
    _restore_task_card_authority_at,
    _switch_task_card_authority_at,
    _write_standing_grant_receipt_at,
    load_standing_grant_receipt,
    restore_task_card_authority,
    switch_task_card_authority,
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
    missing = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", missing)
    assert not missing.exists()
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
    # Evaluation over a missing canonical path mutates nothing and yields None.
    missing = tmp_path / "missing-authority" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", missing)
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


def test_effect_authorization_binds_exact_action_and_effect_without_mutating_grant(tmp_path):
    _receipt, path = _make_receipt(
        tmp_path,
        grant_id="effect-authority",
        allowed_actions=(AutonomyActionClass.TASK_CARD_CREATE,),
    )
    before = path.read_bytes()
    effect = {
        "campaign_id": "g3-security",
        "task_id": "authority-closure",
        "expected_head": "a" * 40,
        "allowed_files": ["nexus/orchestrator/unified_mcp_gateway.py"],
    }

    authority = _authorize_durable_standing_grant_effect_at(
        path,
        repository=_repository(),
        action=AutonomyActionClass.TASK_CARD_CREATE,
        effect=effect,
        requested_at=NOW,
    )

    assert authority["mutation_authorized"] is True
    assert authority["action"] == "TASK_CARD_CREATE"
    assert authority["effect"] == effect
    assert len(authority["effect_hash"]) == 64
    assert len(authority["authorization_hash"]) == 64
    assert authority["grant_receipt_hash"]
    assert path.read_bytes() == before


def test_effect_authorization_fails_closed_when_action_is_out_of_scope(tmp_path):
    _receipt, path = _make_receipt(
        tmp_path,
        grant_id="effect-out-of-scope",
        allowed_actions=(AutonomyActionClass.CANDIDATE_REJECT,),
    )

    with pytest.raises(StandingGrantReceiptError, match="AUTHORIZATION_OUT_OF_SCOPE"):
        _authorize_durable_standing_grant_effect_at(
            path,
            repository=_repository(),
            action=AutonomyActionClass.CANDIDATE_SUPERSEDE,
            effect={"task_id": "candidate-1", "superseded_by": "candidate-2"},
            requested_at=NOW,
        )


def test_effect_authorization_allows_external_candidate_adoption(tmp_path):
    _receipt, path = _make_receipt(
        tmp_path,
        grant_id="effect-adopt-external",
        allowed_actions=(AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL,),
    )

    authority = _authorize_durable_standing_grant_effect_at(
        path,
        repository=_repository(),
        action=AutonomyActionClass.CANDIDATE_ADOPT_EXTERNAL,
        effect={"task_id": "TASK-EPB-001-R1", "candidate_commit_sha": "a" * 40},
        requested_at=NOW,
    )

    assert authority["mutation_authorized"] is True
    assert authority["action"] == "CANDIDATE_ADOPT_EXTERNAL"


def test_effect_authorization_rejects_repository_substitution(tmp_path):
    _receipt, path = _make_receipt(
        tmp_path,
        grant_id="effect-repository",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
    )
    wrong = RepositoryIdentity(
        repository_id="James3014/Other",
        canonical_remote="https://github.com/James3014/Other.git",
    )

    with pytest.raises(StandingGrantReceiptError, match="AUTHORIZATION_REPOSITORY_MISMATCH"):
        _authorize_durable_standing_grant_effect_at(
            path,
            repository=wrong,
            action=AutonomyActionClass.REPOSITORY_PUSH,
            effect={
                "remote": "origin",
                "branch": "nexus/integration/main",
                "expected_sha": "b" * 40,
            },
            requested_at=NOW,
        )


def test_exact_mode_and_size(tmp_path):
    receipt, path = _make_receipt(tmp_path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    size = os.stat(path).st_size
    assert 0 < size < 16 * 1024


def test_switch_task_card_authority_success(tmp_path):
    receipt, path = _make_receipt(
        tmp_path,
        grant_id="grant-orig",
        goal_id="goal-orig",
        thread_id="thread-orig",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
    )
    res = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-1",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-orig",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    assert res["schema"] == "nexus.task_card_authority_switch.v1"
    assert res["status"] == "SWITCHED"
    assert res["predecessor_receipt_hash"] == receipt.receipt_hash
    assert res["predecessor_goal_id"] == "goal-orig"
    assert res["temporary_goal_id"] == "goal-temp"
    assert res["temporary_thread_id"] == "thread-temp"
    assert res["allowed_actions"] == ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"]
    assert res["owner_confirmation"] is True
    assert res["temporary_receipt_hash"] != receipt.receipt_hash

    current = _load_receipt_at(path, now=NOW)
    assert current.receipt_hash == res["temporary_receipt_hash"]
    assert current.context.goal_id == "goal-temp"
    assert current.context.thread_id == "thread-temp"
    assert set(current.context.allowed_actions) == {
        AutonomyActionClass.TASK_CARD_COMMIT,
        AutonomyActionClass.TASK_CARD_CREATE,
    }
    assert current.supersedes_grant_hash == receipt.receipt_hash


def test_switch_task_card_authority_bounds_expiry_by_predecessor(tmp_path):
    predecessor_expiry = NOW + timedelta(minutes=10)
    receipt, path = _make_receipt(
        tmp_path,
        grant_id="grant-short-lived",
        goal_id="goal-orig",
        thread_id="thread-orig",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
        expires_at=predecessor_expiry,
    )
    res = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-bounded-expiry",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-orig",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=25,
        owner_confirmation=True,
        now=NOW,
    )
    assert res["schema"] == "nexus.task_card_authority_switch.v1"
    assert res["status"] == "SWITCHED"
    assert res["expires_at"] == predecessor_expiry.isoformat()

    current = _load_receipt_at(path, now=NOW)
    assert current.receipt_hash == res["temporary_receipt_hash"]
    assert current.context.expires_at == predecessor_expiry
    assert current.context.expires_at < NOW + timedelta(minutes=25)


def test_switch_task_card_authority_idempotency_and_conflict(tmp_path):
    receipt, path = _make_receipt(tmp_path, goal_id="goal-orig")
    res1 = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-idem",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-orig",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    res2 = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-idem",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-orig",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    assert res1 == res2

    with pytest.raises(StandingGrantReceiptError, match="ATTEMPT_KEY_CONFLICT"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-switch-idem",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-orig",
            successor_goal_id="goal-different",
            successor_thread_id="thread-temp",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )


def test_switch_task_card_authority_fails_closed(tmp_path):
    receipt, path = _make_receipt(tmp_path, goal_id="goal-orig")
    # Missing owner confirmation
    with pytest.raises(StandingGrantReceiptError, match="OWNER_CONFIRMATION_REQUIRED"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-fail-1",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-orig",
            successor_goal_id="goal-temp",
            successor_thread_id="thread-temp",
            ttl_minutes=15,
            owner_confirmation=False,
            now=NOW,
        )
    # TTL > 30 minutes
    with pytest.raises(StandingGrantReceiptError, match="TTL_MINUTES_INVALID"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-fail-2",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-orig",
            successor_goal_id="goal-temp",
            successor_thread_id="thread-temp",
            ttl_minutes=31,
            owner_confirmation=True,
            now=NOW,
        )
    # Current hash mismatch
    with pytest.raises(StandingGrantReceiptError, match="CURRENT_RECEIPT_HASH_MISMATCH"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-fail-3",
            expected_current_receipt_hash="0" * 64,
            expected_current_goal_id="goal-orig",
            successor_goal_id="goal-temp",
            successor_thread_id="thread-temp",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )
    # Current goal mismatch
    with pytest.raises(StandingGrantReceiptError, match="CURRENT_GOAL_MISMATCH"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-fail-4",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="wrong-goal",
            successor_goal_id="goal-temp",
            successor_thread_id="thread-temp",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )


def test_restore_task_card_authority_success(tmp_path):
    receipt, path = _make_receipt(
        tmp_path,
        grant_id="grant-pred",
        goal_id="goal-pred",
        thread_id="thread-pred",
        allowed_actions=(AutonomyActionClass.GITHUB_MERGE,),
    )
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-for-restore",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=10,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    restored = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-1",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW + timedelta(minutes=2),
    )
    assert restored["schema"] == "nexus.task_card_authority_restore.v1"
    assert restored["status"] == "RESTORED"
    assert restored["restored_goal_id"] == "goal-pred"
    assert restored["restored_thread_id"] == "thread-pred"
    assert restored["restored_allowed_actions"] == ["GITHUB_MERGE"]
    assert restored["temporary_receipt_hash"] == temp_hash

    current = _load_receipt_at(path, now=NOW + timedelta(minutes=2))
    assert current.receipt_hash == restored["restored_receipt_hash"]
    assert current.context.goal_id == "goal-pred"
    assert current.context.thread_id == "thread-pred"
    assert current.context.allowed_actions == (AutonomyActionClass.GITHUB_MERGE,)
    assert current.supersedes_grant_hash == temp_hash


def test_restore_task_card_authority_idempotency_and_conflict(tmp_path):
    receipt, path = _make_receipt(tmp_path, goal_id="goal-pred")
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-idem-restore",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=10,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    r1 = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-idem",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW,
    )
    r2 = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-idem",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW,
    )
    assert r1 == r2

    with pytest.raises(StandingGrantReceiptError, match="ATTEMPT_KEY_CONFLICT"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-restore-idem",
            switch_operation_id="other_op",
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=True,
            now=NOW,
        )


def test_restore_task_card_authority_fails_closed(tmp_path):
    receipt, path = _make_receipt(tmp_path, goal_id="goal-pred")
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-fail-restore",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred",
        successor_goal_id="goal-temp",
        successor_thread_id="thread-temp",
        ttl_minutes=10,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    # Unknown operation id
    with pytest.raises(StandingGrantReceiptError, match="SWITCH_OPERATION_NOT_FOUND"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-r-fail-1",
            switch_operation_id="nonexistent_op",
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=True,
            now=NOW,
        )

    # Expected temporary hash mismatch
    with pytest.raises(StandingGrantReceiptError, match="TEMPORARY_RECEIPT_HASH_MISMATCH"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-r-fail-2",
            switch_operation_id=op_id,
            expected_temporary_receipt_hash="0" * 64,
            owner_confirmation=True,
            now=NOW,
        )

    # Missing owner confirmation
    with pytest.raises(StandingGrantReceiptError, match="OWNER_CONFIRMATION_REQUIRED"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-r-fail-3",
            switch_operation_id=op_id,
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=False,
            now=NOW,
        )


def test_restore_succeeds_even_when_temporary_grant_expired(tmp_path):
    receipt, path = _make_receipt(
        tmp_path,
        grant_id="grant-exp-pred",
        goal_id="goal-exp-pred",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
    )
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-exp",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-exp-pred",
        successor_goal_id="goal-temp-exp",
        successor_thread_id="thread-temp-exp",
        ttl_minutes=5,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    # At NOW + 10 minutes, the 5-minute temporary grant is expired
    with pytest.raises(StandingGrantReceiptError, match="EXPIRED"):
        _load_receipt_at(path, now=NOW + timedelta(minutes=10))

    # Restore must still succeed
    restored = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-exp",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW + timedelta(minutes=10),
    )
    assert restored["status"] == "RESTORED"
    assert restored["restored_goal_id"] == "goal-exp-pred"


def test_public_switch_and_restore_use_canonical_path_and_reject_receipt_path(
    monkeypatch, tmp_path
):
    canonical_path = tmp_path / "authority" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", canonical_path)
    monkeypatch.setattr(
        standing_grant_store, "DEFAULT_TRANSITIONS_DIR", tmp_path / "authority" / "transitions"
    )

    context = _make_context(
        goal_id="goal-pub",
        thread_id="thread-pub",
        allowed_actions=(AutonomyActionClass.REPOSITORY_PUSH,),
    )
    orig_receipt = StandingGrantReceipt.issue(grant_id="grant-pub", context=context)
    _write_standing_grant_receipt_at(orig_receipt, canonical_path)

    # Public APIs reject arbitrary receipt_path argument
    with pytest.raises(TypeError):
        switch_task_card_authority(  # type: ignore[call-arg]
            attempt_key="attempt-pub-1",
            expected_current_receipt_hash=orig_receipt.receipt_hash,
            expected_current_goal_id="goal-pub",
            successor_goal_id="goal-succ",
            successor_thread_id="thread-succ",
            ttl_minutes=15,
            owner_confirmation=True,
            receipt_path=canonical_path,
        )

    with pytest.raises(TypeError):
        restore_task_card_authority(  # type: ignore[call-arg]
            attempt_key="attempt-pub-2",
            switch_operation_id="switch_123",
            expected_temporary_receipt_hash=orig_receipt.receipt_hash,
            owner_confirmation=True,
            receipt_path=canonical_path,
        )

    # Public API operates correctly on canonical DEFAULT_RECEIPT_PATH
    switched = switch_task_card_authority(
        attempt_key="attempt-pub-switch",
        expected_current_receipt_hash=orig_receipt.receipt_hash,
        expected_current_goal_id="goal-pub",
        successor_goal_id="goal-succ",
        successor_thread_id="thread-succ",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    assert switched["status"] == "SWITCHED"
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    restored = restore_task_card_authority(
        attempt_key="attempt-pub-restore",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW,
    )
    assert restored["status"] == "RESTORED"
    assert restored["restored_goal_id"] == "goal-pub"


def test_switch_crash_before_cas_replay_succeeds(tmp_path, monkeypatch):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-crash-1", goal_id="goal-crash-1")

    # Fault injection: raise error on the first CAS call
    real_write_bytes_locked = standing_grant_store._write_bytes_locked
    cas_calls = 0

    def faulty_write_bytes_locked(*args, **kwargs):
        nonlocal cas_calls
        cas_calls += 1
        raise RuntimeError("SIMULATED_CRASH_BEFORE_SWITCH_CAS")

    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", faulty_write_bytes_locked)

    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_BEFORE_SWITCH_CAS"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-switch-crash-before-cas",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-crash-1",
            successor_goal_id="goal-succ-1",
            successor_thread_id="thread-succ-1",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )

    # Verify state on disk: physical receipt has NOT changed (predecessor still present)
    current = _load_receipt_at(path, now=NOW)
    assert current.receipt_hash == receipt.receipt_hash

    # Verify attempt record was PREPARED
    attempt_path = (
        tmp_path / "authority" / "transitions" / "attempt_attempt-switch-crash-before-cas.json"
    )
    attempt_record = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt_record["status"] == "PREPARED"

    # Restore un-faulted writer and replay exact same attempt
    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", real_write_bytes_locked)
    replay_result = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-crash-before-cas",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-crash-1",
        successor_goal_id="goal-succ-1",
        successor_thread_id="thread-succ-1",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    assert replay_result["status"] == "SWITCHED"
    assert replay_result["predecessor_receipt_hash"] == receipt.receipt_hash

    # Physical receipt was updated to temporary receipt
    current_after = _load_receipt_at(path, now=NOW)
    assert current_after.receipt_hash == replay_result["temporary_receipt_hash"]

    # Journal finalized to COMMITTED / ACTIVE
    final_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert final_attempt["status"] == "COMMITTED"
    op_path = (
        tmp_path / "authority" / "transitions" / f"op_{replay_result['switch_operation_id']}.json"
    )
    final_op = json.loads(op_path.read_text(encoding="utf-8"))
    assert final_op["status"] == "ACTIVE"


def test_switch_crash_after_cas_replay_succeeds_without_duplicate_cas(tmp_path, monkeypatch):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-crash-2", goal_id="goal-crash-2")

    real_write_transition_file = standing_grant_store._write_transition_file
    transition_writes = 0

    def faulty_write_transition_file(p, payload):
        nonlocal transition_writes
        transition_writes += 1
        # First write is op_record PREPARED, second is attempt_record PREPARED.
        # Crash on third write (which is op_record ACTIVE after CAS).
        if transition_writes == 3:
            raise RuntimeError("SIMULATED_CRASH_AFTER_SWITCH_CAS")
        real_write_transition_file(p, payload)

    monkeypatch.setattr(
        standing_grant_store, "_write_transition_file", faulty_write_transition_file
    )

    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_AFTER_SWITCH_CAS"):
        _switch_task_card_authority_at(
            path,
            attempt_key="attempt-switch-crash-after-cas",
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-crash-2",
            successor_goal_id="goal-succ-2",
            successor_thread_id="thread-succ-2",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )

    # Physical receipt on disk has already been updated to temporary receipt
    temp_receipt = _load_receipt_at(path, now=NOW)
    assert temp_receipt.receipt_hash != receipt.receipt_hash
    assert temp_receipt.context.goal_id == "goal-succ-2"

    # Attempt record is still in PREPARED state
    attempt_path = (
        tmp_path / "authority" / "transitions" / "attempt_attempt-switch-crash-after-cas.json"
    )
    attempt_record = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt_record["status"] == "PREPARED"

    # Replay with un-faulted transition writer
    monkeypatch.setattr(standing_grant_store, "_write_transition_file", real_write_transition_file)

    # Track CAS writes during replay: should be 0 because CAS already took effect
    cas_writes_during_replay = 0
    real_write_bytes_locked = standing_grant_store._write_bytes_locked

    def counting_write_bytes_locked(*args, **kwargs):
        nonlocal cas_writes_during_replay
        cas_writes_during_replay += 1
        return real_write_bytes_locked(*args, **kwargs)

    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", counting_write_bytes_locked)

    replay_result = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-crash-after-cas",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-crash-2",
        successor_goal_id="goal-succ-2",
        successor_thread_id="thread-succ-2",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    assert replay_result["status"] == "SWITCHED"
    assert replay_result["temporary_receipt_hash"] == temp_receipt.receipt_hash
    assert cas_writes_during_replay == 0  # No redundant CAS mutation

    # Transition records finalized
    final_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert final_attempt["status"] == "COMMITTED"
    op_path = (
        tmp_path / "authority" / "transitions" / f"op_{replay_result['switch_operation_id']}.json"
    )
    final_op = json.loads(op_path.read_text(encoding="utf-8"))
    assert final_op["status"] == "ACTIVE"


def test_switch_prepared_foreign_current_fails_closed_no_mutation(tmp_path):
    receipt, path = _make_receipt(
        tmp_path, grant_id="grant-orig-foreign", goal_id="goal-orig-foreign"
    )

    # Initiate a switch that is interrupted after PREPARED
    transitions_dir = tmp_path / "authority" / "transitions"

    attempt_key = "attempt-foreign-switch"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"
    op_id = "switch_foreign_123"
    op_path = transitions_dir / f"op_{op_id}.json"

    request_payload = {
        "operation": "SWITCH",
        "attempt_key": attempt_key,
        "expected_current_receipt_hash": receipt.receipt_hash,
        "expected_current_goal_id": "goal-orig-foreign",
        "successor_goal_id": "goal-temp-foreign",
        "successor_thread_id": "thread-temp-foreign",
        "ttl_minutes": 15,
    }
    request_hash = standing_grant_store.canonical_autonomy_hash(request_payload)

    temp_context = StandingGrantContext.issue(
        owner_id=receipt.context.owner_id,
        coordinator_id=receipt.context.coordinator_id,
        repository=receipt.context.repository,
        thread_id="thread-temp-foreign",
        goal_id="goal-temp-foreign",
        allowed_actions=(
            AutonomyActionClass.TASK_CARD_COMMIT,
            AutonomyActionClass.TASK_CARD_CREATE,
        ),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    temp_receipt = StandingGrantReceipt.issue(
        grant_id="grant-temp-foreign",
        context=temp_context,
        supersedes_grant_hash=receipt.receipt_hash,
    )

    result_payload = {
        "schema": "nexus.task_card_authority_switch.v1",
        "status": "SWITCHED",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "predecessor_receipt_hash": receipt.receipt_hash,
        "predecessor_goal_id": "goal-orig-foreign",
        "temporary_grant_id": temp_receipt.grant_id,
        "temporary_receipt_hash": temp_receipt.receipt_hash,
        "temporary_goal_id": "goal-temp-foreign",
        "temporary_thread_id": "thread-temp-foreign",
        "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "expires_at": temp_context.expires_at.isoformat(),
        "owner_confirmation": True,
    }

    op_record = {
        "schema": "nexus.task_card_authority_switch_record.v1",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "status": "PREPARED",
        "predecessor_receipt": receipt.model_dump(mode="json"),
        "predecessor_receipt_hash": receipt.receipt_hash,
        "predecessor_goal_id": "goal-orig-foreign",
        "temporary_receipt": temp_receipt.model_dump(mode="json"),
        "temporary_receipt_hash": temp_receipt.receipt_hash,
        "temporary_goal_id": "goal-temp-foreign",
        "temporary_thread_id": "thread-temp-foreign",
        "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "created_at": NOW.isoformat(),
        "expires_at": temp_context.expires_at.isoformat(),
        "restored_at": None,
        "restored_receipt_hash": None,
    }
    standing_grant_store._write_transition_file(op_path, op_record)

    attempt_record = {
        "schema": "nexus.task_card_authority_transition_attempt.v1",
        "attempt_key": attempt_key,
        "operation_type": "SWITCH",
        "status": "PREPARED",
        "switch_operation_id": op_id,
        "request": request_payload,
        "request_hash": request_hash,
        "predecessor_receipt_hash": receipt.receipt_hash,
        "intended_successor_receipt_hash": temp_receipt.receipt_hash,
        "result": result_payload,
        "created_at": NOW.isoformat(),
    }
    standing_grant_store._write_transition_file(attempt_path, attempt_record)

    # Now replace the physical receipt on disk with an unrelated foreign receipt
    foreign_context = _make_context(goal_id="goal-foreign-unrelated")
    foreign_receipt = StandingGrantReceipt.issue(
        grant_id="grant-foreign-unrelated",
        context=foreign_context,
        supersedes_grant_hash=receipt.receipt_hash,
    )
    standing_grant_store._write_bytes_locked(
        standing_grant_store._canonical_json(foreign_receipt.model_dump(mode="json")),
        foreign_receipt.supersedes_grant_hash,
        path,
        receipt.receipt_hash,
    )
    foreign_bytes_before = path.read_bytes()

    # Replaying the PREPARED attempt when disk has a foreign receipt must fail closed without mutating disk
    with pytest.raises(StandingGrantReceiptError, match="CURRENT_RECEIPT_HASH_MISMATCH"):
        _switch_task_card_authority_at(
            path,
            attempt_key=attempt_key,
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-orig-foreign",
            successor_goal_id="goal-temp-foreign",
            successor_thread_id="thread-temp-foreign",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )

    # Zero mutation on foreign receipt
    assert path.read_bytes() == foreign_bytes_before


def test_restore_crash_before_cas_replay_succeeds(tmp_path, monkeypatch):
    receipt, path = _make_receipt(
        tmp_path, grant_id="grant-pred-rcrash", goal_id="goal-pred-rcrash"
    )
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-for-restore-crash1",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred-rcrash",
        successor_goal_id="goal-temp-rcrash",
        successor_thread_id="thread-temp-rcrash",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    real_write_bytes_locked = standing_grant_store._write_bytes_locked

    def faulty_write_bytes_locked(*args, **kwargs):
        raise RuntimeError("SIMULATED_CRASH_BEFORE_RESTORE_CAS")

    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", faulty_write_bytes_locked)

    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_BEFORE_RESTORE_CAS"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-restore-crash-before-cas",
            switch_operation_id=op_id,
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=True,
            now=NOW,
        )

    # Physical receipt is still temporary receipt
    current = _load_receipt_at(path, now=NOW)
    assert current.receipt_hash == temp_hash

    # Restore attempt record is PREPARED
    attempt_path = (
        tmp_path / "authority" / "transitions" / "attempt_attempt-restore-crash-before-cas.json"
    )
    attempt_record = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt_record["status"] == "PREPARED"

    # Replay with un-faulted writer
    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", real_write_bytes_locked)
    replay_result = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-crash-before-cas",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW,
    )
    assert replay_result["status"] == "RESTORED"
    assert replay_result["restored_goal_id"] == "goal-pred-rcrash"

    # Physical receipt is now restored
    current_after = _load_receipt_at(path, now=NOW)
    assert current_after.receipt_hash == replay_result["restored_receipt_hash"]

    # Journal finalized
    final_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert final_attempt["status"] == "COMMITTED"
    op_path = tmp_path / "authority" / "transitions" / f"op_{op_id}.json"
    final_op = json.loads(op_path.read_text(encoding="utf-8"))
    assert final_op["status"] == "RESTORED"


def test_restore_crash_after_cas_replay_succeeds_without_duplicate_cas(tmp_path, monkeypatch):
    receipt, path = _make_receipt(
        tmp_path, grant_id="grant-pred-rcrash2", goal_id="goal-pred-rcrash2"
    )
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-for-restore-crash2",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred-rcrash2",
        successor_goal_id="goal-temp-rcrash2",
        successor_thread_id="thread-temp-rcrash2",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    real_write_transition_file = standing_grant_store._write_transition_file
    writes = 0

    def faulty_write_transition_file(p, payload):
        nonlocal writes
        writes += 1
        # First write is attempt_record PREPARED.
        # Crash on second write (op_record RESTORED after CAS).
        if writes == 2:
            raise RuntimeError("SIMULATED_CRASH_AFTER_RESTORE_CAS")
        real_write_transition_file(p, payload)

    monkeypatch.setattr(
        standing_grant_store, "_write_transition_file", faulty_write_transition_file
    )

    with pytest.raises(RuntimeError, match="SIMULATED_CRASH_AFTER_RESTORE_CAS"):
        _restore_task_card_authority_at(
            path,
            attempt_key="attempt-restore-crash-after-cas",
            switch_operation_id=op_id,
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=True,
            now=NOW,
        )

    # Physical receipt on disk has already been updated to restored receipt
    restored_receipt = _load_receipt_at(path, now=NOW)
    assert restored_receipt.receipt_hash != temp_hash
    assert restored_receipt.context.goal_id == "goal-pred-rcrash2"

    # Attempt record is still in PREPARED state
    attempt_path = (
        tmp_path / "authority" / "transitions" / "attempt_attempt-restore-crash-after-cas.json"
    )
    attempt_record = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert attempt_record["status"] == "PREPARED"

    # Replay with un-faulted transition writer
    monkeypatch.setattr(standing_grant_store, "_write_transition_file", real_write_transition_file)

    # Track CAS writes during replay: should be 0 because CAS already completed
    cas_writes_during_replay = 0
    real_write_bytes_locked = standing_grant_store._write_bytes_locked

    def counting_write_bytes_locked(*args, **kwargs):
        nonlocal cas_writes_during_replay
        cas_writes_during_replay += 1
        return real_write_bytes_locked(*args, **kwargs)

    monkeypatch.setattr(standing_grant_store, "_write_bytes_locked", counting_write_bytes_locked)

    replay_result = _restore_task_card_authority_at(
        path,
        attempt_key="attempt-restore-crash-after-cas",
        switch_operation_id=op_id,
        expected_temporary_receipt_hash=temp_hash,
        owner_confirmation=True,
        now=NOW,
    )
    assert replay_result["status"] == "RESTORED"
    assert replay_result["restored_receipt_hash"] == restored_receipt.receipt_hash
    assert cas_writes_during_replay == 0  # No duplicate CAS

    # Finalized transition records
    final_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    assert final_attempt["status"] == "COMMITTED"
    op_path = tmp_path / "authority" / "transitions" / f"op_{op_id}.json"
    final_op = json.loads(op_path.read_text(encoding="utf-8"))
    assert final_op["status"] == "RESTORED"


def test_restore_prepared_foreign_current_fails_closed_no_mutation(tmp_path):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-pred-rf", goal_id="goal-pred-rf")
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-switch-for-restore-foreign",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-pred-rf",
        successor_goal_id="goal-temp-rf",
        successor_thread_id="thread-temp-rf",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]

    # Craft PREPARED restore attempt
    attempt_key = "attempt-foreign-restore"
    transitions_dir = tmp_path / "authority" / "transitions"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"

    request_payload = {
        "operation": "RESTORE",
        "attempt_key": attempt_key,
        "switch_operation_id": op_id,
        "expected_temporary_receipt_hash": temp_hash,
    }
    request_hash = standing_grant_store.canonical_autonomy_hash(request_payload)

    restored_receipt = StandingGrantReceipt.issue(
        grant_id="grant-pred-rf-restored-foreign",
        context=receipt.context,
        supersedes_grant_hash=temp_hash,
    )

    result_payload = {
        "schema": "nexus.task_card_authority_restore.v1",
        "status": "RESTORED",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "restored_grant_id": restored_receipt.grant_id,
        "restored_receipt_hash": restored_receipt.receipt_hash,
        "restored_goal_id": "goal-pred-rf",
        "restored_thread_id": "thread-pred-rf",
        "restored_allowed_actions": [a.value for a in receipt.context.allowed_actions],
        "temporary_receipt_hash": temp_hash,
        "owner_confirmation": True,
    }

    attempt_record = {
        "schema": "nexus.task_card_authority_transition_attempt.v1",
        "attempt_key": attempt_key,
        "operation_type": "RESTORE",
        "status": "PREPARED",
        "switch_operation_id": op_id,
        "request": request_payload,
        "request_hash": request_hash,
        "expected_temporary_receipt_hash": temp_hash,
        "intended_restored_receipt": restored_receipt.model_dump(mode="json"),
        "intended_restored_receipt_hash": restored_receipt.receipt_hash,
        "result": result_payload,
        "created_at": NOW.isoformat(),
    }
    standing_grant_store._write_transition_file(attempt_path, attempt_record)

    # Overwrite physical receipt with unrelated foreign receipt
    foreign_context = _make_context(goal_id="goal-restore-foreign-unrelated")
    foreign_receipt = StandingGrantReceipt.issue(
        grant_id="grant-restore-foreign-unrelated",
        context=foreign_context,
        supersedes_grant_hash=temp_hash,
    )
    standing_grant_store._write_bytes_locked(
        standing_grant_store._canonical_json(foreign_receipt.model_dump(mode="json")),
        foreign_receipt.supersedes_grant_hash,
        path,
        temp_hash,
    )
    foreign_bytes_before = path.read_bytes()

    # Replaying PREPARED restore on foreign receipt fails closed without mutation
    with pytest.raises(StandingGrantReceiptError, match="CURRENT_RECEIPT_HASH_MISMATCH"):
        _restore_task_card_authority_at(
            path,
            attempt_key=attempt_key,
            switch_operation_id=op_id,
            expected_temporary_receipt_hash=temp_hash,
            owner_confirmation=True,
            now=NOW,
        )

    assert path.read_bytes() == foreign_bytes_before


def test_transition_files_contain_valid_record_hash(tmp_path):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-rh-test", goal_id="goal-rh-test")
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-rh-switch",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-rh-test",
        successor_goal_id="goal-rh-succ",
        successor_thread_id="thread-rh-succ",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    transitions_dir = tmp_path / "authority" / "transitions"
    attempt_path = transitions_dir / "attempt_attempt-rh-switch.json"
    op_path = transitions_dir / f"op_{switched['switch_operation_id']}.json"

    attempt_data = json.loads(attempt_path.read_text(encoding="utf-8"))
    op_data = json.loads(op_path.read_text(encoding="utf-8"))

    assert "record_hash" in attempt_data
    assert "record_hash" in op_data
    assert (
        standing_grant_store.canonical_autonomy_hash({
            k: v for k, v in attempt_data.items() if k != "record_hash"
        })
        == attempt_data["record_hash"]
    )
    assert (
        standing_grant_store.canonical_autonomy_hash({
            k: v for k, v in op_data.items() if k != "record_hash"
        })
        == op_data["record_hash"]
    )


def test_switch_journal_tamper_fails_closed_zero_mutation(tmp_path):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-tamper-sw", goal_id="goal-tamper-sw")
    transitions_dir = tmp_path / "authority" / "transitions"
    attempt_key = "attempt-tamper-sw"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"
    op_id = "switch_tamper_123"
    op_path = transitions_dir / f"op_{op_id}.json"

    # Set up a PREPARED switch attempt
    switched_sim = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-seed-sw",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-tamper-sw",
        successor_goal_id="goal-seed-succ",
        successor_thread_id="thread-seed-succ",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    # Restore back to original so disk is at receipt.receipt_hash
    _restore_task_card_authority_at(
        path,
        attempt_key="attempt-seed-rest",
        switch_operation_id=switched_sim["switch_operation_id"],
        expected_temporary_receipt_hash=switched_sim["temporary_receipt_hash"],
        owner_confirmation=True,
        now=NOW,
    )
    current_orig = _load_receipt_at(path, now=NOW)
    disk_bytes_before = path.read_bytes()

    # Create PREPARED records for attempt-tamper-sw
    temp_context = StandingGrantContext.issue(
        owner_id=receipt.context.owner_id,
        coordinator_id=receipt.context.coordinator_id,
        repository=receipt.context.repository,
        thread_id="thread-tamper-succ",
        goal_id="goal-tamper-succ",
        allowed_actions=(
            AutonomyActionClass.TASK_CARD_COMMIT,
            AutonomyActionClass.TASK_CARD_CREATE,
        ),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    temp_receipt = StandingGrantReceipt.issue(
        grant_id="grant-tamper-temp",
        context=temp_context,
        supersedes_grant_hash=current_orig.receipt_hash,
    )

    request_payload = {
        "operation": "SWITCH",
        "attempt_key": attempt_key,
        "expected_current_receipt_hash": current_orig.receipt_hash,
        "expected_current_goal_id": current_orig.context.goal_id,
        "successor_goal_id": "goal-tamper-succ",
        "successor_thread_id": "thread-tamper-succ",
        "ttl_minutes": 15,
    }
    request_hash = standing_grant_store.canonical_autonomy_hash(request_payload)

    result_payload = {
        "schema": "nexus.task_card_authority_switch.v1",
        "status": "SWITCHED",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "predecessor_receipt_hash": current_orig.receipt_hash,
        "predecessor_goal_id": current_orig.context.goal_id,
        "temporary_grant_id": temp_receipt.grant_id,
        "temporary_receipt_hash": temp_receipt.receipt_hash,
        "temporary_goal_id": "goal-tamper-succ",
        "temporary_thread_id": "thread-tamper-succ",
        "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "expires_at": temp_context.expires_at.isoformat(),
        "owner_confirmation": True,
    }

    base_op_record = {
        "schema": "nexus.task_card_authority_switch_record.v1",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "status": "PREPARED",
        "predecessor_receipt": current_orig.model_dump(mode="json"),
        "predecessor_receipt_hash": current_orig.receipt_hash,
        "predecessor_goal_id": current_orig.context.goal_id,
        "temporary_receipt": temp_receipt.model_dump(mode="json"),
        "temporary_receipt_hash": temp_receipt.receipt_hash,
        "temporary_goal_id": "goal-tamper-succ",
        "temporary_thread_id": "thread-tamper-succ",
        "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "created_at": NOW.isoformat(),
        "expires_at": temp_context.expires_at.isoformat(),
        "restored_at": None,
        "restored_receipt_hash": None,
    }

    base_attempt_record = {
        "schema": "nexus.task_card_authority_transition_attempt.v1",
        "attempt_key": attempt_key,
        "operation_type": "SWITCH",
        "status": "PREPARED",
        "switch_operation_id": op_id,
        "request": request_payload,
        "request_hash": request_hash,
        "predecessor_receipt_hash": current_orig.receipt_hash,
        "intended_successor_receipt_hash": temp_receipt.receipt_hash,
        "result": result_payload,
        "created_at": NOW.isoformat(),
    }

    # Test tampering various fields directly on disk without recomputing record_hash
    tamper_cases = [
        ("op", "predecessor_goal_id", "goal-hacked"),
        ("op", "temporary_receipt_hash", "0" * 64),
        ("op", "status", "COMMITTED"),
        ("op", "record_hash", "f" * 64),
        ("attempt", "intended_successor_receipt_hash", "1" * 64),
        ("attempt", "predecessor_receipt_hash", "2" * 64),
        ("attempt", "status", "COMMITTED"),
        ("attempt", "record_hash", "bad_hash_format"),
    ]

    for target_rec, field, evil_val in tamper_cases:
        standing_grant_store._write_transition_file(op_path, dict(base_op_record))
        standing_grant_store._write_transition_file(attempt_path, dict(base_attempt_record))

        target_file = op_path if target_rec == "op" else attempt_path
        raw_json = json.loads(target_file.read_text(encoding="utf-8"))
        raw_json[field] = evil_val
        target_file.write_text(
            standing_grant_store._canonical_json(raw_json) + "\n", encoding="utf-8"
        )

        with pytest.raises(StandingGrantReceiptError, match="TRANSITION_TAMPERED"):
            _switch_task_card_authority_at(
                path,
                attempt_key=attempt_key,
                expected_current_receipt_hash=current_orig.receipt_hash,
                expected_current_goal_id=current_orig.context.goal_id,
                successor_goal_id="goal-tamper-succ",
                successor_thread_id="thread-tamper-succ",
                ttl_minutes=15,
                owner_confirmation=True,
                now=NOW,
            )
        assert path.read_bytes() == disk_bytes_before


def test_restore_journal_tamper_fails_closed_zero_mutation(tmp_path):
    receipt, path = _make_receipt(
        tmp_path, grant_id="grant-tamper-rest", goal_id="goal-tamper-rest"
    )
    switched = _switch_task_card_authority_at(
        path,
        attempt_key="attempt-sw-for-tamper-rest",
        expected_current_receipt_hash=receipt.receipt_hash,
        expected_current_goal_id="goal-tamper-rest",
        successor_goal_id="goal-temp-rest",
        successor_thread_id="thread-temp-rest",
        ttl_minutes=15,
        owner_confirmation=True,
        now=NOW,
    )
    temp_hash = switched["temporary_receipt_hash"]
    op_id = switched["switch_operation_id"]
    disk_bytes_before = path.read_bytes()

    transitions_dir = tmp_path / "authority" / "transitions"
    attempt_key = "attempt-tamper-rest"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"

    # Craft PREPARED restore attempt
    restored_receipt = StandingGrantReceipt.issue(
        grant_id=f"{receipt.grant_id}-restored-tamper",
        context=receipt.context,
        supersedes_grant_hash=temp_hash,
    )
    request_payload = {
        "operation": "RESTORE",
        "attempt_key": attempt_key,
        "switch_operation_id": op_id,
        "expected_temporary_receipt_hash": temp_hash,
    }
    request_hash = standing_grant_store.canonical_autonomy_hash(request_payload)

    result_payload = {
        "schema": "nexus.task_card_authority_restore.v1",
        "status": "RESTORED",
        "switch_operation_id": op_id,
        "attempt_key": attempt_key,
        "restored_grant_id": restored_receipt.grant_id,
        "restored_receipt_hash": restored_receipt.receipt_hash,
        "restored_goal_id": "goal-tamper-rest",
        "restored_thread_id": "thread-tamper-rest",
        "restored_allowed_actions": [a.value for a in receipt.context.allowed_actions],
        "temporary_receipt_hash": temp_hash,
        "owner_confirmation": True,
    }

    base_attempt_record = {
        "schema": "nexus.task_card_authority_transition_attempt.v1",
        "attempt_key": attempt_key,
        "operation_type": "RESTORE",
        "status": "PREPARED",
        "switch_operation_id": op_id,
        "request": request_payload,
        "request_hash": request_hash,
        "expected_temporary_receipt_hash": temp_hash,
        "intended_restored_receipt": restored_receipt.model_dump(mode="json"),
        "intended_restored_receipt_hash": restored_receipt.receipt_hash,
        "result": result_payload,
        "created_at": NOW.isoformat(),
    }

    tamper_cases = [
        ("intended_restored_receipt_hash", "3" * 64),
        ("expected_temporary_receipt_hash", "4" * 64),
        ("status", "COMMITTED"),
        ("record_hash", "0" * 64),
    ]

    for field, evil_val in tamper_cases:
        standing_grant_store._write_transition_file(attempt_path, dict(base_attempt_record))
        raw_json = json.loads(attempt_path.read_text(encoding="utf-8"))
        raw_json[field] = evil_val
        attempt_path.write_text(
            standing_grant_store._canonical_json(raw_json) + "\n", encoding="utf-8"
        )

        with pytest.raises(StandingGrantReceiptError, match="TRANSITION_TAMPERED"):
            _restore_task_card_authority_at(
                path,
                attempt_key=attempt_key,
                switch_operation_id=op_id,
                expected_temporary_receipt_hash=temp_hash,
                owner_confirmation=True,
                now=NOW,
            )
        assert path.read_bytes() == disk_bytes_before


def test_cross_record_substitution_fails_closed_zero_mutation(tmp_path):
    receipt, path = _make_receipt(tmp_path, grant_id="grant-xrec", goal_id="goal-xrec")
    transitions_dir = tmp_path / "authority" / "transitions"

    # Case 1: PREPARED switch attempt references an op_record with mismatched switch_operation_id
    attempt_key = "attempt-xrec-switch"
    attempt_path = transitions_dir / f"attempt_{attempt_key}.json"
    op_id = "switch_xrec_1"
    op_path = transitions_dir / f"op_{op_id}.json"

    temp_context = StandingGrantContext.issue(
        owner_id=receipt.context.owner_id,
        coordinator_id=receipt.context.coordinator_id,
        repository=receipt.context.repository,
        thread_id="thread-xrec-succ",
        goal_id="goal-xrec-succ",
        allowed_actions=(
            AutonomyActionClass.TASK_CARD_COMMIT,
            AutonomyActionClass.TASK_CARD_CREATE,
        ),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    temp_receipt = StandingGrantReceipt.issue(
        grant_id="grant-xrec-temp",
        context=temp_context,
        supersedes_grant_hash=receipt.receipt_hash,
    )
    request_payload = {
        "operation": "SWITCH",
        "attempt_key": attempt_key,
        "expected_current_receipt_hash": receipt.receipt_hash,
        "expected_current_goal_id": "goal-xrec",
        "successor_goal_id": "goal-xrec-succ",
        "successor_thread_id": "thread-xrec-succ",
        "ttl_minutes": 15,
    }
    request_hash = standing_grant_store.canonical_autonomy_hash(request_payload)

    # Write op_record with internal switch_operation_id="switch_foreign_id"
    op_record = {
        "schema": "nexus.task_card_authority_switch_record.v1",
        "switch_operation_id": "switch_foreign_id",  # Mismatch!
        "attempt_key": attempt_key,
        "status": "PREPARED",
        "predecessor_receipt": receipt.model_dump(mode="json"),
        "predecessor_receipt_hash": receipt.receipt_hash,
        "predecessor_goal_id": "goal-xrec",
        "temporary_receipt": temp_receipt.model_dump(mode="json"),
        "temporary_receipt_hash": temp_receipt.receipt_hash,
        "temporary_goal_id": "goal-xrec-succ",
        "temporary_thread_id": "thread-xrec-succ",
        "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
        "created_at": NOW.isoformat(),
        "expires_at": temp_context.expires_at.isoformat(),
        "restored_at": None,
        "restored_receipt_hash": None,
    }
    standing_grant_store._write_transition_file(op_path, op_record)

    attempt_record = {
        "schema": "nexus.task_card_authority_transition_attempt.v1",
        "attempt_key": attempt_key,
        "operation_type": "SWITCH",
        "status": "PREPARED",
        "switch_operation_id": op_id,
        "request": request_payload,
        "request_hash": request_hash,
        "predecessor_receipt_hash": receipt.receipt_hash,
        "intended_successor_receipt_hash": temp_receipt.receipt_hash,
        "result": {
            "schema": "nexus.task_card_authority_switch.v1",
            "status": "SWITCHED",
            "switch_operation_id": op_id,
            "attempt_key": attempt_key,
            "predecessor_receipt_hash": receipt.receipt_hash,
            "predecessor_goal_id": "goal-xrec",
            "temporary_grant_id": temp_receipt.grant_id,
            "temporary_receipt_hash": temp_receipt.receipt_hash,
            "temporary_goal_id": "goal-xrec-succ",
            "temporary_thread_id": "thread-xrec-succ",
            "allowed_actions": ["TASK_CARD_COMMIT", "TASK_CARD_CREATE"],
            "expires_at": temp_context.expires_at.isoformat(),
            "owner_confirmation": True,
        },
        "created_at": NOW.isoformat(),
    }
    standing_grant_store._write_transition_file(attempt_path, attempt_record)

    disk_bytes_before = path.read_bytes()
    with pytest.raises(StandingGrantReceiptError, match="TRANSITION_RECORD_INCONSISTENT"):
        _switch_task_card_authority_at(
            path,
            attempt_key=attempt_key,
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-xrec",
            successor_goal_id="goal-xrec-succ",
            successor_thread_id="thread-xrec-succ",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )
    assert path.read_bytes() == disk_bytes_before

    # Case 2: Op record with mismatched temporary_receipt_hash vs internal temporary_receipt
    op_record["switch_operation_id"] = op_id
    op_record["temporary_receipt_hash"] = (
        "9" * 64
    )  # Recomputed record_hash, but hash mismatch internally
    standing_grant_store._write_transition_file(op_path, op_record)

    with pytest.raises(StandingGrantReceiptError, match="TRANSITION_RECORD_INCONSISTENT"):
        _switch_task_card_authority_at(
            path,
            attempt_key=attempt_key,
            expected_current_receipt_hash=receipt.receipt_hash,
            expected_current_goal_id="goal-xrec",
            successor_goal_id="goal-xrec-succ",
            successor_thread_id="thread-xrec-succ",
            ttl_minutes=15,
            owner_confirmation=True,
            now=NOW,
        )
    assert path.read_bytes() == disk_bytes_before
