import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

import scripts.ops.mcp_gateway_durable as manager
from nexus.contracts.state_owner_transition import WriterTransitionRequest
from nexus.orchestrator.unified_mcp_gateway import LoadedWriterCollectorPlan, UnifiedMCPGateway
from nexus.orchestrator.writer_quiescence import (
    WriterIdentity,
    WriterRegistry,
    current_process_start_identity,
)
from tests.contracts.test_state_owner_transition import _raw


def receipt_bytes(tmp_path):
    process_start = current_process_start_identity()
    thread_id = str(threading.get_ident())
    reg = WriterRegistry(
        source_identity="source@tree",
        process_start_identity=process_start,
        server_identity="srv",
    )
    ident = WriterIdentity(
        tmp_path, "task_state", "source@tree", process_start, thread_id, 7, "writer"
    )
    reg.register(
        ident, snapshot=lambda: b"state", process_state=lambda: "alive", pending=lambda: ()
    )
    with reg.acquire(
        root=ident.root,
        role=ident.role,
        writer_id=ident.writer_id,
        generation=7,
        thread_id=thread_id,
    ):
        pass
    hold = reg.begin_hold([ident.root], cohort_id="cohort")
    hold.acknowledge(ident.writer_id, root=ident.root, role=ident.role, generation=7)
    return hold.finalize().to_bytes()


def test_core_generated_durable_receipt_projection(tmp_path, monkeypatch):
    path = tmp_path / "evidence.json"
    path.write_bytes(receipt_bytes(tmp_path))
    monkeypatch.setattr(manager, "GATEWAY_EVIDENCE_STORE", path)
    monkeypatch.setattr(manager, "_safe_store_path", lambda value: path)
    observed = manager.observe_gateway_quiescence()
    assert observed["lifecycle_state"] == "UNKNOWN"
    assert observed["evidence_sha256"] == ""
    assert observed["unknown_reason"] == "CURRENT_PROVENANCE_REQUIRES_F_REGISTRY_BRIDGE"
    historical = observed["historical_projection"]
    assert historical["observations"] and historical["leases"]
    assert observed["assist_state"] == ""
    assert observed["reacquisition_receipt"] == ""
    assert all("|" in key for key in historical["snapshot_hashes"])


def test_corrupt_receipt_denied(tmp_path, monkeypatch):
    path = tmp_path / "evidence.json"
    path.write_bytes(receipt_bytes(tmp_path) + b"tamper")
    monkeypatch.setattr(manager, "_safe_store_path", lambda value: path)
    with pytest.raises(manager.GatewayContractError):
        manager.observe_gateway_quiescence()


