import json
from datetime import datetime, timedelta, timezone

import pytest

import nexus.orchestrator.state_owner_transition_authority as mod
from nexus.contracts.state_owner_transition import WriterTransitionRequest


def req():
    raw = {
        "schema": "nexus.state_owner_transition_request.v1",
        "operation": "PREFLIGHT",
        "request_id": "r",
        "transaction_id": "t",
        "idempotency_key": "i",
        "task_id": "task",
        "card_path": "card",
        "card_sha256": "a" * 64,
        "expected_source_head": "1" * 40,
        "expected_source_tree": "b" * 40,
        "accepted_source_receipt": "src",
        "root_id": "root",
        "expected_root_identity": "c" * 64,
        "expected_owner_id": "owner",
        "expected_generation": None,
        "expected_writer_id": "old",
        "expected_manifest_sha256": None,
        "next_generation": 1,
        "next_writer_id": "new",
        "selections": [
            {
                "entry_id": "e",
                "role": "task_state",
                "relative_path": "x.json",
                "expected_sha256": "d" * 64,
                "size": 1,
            }
        ],
        "authority_receipt_id": "auth",
        "authority_receipt_hash": "e" * 64,
        "drain_receipt_id": "drain",
        "drain_receipt_hash": "f" * 64,
        "snapshot_receipt_id": "snap",
        "snapshot_receipt_hash": "0" * 64,
        "rollback_receipt_id": "roll",
        "rollback_receipt_hash": "1" * 64,
        "loaded_writer_plan_id": "plan",
        "loaded_writer_plan_hash": "2" * 64,
    }
    return WriterTransitionRequest.from_mapping(raw)


def source():
    return mod.LoadedSourceIdentity("James3014/Nexus-new", "1" * 40, "b" * 40, "card", "a" * 64)


