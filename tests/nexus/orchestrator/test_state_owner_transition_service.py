from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.contracts.state_owner_transition import ReceiptState, WriterTransitionRequest
from nexus.events.state_owner_manifest import read_manifest
from nexus.orchestrator import state_owner_transition_service as module
from nexus.orchestrator.state_owner_transition_authority import LoadedSourceIdentity
from nexus.orchestrator.state_owner_transition_service import (
    StateOwnerTransitionService,
    TransitionServiceError,
    _intent_path,
    _record_intent,
)
from tests.contracts.test_state_owner_transition import _raw


def _bind_fixture(tmp_path, monkeypatch):
    """Select isolated durable stores; execute the real loaders and authorizer."""
    import json
    import subprocess

    from nexus.orchestrator import standing_grant_store as grants
    from nexus.orchestrator import state_owner_transition_authority as authority

    monkeypatch.setattr(authority, "MIRROR_ROOT", tmp_path / "mirror")
    monkeypatch.setattr(authority, "DURABLE_PATH", tmp_path / "authority.json")
    monkeypatch.setattr(
        authority,
        "_remote_main_head",
        lambda: subprocess.check_output(
            ["git", "-C", str(tmp_path / "mirror"), "rev-parse", "HEAD"], text=True
        ).strip(),
    )
    monkeypatch.setattr(grants, "DEFAULT_RECEIPT_PATH", tmp_path / "grant" / "standing-grant.json")
    monkeypatch.setattr(
        module,
        "_COLLECTOR_LOADER",
        lambda req: module._VerifiedCollectorEvidence({
            **{
                k: getattr(req, k)
                for k in (
                    "drain_receipt_id",
                    "drain_receipt_hash",
                    "snapshot_receipt_id",
                    "snapshot_receipt_hash",
                    "rollback_receipt_id",
                    "rollback_receipt_hash",
                    "loaded_writer_plan_id",
                    "loaded_writer_plan_hash",
                )
            },
            "request_digest": req.request_digest,
            "drain_state": "DRAINED",
            "root_id": req.root_id,
            "root_identity": req.expected_root_identity,
            "source_head": req.expected_source_head,
            "source_tree": req.expected_source_tree,
            "generation": req.expected_generation,
            "artifact_bytes": {"state.json": b"x"},
            "source_receipt_bytes": b"accepted",
        }),
    )
    raw = json.loads((tmp_path / "request.json").read_text())
    source = LoadedSourceIdentity(
        "James3014/Nexus-new",
        raw["expected_source_head"],
        raw["expected_source_tree"],
        raw["card_path"],
        raw["card_sha256"],
    )
    return tmp_path / "root", tmp_path / "source", source, raw


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    authority_overrides=None,
    grant_overrides=None,
    existing=False,
    card_scope=None,
    source_only=False,
):
    import json
    import subprocess

    from nexus.contracts.autonomy_goal import (
        AutonomyActionClass,
        RepositoryIdentity,
        StandingGrantContext,
    )
    from nexus.orchestrator import state_owner_transition_authority as authority
    from nexus.orchestrator.standing_grant_store import (
        StandingGrantReceipt,
        _write_standing_grant_receipt_at,
    )

    root = tmp_path / "root"
    root.mkdir()
    (root / "state.json").write_bytes(b"x")
    source_root = tmp_path / "source"
    (source_root / "tasks").mkdir(parents=True)
    scope = dict(
        schema="nexus.writer_transition_card_scope.v1",
        mode="LIVE_SAME_OWNER",
        task_id="task",
        repository="James3014/Nexus-new",
        root_ids=["root"],
        operations=["APPLY", "RECONCILE"],
    )
    scope.update(card_scope or {})
    card_bytes = (
        b"# Source-only Card"
        if source_only
        else (
            "# Isolated live fixture card\n```writer-transition-scope\n"
            + json.dumps(scope)
            + "\n```\n"
        ).encode()
    )
    (source_root / "tasks/card.md").write_bytes(card_bytes)

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(source_root), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("add", ".")
    git("commit", "-m", "source")
    raw = _raw()
    raw.update(
        accepted_source_receipt="acceptance://source-proof",
        operation="APPLY",
        expected_root_identity=hashlib.sha256(str(root.resolve()).encode()).hexdigest(),
        card_sha256=hashlib.sha256(card_bytes).hexdigest(),
        accepted_source_receipt_hash=hashlib.sha256(b"accepted").hexdigest(),
        expected_source_head=git("rev-parse", "HEAD"),
        expected_source_tree=git("rev-parse", "HEAD^{tree}"),
    )
    raw["selections"][0].update(expected_sha256=hashlib.sha256(b"x").hexdigest(), size=1)
    if existing:
        from nexus.events.state_owner_manifest import (
            StateOwnerBinding,
            StateOwnerSelection,
            commit_owner_transaction,
            owner_transaction_guard,
        )
        from nexus.events.writer_generation import EventWriterGeneration, install_generation

        token = EventWriterGeneration(1, "old")
        install_generation(root, token, expected_generation=None)
        with owner_transaction_guard(
            StateOwnerBinding("owner", root, 1, "previous"),
            writer_generation=token,
            selections=(StateOwnerSelection("e", "task_state", "state.json"),),
        ) as guard:
            before = commit_owner_transaction(guard)
        raw.update(
            expected_generation=1,
            next_generation=2,
            expected_manifest_sha256=before.manifest_sha256,
        )
    context_args = dict(
        owner_id="James3014",
        coordinator_id="primary-codex-coordinator",
        repository=RepositoryIdentity(
            repository_id="James3014/Nexus-new", canonical_remote=authority.EXPECTED_REMOTE
        ),
        thread_id="thread",
        goal_id="goal",
        allowed_actions=(AutonomyActionClass.RUNTIME_ACTIVATE,),
        issued_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    context_args.update(grant_overrides or {})
    grant = StandingGrantReceipt.issue(
        grant_id="grant", context=StandingGrantContext.issue(**context_args)
    )
    _write_standing_grant_receipt_at(grant, tmp_path / "grant" / "standing-grant.json")
    request = WriterTransitionRequest.from_mapping(raw)
    payload = dict(
        schema="nexus.writer_transition_authority.v1",
        receipt_id="authority",
        issuer="James3014",
        coordinator_id="primary-codex-coordinator",
        owner_id="James3014",
        repository="James3014/Nexus-new",
        goal_id="goal",
        thread_id="thread",
        grant_id="grant",
        grant_receipt_hash=grant.receipt_hash,
        grant_context_hash=grant.context.context_hash,
        action="WRITER_TRANSITION",
        source_head=request.expected_source_head,
        source_tree=request.expected_source_tree,
        card_path=request.card_path,
        card_sha256=request.card_sha256,
        authorization_intent_digest=request.authorization_intent_digest,
        operation_digest=request.authorization_intent_digest,
        root_id=request.root_id,
        effect_hash=authority._effect_hash(request),
        revoked=False,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    payload.update(authority_overrides or {})
    data = json.dumps(payload, sort_keys=True).encode()
    subprocess.check_call(["git", "clone", "--quiet", str(source_root), str(tmp_path / "mirror")])
    source_root = tmp_path / "mirror"
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("remote", "remove", "origin")
    tracked = source_root / authority.TRACKED_RELATIVE
    tracked.parent.mkdir(parents=True)
    tracked.write_bytes(data)
    git("add", ".")
    git("commit", "-m", "publish")
    git("remote", "add", "origin", authority.EXPECTED_REMOTE)
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
    (tmp_path / "authority.json").write_bytes(data)
    raw["authority_receipt_hash"] = hashlib.sha256(data).hexdigest()
    (tmp_path / "request.json").write_text(json.dumps(raw))
    return _bind_fixture(tmp_path, monkeypatch)


def _child(tmp_path, operation):
    import json
    import subprocess
    import sys

    code = """import json, os, sys, pytest
from pathlib import Path
from tests.nexus.orchestrator.test_state_owner_transition_service import _bind_fixture
from nexus.orchestrator.state_owner_transition_service import StateOwnerTransitionService
with pytest.MonkeyPatch.context() as patch:
 root, source_root, source, raw = _bind_fixture(Path(sys.argv[1]), patch)
 service = StateOwnerTransitionService(roots={'root':root}, source=source, source_root=source_root)
 operation = sys.argv[2]
 result = service.apply(raw) if operation == 'apply' else service.reconcile({**raw, 'operation':'RECONCILE'})
 print(json.dumps({'pid':os.getpid(), 'receipt':result.to_dict()}))
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", code, str(tmp_path), operation],
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    result = json.loads(child.stdout)
    assert result["pid"] != os.getpid()
    return result["receipt"]


def test_initial_apply_uses_real_p6c_and_fresh_process_replays(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    first = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).apply(raw)
    assert (
        first.state is ReceiptState.COMMITTED
        and first.before_manifest_present is False
        and first.observed_after_manifest_sha256
    )
    assert read_manifest(root).transaction_id == raw["transaction_id"]
    replay = _child(tmp_path, "apply")
    assert (
        replay["state"] == "COMMITTED"
        and replay["replayed"]
        and replay["observed_after_manifest_sha256"] == first.observed_after_manifest_sha256
    )


def test_reconcile_reads_committed_transaction_without_writes(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    assert (
        StateOwnerTransitionService(roots={"root": root}, source=source, source_root=source_root)
        .apply(raw)
        .state
        is ReceiptState.COMMITTED
    )
    result = _child(tmp_path, "reconcile")
    assert result["state"] == "RECONCILED" and result["writes_observed"] is False


def test_apply_crash_preserves_durable_intent(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        module,
        "commit_owner_transaction",
        lambda _ctx: (_ for _ in ()).throw(RuntimeError("crash")),
    )
    receipt = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).apply(raw)
    assert receipt.state is ReceiptState.UNKNOWN and receipt.writes_observed
    assert module._read_intent(root)["state"] == "INTENT_RECORDED"


def test_conflicting_intent_replay_is_fail_closed(tmp_path):
    request = WriterTransitionRequest.from_mapping(_raw())
    _record_intent(tmp_path, request)
    with pytest.raises(TransitionServiceError, match="CONFLICTING_REPLAY"):
        _record_intent(
            tmp_path,
            WriterTransitionRequest.from_mapping(
                dict(request.to_dict(), idempotency_key="different")
            ),
        )


def test_preflight_is_zero_write_and_operation_scoped(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    result = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    after = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    assert result.state is ReceiptState.PREFLIGHT_READY and before == after
    denied = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).apply({**raw, "operation": "RECONCILE"})
    assert denied.state is ReceiptState.DENIED and not denied.writes_observed


def test_missing_collector_denies_before_any_write(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_COLLECTOR_LOADER", None)
    result = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert (
        result.state is ReceiptState.DENIED
        and "MISSING_WRITER_TRANSITION_COLLECTOR" in result.error
        and not (root / ".nexus").exists()
    )


def test_selected_symlink_is_denied_before_intent(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    (root / "state.json").unlink()
    (root / "state.json").symlink_to(source_root / "tasks/card.md")
    result = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert (
        result.state is ReceiptState.DENIED
        and "SELECTED_FILE_UNSAFE" in result.error
        and not (root / ".nexus").exists()
    )


def test_malformed_intent_does_not_look_absent(tmp_path):
    path = _intent_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(TransitionServiceError, match="INTENT_RECORD_UNREADABLE"):
        module._read_intent(tmp_path)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"expires_at": "2020-01-01T00:00:00+00:00"}, "EXPIRY"),
        ({"authorization_intent_digest": "0" * 64}, "REQUEST_MISMATCH"),
        ({"grant_context_hash": "0" * 64}, "GRANT_SCOPE_MISMATCH"),
        ({"owner_id": "foreign"}, "ISSUER_INVALID"),
        ({"thread_id": "foreign"}, "GRANT_THREAD_MISMATCH"),
    ],
)
def test_real_authority_and_grant_binding_failures(tmp_path, monkeypatch, overrides, reason):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch, authority_overrides=overrides)
    receipt = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert receipt.state is ReceiptState.DENIED and reason in receipt.error
    assert not (root / ".nexus").exists()


def test_expired_real_canonical_grant_denied(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(
        tmp_path,
        monkeypatch,
        grant_overrides={
            "issued_at": datetime.now(timezone.utc) - timedelta(hours=2),
            "expires_at": datetime.now(timezone.utc) - timedelta(hours=1),
        },
    )
    receipt = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert receipt.state is ReceiptState.DENIED and "GRANT_DENIED" in receipt.error
    assert not (root / ".nexus").exists()


def test_generation_cas_race_denied_before_intent(tmp_path, monkeypatch):
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    install_generation(root, EventWriterGeneration(5, "foreign"), expected_generation=None)
    receipt = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).apply(raw)
    assert receipt.state is not ReceiptState.COMMITTED and not _intent_path(root).exists()


def test_reconcile_rejects_changed_request_and_corrupt_record(tmp_path, monkeypatch):
    import json

    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    service = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    )
    assert service.apply(raw).state is ReceiptState.COMMITTED
    result = service.reconcile({**raw, "operation": "RECONCILE", "expected_owner_id": "foreign"})
    assert result.state is ReceiptState.UNKNOWN and "TRANSACTION_MISMATCH" in result.error
    data = json.loads(_intent_path(root).read_text())
    data["request_digest"] = "0" * 64
    _intent_path(root).write_text(json.dumps(data))
    result = service.reconcile({**raw, "operation": "RECONCILE"})
    assert result.state is ReceiptState.UNKNOWN and "INTENT_RECORD_MALFORMED" in result.error


def test_source_receipt_actual_bytes_are_required(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    original = module._COLLECTOR_LOADER

    def corrupt(req):
        evidence = original(req)
        evidence.payload["source_receipt_bytes"] = b"tampered"
        return evidence

    monkeypatch.setattr(module, "_COLLECTOR_LOADER", corrupt)
    result = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert (
        result.state is ReceiptState.DENIED and "SOURCE_ACCEPTANCE_RECEIPT_MISMATCH" in result.error
    )
    assert not (root / ".nexus").exists()


@pytest.mark.parametrize("existing", [False, True])
def test_committed_receipt_tamper_is_unknown(tmp_path, monkeypatch, existing):
    import json

    root, source_root, source, raw = _setup(tmp_path, monkeypatch, existing=existing)
    service = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    )
    result = service.apply(raw)
    assert result.state is ReceiptState.COMMITTED, result.error
    original = json.loads(_intent_path(root).read_text())
    for key in ("grant_hash", "effect_hash", "receipt_digest", "observed_before_manifest_sha256"):
        changed = json.loads(json.dumps(original))
        changed["outcome"][key] = "0" * 64
        _intent_path(root).write_text(json.dumps(changed))
        for operation in ("apply", "reconcile"):
            outcome = _child(tmp_path, operation)
            assert outcome["state"] == "UNKNOWN" and "OUTCOME_BINDING_MISMATCH" in outcome["error"]


def test_higher_generation_denial_replay_and_reconcile(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch, existing=True)
    service = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    )
    denied = service.apply({**raw, "operation": "RECONCILE"})
    assert denied.state is ReceiptState.DENIED
    first = service.apply(raw)
    assert (
        first.state is ReceiptState.COMMITTED
        and first.before_manifest_present
        and first.observed_before_manifest_sha256 == raw["expected_manifest_sha256"]
    ), first.error
    assert _child(tmp_path, "apply")["state"] == "COMMITTED"
    assert _child(tmp_path, "reconcile")["state"] == "RECONCILED"


def test_source_dirty_or_missing_root_denies(tmp_path, monkeypatch):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch)
    result = StateOwnerTransitionService(roots={"root": root}, source=source).preflight(raw)
    assert result.state is ReceiptState.DENIED and "SOURCE_ROOT_REQUIRED" in result.error
    (source_root / "untracked").write_text("dirty")
    result = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert result.state is ReceiptState.DENIED and "SOURCE_DIRTY" in result.error


@pytest.mark.parametrize(
    "options",
    [
        {"source_only": True},
        {"card_scope": {"root_ids": ["foreign"]}},
        {"card_scope": {"task_id": "foreign"}},
        {"card_scope": {"mode": "SOURCE_ONLY"}},
        {"card_scope": {"root_ids": ["root", "root"]}},
        {"card_scope": {"unexpected": True}},
    ],
)
def test_live_card_scope_fail_closed(tmp_path, monkeypatch, options):
    root, source_root, source, raw = _setup(tmp_path, monkeypatch, **options)
    receipt = StateOwnerTransitionService(
        roots={"root": root}, source=source, source_root=source_root
    ).preflight(raw)
    assert receipt.state is ReceiptState.DENIED and "LIVE_CARD_SCOPE_INVALID" in receipt.error
    assert not (root / ".nexus").exists()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("boundary", ["generation", "prepared", "committed"])
def test_child_crash_boundary_reconcile_without_redispatch(
    tmp_path, monkeypatch, existing, boundary
):
    import subprocess
    import sys

    root, _source_root, _source, raw = _setup(tmp_path, monkeypatch, existing=existing)
    code = """import os, sys, pytest
from pathlib import Path
from tests.nexus.orchestrator.test_state_owner_transition_service import _bind_fixture
from nexus.orchestrator import state_owner_transition_service as module
with pytest.MonkeyPatch.context() as patch:
 root, source_root, source, raw = _bind_fixture(Path(sys.argv[1]), patch)
 boundary = sys.argv[2]
 original = module.commit_owner_transaction
 def commit(context):
  if boundary == 'prepared': os._exit(73)
  result = original(context)
  if boundary == 'committed': os._exit(73)
  return result
 patch.setattr(module, 'commit_owner_transaction', commit)
 original_guard = module.owner_transaction_guard
 def guard(*args, **kwargs):
  if boundary == 'generation': os._exit(73)
  return original_guard(*args, **kwargs)
 patch.setattr(module, 'owner_transaction_guard', guard)
 module.StateOwnerTransitionService(roots={'root':root}, source=source, source_root=source_root).apply(raw)
 raise AssertionError('boundary not reached')
"""
    child = subprocess.run(
        [sys.executable, "-B", "-c", code, str(tmp_path), boundary],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert child.returncode == 73, child.stderr
    intent = module._read_intent(root)
    assert intent["state"] == "INTENT_RECORDED"
    assert intent["before_observation"] == {
        "present": existing,
        "manifest_sha256": raw["expected_manifest_sha256"],
    }
    assert intent["phase"] == ("GENERATION_ADVANCED" if boundary == "generation" else "PREPARED")
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = _child(tmp_path, "reconcile")
    assert result["state"] == ("RECONCILED" if boundary == "committed" else "UNKNOWN"), result
    assert not result["writes_observed"]
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert _child(tmp_path, "apply")["state"] == "UNKNOWN"
    assert before == {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