def test_restarted_manager_keeps_well_formed_receipt_historical(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_bytes(receipt_bytes(tmp_path))
    script = """import json, os, sys
from pathlib import Path
import scripts.ops.mcp_gateway_durable as manager
manager._safe_store_path = lambda value: Path(sys.argv[1])
print(json.dumps({"pid": os.getpid(), "observation": manager.observe_gateway_quiescence()}))
"""
    process = subprocess.run(
        [sys.executable, "-B", "-c", script, str(path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    result = json.loads(process.stdout)
    assert result["pid"] != os.getpid()
    assert result["observation"]["lifecycle_state"] == "UNKNOWN"
    assert result["observation"]["historical_projection"]["receipt_sha256"]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _physical_fixture(tmp_path, monkeypatch):
    """Real loaded service, registry and public grant; only remote transport is stubbed."""
    from nexus.contracts.autonomy_goal import (
        AutonomyActionClass,
        RepositoryIdentity,
        StandingGrantContext,
    )
    from nexus.orchestrator import standing_grant_store as grants
    from nexus.orchestrator import state_owner_transition_authority as authority
    from nexus.orchestrator import state_owner_transition_service as transition
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    root = tmp_path / "state"
    root.mkdir()
    artifact = root / "state.json"
    artifact.write_bytes(b'{"task_id":"state","status":"DIRECT_COMPLETED"}')
    source = tmp_path / "source"
    (source / "tasks").mkdir(parents=True)
    card_bytes = (
        "# Isolated integration fixture\n```writer-transition-scope\n"
        + json.dumps({
            "schema": "nexus.writer_transition_card_scope.v1",
            "mode": "LIVE_SAME_OWNER",
            "task_id": "task",
            "repository": "James3014/Nexus-new",
            "root_ids": ["root"],
            "operations": ["APPLY", "RECONCILE"],
        })
        + "\n```\n"
    ).encode()
    (source / "tasks/card.md").write_bytes(card_bytes)

    def git(root, *args):
        return subprocess.check_output(
            ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Fixture")
    git(source, "config", "user.email", "fixture@example.invalid")
    git(source, "add", ".")
    git(source, "commit", "-m", "source")
    head, tree = git(source, "rev-parse", "HEAD"), git(source, "rev-parse", "HEAD^{tree}")
    loaded = authority.LoadedSourceIdentity(
        "James3014/Nexus-new", head, tree, "tasks/card.md", _sha(card_bytes)
    )
    service = SelfHostedTaskService(state_dir=root, auto_reconcile=False)
    service.loaded_source_identity = loaded
    service.source_root = source
    service.writer_roots = {"root": root}
    service.writer_generation = 0
    service.writer_id = "old"
    gateway = UnifiedMCPGateway(service=service)
    registry = gateway._writer_quiescence_registry
    hold = registry.begin_hold([root], cohort_id="cohort")
    hold.acknowledge("old", root=root, role="task_state", generation=0)
    quiescence = registry.persist_finalized(hold)

    def receipt_file(name):
        path = tmp_path / (name + ".json")
        path.write_bytes(json.dumps({"receipt_id": name}, sort_keys=True).encode())
        return path

    accepted = tmp_path / "source-acceptance"
    accepted.write_bytes(b"accepted-source-fixture")
    snapshot, rollback, plan_path = (
        receipt_file(name) for name in ("snapshot", "rollback", "plan")
    )
    raw = _raw()
    raw.update(
        operation="APPLY",
        transaction_id="cohort",
        expected_source_head=head,
        expected_source_tree=tree,
        card_sha256=_sha(card_bytes),
        expected_root_identity=_sha(str(root.resolve()).encode()),
        accepted_source_receipt_hash=_sha(accepted.read_bytes()),
        drain_receipt_id="cohort",
        drain_receipt_hash=_sha(quiescence.to_bytes()),
        snapshot_receipt_id="snapshot",
        snapshot_receipt_hash=_sha(snapshot.read_bytes()),
        rollback_receipt_id="rollback",
        rollback_receipt_hash=_sha(rollback.read_bytes()),
        loaded_writer_plan_id="plan",
        loaded_writer_plan_hash=_sha(plan_path.read_bytes()),
    )
    raw["selections"][0].update(
        expected_sha256=_sha(artifact.read_bytes()), size=artifact.stat().st_size
    )

    # This is the public typed operator writer, relocated to an isolated store.
    monkeypatch.setattr(grants, "DEFAULT_RECEIPT_PATH", tmp_path / "grant" / "receipt.json")
    context = StandingGrantContext.issue(
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
    grant = grants.StandingGrantReceipt.issue(grant_id="grant", context=context)
    grants.write_standing_grant_receipt(grant)
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
        source_head=head,
        source_tree=tree,
        card_path=request.card_path,
        card_sha256=request.card_sha256,
        authorization_intent_digest=request.authorization_intent_digest,
        operation_digest=request.authorization_intent_digest,
        root_id="root",
        effect_hash=authority._effect_hash(request),
        revoked=False,
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    authority_bytes = json.dumps(payload, sort_keys=True).encode()
    mirror = tmp_path / "mirror"
    subprocess.check_call(["git", "clone", "--quiet", str(source), str(mirror)])
    git(mirror, "config", "user.name", "Fixture")
    git(mirror, "config", "user.email", "fixture@example.invalid")
    tracked = mirror / authority.TRACKED_RELATIVE
    tracked.parent.mkdir(parents=True)
    tracked.write_bytes(authority_bytes)
    git(mirror, "add", ".")
    git(mirror, "commit", "-m", "publish fixture authority")
    git(mirror, "remote", "set-url", "origin", authority.EXPECTED_REMOTE)
    git(mirror, "update-ref", "refs/remotes/origin/main", git(mirror, "rev-parse", "HEAD"))
    durable = tmp_path / "authority.json"
    durable.write_bytes(authority_bytes)
    monkeypatch.setattr(authority, "MIRROR_ROOT", mirror)
    monkeypatch.setattr(authority, "DURABLE_PATH", durable)
    # No network: substitute only the remote ref observation, not authority validation.
    monkeypatch.setattr(authority, "_remote_main_head", lambda: git(mirror, "rev-parse", "HEAD"))
    monkeypatch.setattr(transition, "_COLLECTOR_LOADER", None)
    raw["authority_receipt_hash"] = _sha(authority_bytes)
    request = WriterTransitionRequest.from_mapping(raw)
    service.loaded_writer_collector_plan = LoadedWriterCollectorPlan(
        request.request_digest,
        "cohort",
        "root",
        root,
        head,
        tree,
        0,
        "old",
        accepted,
        snapshot,
        rollback,
        plan_path,
        ("state.json",),
    )
    gateway._bind_loaded_writer_collector_plan()
    actual_transition = transition.build_source_owned_transition_service(service)
    return gateway, actual_transition, request, service, hold


def _tree_bytes(root):
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def test_actual_gateway_collector_and_card_a_preflight_are_read_only(tmp_path, monkeypatch):
    from nexus.contracts.state_owner_transition import ReceiptState

    gateway, transition, request, service, hold = _physical_fixture(tmp_path, monkeypatch)
    before = _tree_bytes(tmp_path)
    result = gateway._invoke_writer_transition_operation(transition, request, inspect_only=True)
    assert result.state is ReceiptState.PREFLIGHT_READY, result.error
    assert result.writes_observed is False
    assert _tree_bytes(tmp_path) == before
    evidence = gateway._writer_transition_collector(request)
    assert evidence["generation"] is None
    assert evidence["registered_writer_generation"] == 0
    assert evidence["physical_manifest_present"] is False
    assert (
        gateway._writer_quiescence_registry.load_finalized(hold.cohort_id).drain_state == "DRAINED"
    )
    assert service.writer_quiescence_pending_work() == ()


def test_actual_gateway_missing_plan_and_other_instance_cannot_adopt(tmp_path, monkeypatch):
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
    from nexus.orchestrator.state_owner_transition_service import MissingDependency
    from nexus.orchestrator.writer_quiescence import UnknownWriter

    gateway, transition, request, service, hold = _physical_fixture(tmp_path, monkeypatch)
    other_service = SelfHostedTaskService(state_dir=service.state_dir, auto_reconcile=False)
    other_service.loaded_source_identity = service.loaded_source_identity
    other_service.writer_generation = 0
    other_service.writer_id = "old"
    other = UnifiedMCPGateway(service=other_service)
    before = _tree_bytes(tmp_path)
    with pytest.raises(MissingDependency, match="MISSING_LOADED_WRITER_COLLECTOR_PLAN"):
        other._writer_transition_collector(request)
    other_service.loaded_writer_collector_plan = service.loaded_writer_collector_plan
    with pytest.raises(UnknownWriter, match="MISSING_FINALIZED_WRITER_QUIESCENCE_RECEIPT"):
        other._bind_loaded_writer_collector_plan()
    assert _tree_bytes(tmp_path) == before
    assert (
        gateway._invoke_writer_transition_operation(
            transition, request, inspect_only=True
        ).state.value
        == "PREFLIGHT_READY"
    )


def test_actual_gateway_collector_rejects_snapshot_and_initial_generation_drift(
    tmp_path, monkeypatch
):
    from nexus.events.writer_generation import EventWriterGeneration, install_generation
    from nexus.orchestrator.state_owner_transition_service import MissingDependency

    gateway, transition, request, service, hold = _physical_fixture(tmp_path, monkeypatch)
    artifact = service.state_dir / "state.json"
    original = artifact.read_bytes()
    artifact.write_bytes(original + b" ")
    with pytest.raises(MissingDependency, match="OBSERVATION_CHANGED"):
        gateway._writer_transition_collector(request)
    artifact.write_bytes(original)
    install_generation(service.state_dir, EventWriterGeneration(1, "old"), expected_generation=None)
    with pytest.raises(MissingDependency, match="PARTIAL_GENERATION_STATE"):
        gateway._writer_transition_collector(request)


def test_dispatcher_context_does_not_escape_to_other_threads(tmp_path, monkeypatch):
    from nexus.orchestrator import state_owner_transition_service as module
    from nexus.orchestrator.unified_mcp_gateway import _dispatch_writer_transition_collector

    gateway, transition, request, service, hold = _physical_fixture(tmp_path, monkeypatch)
    assert (
        gateway._invoke_writer_transition_operation(
            transition, request, inspect_only=True
        ).state.value
        == "PREFLIGHT_READY"
    )
    errors = []

    def unrelated_thread():
        try:
            _dispatch_writer_transition_collector(request)
        except module.MissingDependency as exc:
            errors.append(str(exc))

    thread = threading.Thread(target=unrelated_thread)
    thread.start()
    thread.join()
    assert errors == ["MISSING_WRITER_TRANSITION_COLLECTOR_CONTEXT"]
    assert transition.preflight(request).state.value == "DENIED"


def test_original_loader_thread_exit_invalidates_current_drain(tmp_path, monkeypatch):
    from nexus.orchestrator.state_owner_transition_service import MissingDependency

    result = []
    errors = []

    def load_then_exit():
        try:
            result.append(_physical_fixture(tmp_path, monkeypatch))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=load_then_exit)
    thread.start()
    thread.join()
    assert not errors
    gateway, transition, request, service, hold = result[0]
    assert service.writer_quiescence_pending_work() == ()
    assert not thread.is_alive()
    with pytest.raises(MissingDependency, match="PROCESS_OBSERVATION_CHANGED"):
        gateway._writer_transition_collector(request)


def test_duplicate_observation_receipt_fields_are_rejected(tmp_path, monkeypatch):
    gateway, transition, request, service, hold = _physical_fixture(tmp_path, monkeypatch)
    service.loaded_writer_collector_plan.snapshot_receipt.write_bytes(
        b'{"receipt_id":"snapshot","receipt_id":"forged"}'
    )
    with pytest.raises(ValueError, match="duplicate observation field"):
        gateway._writer_transition_collector(request)