def receipt(effect, **extra):
    d = {
        "schema": "nexus.writer_transition_authority.v1",
        "receipt_id": "auth",
        "issuer": "James3014",
        "coordinator_id": "primary-codex-coordinator",
        "owner_id": "James3014",
        "repository": "James3014/Nexus-new",
        "goal_id": "goal",
        "thread_id": "thread",
        "grant_id": "grant",
        "grant_receipt_hash": "3" * 64,
        "grant_context_hash": "4" * 64,
        "action": "WRITER_TRANSITION",
        "source_head": "1" * 40,
        "source_tree": "b" * 40,
        "card_path": "card",
        "card_sha256": "a" * 64,
        "authorization_intent_digest": mod._authorization_intent_digest(req()),
        "operation_digest": mod._authorization_intent_digest(req()),
        "root_id": "root",
        "effect_hash": effect,
        "revoked": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    d.update(extra)
    return json.dumps(d).encode()


def setup(monkeypatch, data):
    monkeypatch.setattr(mod, "_mirror_identity", lambda: ("1" * 40, "b" * 40, "e" * 64))
    monkeypatch.setattr(mod, "_git", lambda *args: "b" * 40)
    monkeypatch.setattr(mod.subprocess, "check_call", lambda *args, **kwargs: 0)
    monkeypatch.setattr(mod, "_regular", lambda p: data)


def test_positive_typed_registered_handle(monkeypatch):
    effect = mod._effect_hash(req())
    data = receipt(effect)
    setup(monkeypatch, data)
    value = mod.load_verified_writer_transition_authority(
        request=req(), loaded_source_identity=source()
    )
    assert mod.is_registered_authority(value)


def test_rejects_publication_byte_mismatch(monkeypatch):
    effect = mod._effect_hash(req())
    setup(monkeypatch, receipt(effect))
    data = receipt(effect)
    calls = iter([data, b"different"])
    monkeypatch.setattr(mod, "_regular", lambda p: next(calls))
    with pytest.raises(mod.WriterAuthorityError, match="PUBLICATION_BYTES"):
        mod.load_verified_writer_transition_authority(
            request=req(), loaded_source_identity=source()
        )


def test_rejects_issuer_expiry_and_effect(monkeypatch):
    setup(monkeypatch, receipt("0" * 64, issuer="attacker"))
    with pytest.raises(mod.WriterAuthorityError, match="ISSUER"):
        mod.load_verified_writer_transition_authority(
            request=req(), loaded_source_identity=source()
        )
    setup(monkeypatch, receipt("0" * 64, expires_at="2020-01-01T00:00:00+00:00"))
    with pytest.raises(mod.WriterAuthorityError, match="EXPIRY"):
        mod.load_verified_writer_transition_authority(
            request=req(), loaded_source_identity=source()
        )


def test_rejects_dirty_or_wrong_origin_identity(monkeypatch):
    monkeypatch.setattr(
        mod,
        "_mirror_identity",
        lambda: (_ for _ in ()).throw(
            mod.WriterAuthorityError("AUTHORITY_MIRROR_NOT_FRESH_CLEAN_MAIN")
        ),
    )
    with pytest.raises(mod.WriterAuthorityError, match="FRESH"):
        mod.load_verified_writer_transition_authority(
            request=req(), loaded_source_identity=source()
        )


def test_real_clean_mirror_identity_and_git_blob(tmp_path, monkeypatch):
    import subprocess

    mirror = tmp_path / "mirror"
    mirror.mkdir(mode=0o700)

    def run(*args):
        return subprocess.run(
            args, cwd=mirror, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    run("git", "init", "-b", "main")
    run("git", "config", "user.email", "test@example.invalid")
    run("git", "config", "user.name", "Test")
    tracked = mirror / mod.TRACKED_RELATIVE
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("{}\n")
    run("git", "add", str(mod.TRACKED_RELATIVE))
    run("git", "commit", "-m", "authority")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=mirror, text=True).strip()
    run("git", "remote", "add", "origin", mod.EXPECTED_REMOTE)
    run("git", "update-ref", "refs/remotes/origin/main", head)
    monkeypatch.setattr(mod, "MIRROR_ROOT", mirror)
    monkeypatch.setattr(mod, "_remote_main_head", lambda: head)
    got_head, got_tree, got_blob = mod._mirror_identity()
    assert got_head == head and len(got_tree) == 40 and len(got_blob) == 64


def test_actual_temp_published_receipt_loads_without_reader_mocks(tmp_path, monkeypatch):
    import hashlib
    import subprocess
    from dataclasses import replace

    mirror = tmp_path / "mirror"
    mirror.mkdir(mode=0o700)

    def run(*args):
        return subprocess.run(
            args, cwd=mirror, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

    run("git", "init", "-b", "main")
    run("git", "config", "user.email", "test@example.invalid")
    run("git", "config", "user.name", "Test")
    tracked = mirror / mod.TRACKED_RELATIVE
    tracked.parent.mkdir(parents=True, exist_ok=True)
    tracked.write_text("placeholder\n")
    run("git", "add", str(mod.TRACKED_RELATIVE))
    run("git", "commit", "-m", "source")
    source_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=mirror, text=True
    ).strip()
    source_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=mirror, text=True
    ).strip()
    run("git", "remote", "add", "origin", mod.EXPECTED_REMOTE)
    run("git", "update-ref", "refs/remotes/origin/main", source_head)
    request = replace(
        req(),
        expected_source_head=source_head,
        expected_source_tree=source_tree,
        authority_receipt_hash="0" * 64,
    )
    payload = {
        "schema": "nexus.writer_transition_authority.v1",
        "receipt_id": "auth",
        "issuer": "James3014",
        "coordinator_id": "primary-codex-coordinator",
        "owner_id": "James3014",
        "repository": "James3014/Nexus-new",
        "goal_id": "goal",
        "thread_id": "thread",
        "grant_id": "grant",
        "grant_receipt_hash": "3" * 64,
        "grant_context_hash": "4" * 64,
        "action": "WRITER_TRANSITION",
        "source_head": source_head,
        "source_tree": source_tree,
        "card_path": "card",
        "card_sha256": "a" * 64,
        "authorization_intent_digest": mod._authorization_intent_digest(request),
        "operation_digest": mod._authorization_intent_digest(request),
        "root_id": "root",
        "effect_hash": mod._effect_hash(request),
        "revoked": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    }
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    tracked.write_bytes(data)
    run("git", "add", str(mod.TRACKED_RELATIVE))
    run("git", "commit", "-m", "publish")
    publication_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=mirror, text=True
    ).strip()
    run("git", "update-ref", "refs/remotes/origin/main", publication_head)
    durable = tmp_path / "durable.json"
    durable.write_bytes(data)
    durable.parent.chmod(0o700)
    durable.chmod(0o600)
    monkeypatch.setattr(mod, "MIRROR_ROOT", mirror)
    monkeypatch.setattr(mod, "DURABLE_PATH", durable)
    monkeypatch.setattr(mod, "_remote_main_head", lambda: publication_head)
    final = replace(request, authority_receipt_hash=hashlib.sha256(data).hexdigest())
    value = mod.load_verified_writer_transition_authority(
        request=final,
        loaded_source_identity=mod.LoadedSourceIdentity(
            "James3014/Nexus-new", source_head, source_tree, "card", "a" * 64
        ),
    )
    assert (
        mod.is_registered_authority(value)
        and value.authorization_intent_digest == mod._authorization_intent_digest(final)
        and value.full_request_digest == final.request_digest
    )
    forged = mod.VerifiedWriterTransitionAuthority(
        value.receipt_id,
        value.receipt_hash,
        value.tracked_blob_hash,
        value.issuer,
        value.source_head,
        value.card_sha256,
        object(),
        value.authorization_intent_digest,
        value.process_id,
        value.thread_id,
        value.full_request_digest,
    )
    assert not mod.is_registered_authority(forged)


def test_remote_freshness_transport_changed_missing_unknown(monkeypatch):
    monkeypatch.setattr(
        mod.subprocess, "check_output", lambda *a, **k: "f" * 40 + "\trefs/heads/main\n"
    )
    assert mod._remote_main_head() == "f" * 40

    def missing(*a, **k):
        raise __import__("subprocess").CalledProcessError(2, a[0])

    monkeypatch.setattr(mod.subprocess, "check_output", missing)
    with pytest.raises(mod.WriterAuthorityError, match="FRESHNESS_UNKNOWN"):
        mod._remote_main_head()
    monkeypatch.setattr(
        mod.subprocess,
        "check_output",
        lambda *a, **k: "a" * 40 + "\trefs/heads/main\n" + "b" * 40 + "\trefs/heads/main\n",
    )
    with pytest.raises(mod.WriterAuthorityError, match="REMOTE_MAIN_UNKNOWN"):
        mod._remote_main_head()


def test_indexed_publications_select_distinct_fixed_pairs_through_loader(monkeypatch):
    from dataclasses import replace
    from pathlib import Path

    publications = {
        root_id: mod.AuthorityPublication(
            Path("tasks") / f"authority-{root_id}.json",
            Path(f"/tmp/authority-{root_id}.json"),
        )
        for root_id in ("task", "runtime", "event")
    }
    monkeypatch.setattr(mod, "PUBLICATION_INVENTORY", publications)
    payloads = {}
    for root_id, publication in publications.items():
        request = replace(req(), root_id=root_id)
        effect = mod._effect_hash(request)
        value = json.loads(receipt(effect))
        value.update(
            root_id=root_id,
            authorization_intent_digest=request.authorization_intent_digest,
            operation_digest=request.authorization_intent_digest,
        )
        payloads[root_id] = json.dumps(value).encode()

    monkeypatch.setattr(
        mod,
        "_mirror_identity",
        lambda publication=None: ("1" * 40, "b" * 40, "e" * 64),
    )
    monkeypatch.setattr(mod, "_git", lambda *args: "b" * 40)
    monkeypatch.setattr(mod.subprocess, "check_call", lambda *args, **kwargs: 0)
    current_payload = [b""]
    monkeypatch.setattr(mod, "_regular", lambda _path: current_payload[0])
    for root_id in publications:
        request = replace(req(), root_id=root_id)
        current_payload[0] = payloads[root_id]
        value = mod.load_verified_writer_transition_authority(
            request=request, loaded_source_identity=source()
        )
        assert value.publication_root_id == root_id


def test_unindexed_root_denies_before_publication_read(monkeypatch):
    from dataclasses import replace
    from pathlib import Path

    monkeypatch.setattr(
        mod,
        "PUBLICATION_INVENTORY",
        {"task": mod.AuthorityPublication(Path("task.json"), Path("/tmp/task.json"))},
    )
    monkeypatch.setattr(mod, "_mirror_identity", lambda: pytest.fail("must not read"))
    with pytest.raises(mod.WriterAuthorityError, match="PUBLICATION_NOT_INDEXED"):
        mod.load_verified_writer_transition_authority(
            request=replace(req(), root_id="foreign"), loaded_source_identity=source()
        )


def test_indexed_publication_rejects_source_and_receipt_hash_drift(monkeypatch):
    from dataclasses import replace

    effect = mod._effect_hash(req())
    setup(monkeypatch, receipt(effect))
    with pytest.raises(mod.WriterAuthorityError, match="SOURCE_TREE"):
        mod.load_verified_writer_transition_authority(
            request=req(),
            loaded_source_identity=replace(source(), source_tree="c" * 40),
        )

    setup(monkeypatch, receipt(effect))
    with pytest.raises(mod.WriterAuthorityError, match="BLOB_HASH"):
        mod.load_verified_writer_transition_authority(
            request=replace(req(), authority_receipt_hash="0" * 64),
            loaded_source_identity=source(),
        )


def test_single_publication_compatibility_accepts_any_bound_root_id(monkeypatch):
    from dataclasses import replace

    request = replace(req(), root_id="legacy-root-1")
    value = json.loads(receipt(mod._effect_hash(request)))
    value.update(
        root_id=request.root_id,
        authorization_intent_digest=request.authorization_intent_digest,
        operation_digest=request.authorization_intent_digest,
    )
    setup(monkeypatch, json.dumps(value).encode())
    loaded = mod.load_verified_writer_transition_authority(
        request=request, loaded_source_identity=source()
    )
    assert loaded.publication_root_id == request.root_id
