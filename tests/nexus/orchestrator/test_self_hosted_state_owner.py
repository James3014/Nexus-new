import json
from types import SimpleNamespace

import pytest

from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _service(tmp_path):
    return SelfHostedTaskService(
        state_dir=tmp_path / "state",
        auto_reconcile=False,
        ephemeral=True,
    )


def test_legacy_state_write_keeps_existing_path_without_owner_context(tmp_path):
    service = _service(tmp_path)
    result = service._write_state("legacy", {"status": "PENDING"})
    assert result["status"] == "PENDING"
    assert (tmp_path / "state" / "legacy.json").exists()


def test_opt_in_state_write_asserts_exact_owner_role_and_path(tmp_path, monkeypatch):
    service = _service(tmp_path)
    calls = []

    def assert_owner_write(context, *, role, relative_path):
        calls.append((context, role, relative_path))

    import nexus.events.state_owner_manifest as manifest

    monkeypatch.setattr(manifest, "assert_owner_write", assert_owner_write, raising=False)
    context = SimpleNamespace(binding=SimpleNamespace(root=service.state_dir))
    service._write_state("task-1", {"status": "PENDING"}, owner_context=context)
    assert calls == [(context, "task_state", "task-1.json"), (context, "task_state", "task-1.json")]


def test_opt_in_state_write_denies_cross_root_before_bytes(tmp_path, monkeypatch):
    service = _service(tmp_path)
    import nexus.events.state_owner_manifest as manifest

    called = []
    monkeypatch.setattr(
        manifest,
        "assert_owner_write",
        lambda *args, **kwargs: called.append((args, kwargs)),
        raising=False,
    )
    context = SimpleNamespace(binding=SimpleNamespace(root=(tmp_path / "other").resolve()))
    from nexus.events.state_owner_manifest import OwnerConflict
    with pytest.raises(OwnerConflict, match="STATE_OWNER_ROOT_MISMATCH"):
        service._write_state("task-1", {"status": "PENDING"}, owner_context=context)
    assert not (service.state_dir / "task-1.json").exists()
    assert called == []


def test_real_owner_guard_binds_task_state_write_and_commit(tmp_path):
    from nexus.events.state_owner_manifest import (
        StateOwnerBinding,
        StateOwnerSelection,
        commit_owner_transaction,
        owner_transaction_guard,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    service = _service(tmp_path)
    task_id = "task-guarded"
    service._write_state(task_id, {"status": "BASELINE"})
    install_generation(service.state_dir, EventWriterGeneration(1, "writer-1"))
    binding = StateOwnerBinding(
        "owner-1", service.state_dir, 1, "tx-guarded"
    )
    selections = (
        StateOwnerSelection("task:task-guarded", "task_state", f"{task_id}.json"),
    )
    with owner_transaction_guard(
        binding, writer_generation=EventWriterGeneration(1, "writer-1"), selections=selections
    ) as context:
        service._write_state(task_id, {"status": "COMMITTED"}, owner_context=context)
        committed = commit_owner_transaction(context)
    assert committed.state == "COMMITTED"
    import json

    persisted = json.loads((service.state_dir / f"{task_id}.json").read_text())
    assert persisted["status"] == "COMMITTED"


def test_owner_guard_rejects_fake_closed_and_cross_path_contexts_before_bytes(tmp_path):
    from nexus.events.state_owner_manifest import (
        OwnerConflict,
        StateOwnerBinding,
        StateOwnerSelection,
        commit_owner_transaction,
        owner_transaction_guard,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    service = _service(tmp_path)
    service._write_state("task-guarded", {"status": "BASELINE"})
    install_generation(service.state_dir, EventWriterGeneration(1, "writer-1"))
    binding = StateOwnerBinding("owner-1", service.state_dir, 1, "tx-guarded")
    selection = StateOwnerSelection("task:task-guarded", "task_state", "task-guarded.json")

    with pytest.raises(OwnerConflict):
        service._write_state(
            "task-guarded", {"status": "FAKE"}, owner_context=object()
        )

    with owner_transaction_guard(
        binding, writer_generation=EventWriterGeneration(1, "writer-1"), selections=(selection,)
    ) as context:
        with pytest.raises(OwnerConflict):
            service._write_state("other-task", {"status": "WRONG_PATH"}, owner_context=context)
        commit_owner_transaction(context)

    with pytest.raises(OwnerConflict):
        service._write_state("task-guarded", {"status": "CLOSED"}, owner_context=context)
    assert "CLOSED" not in (service.state_dir / "task-guarded.json").read_text()


def test_public_work_claim_paths_carry_owner_context_acquire_recover_release(tmp_path):
    from nexus.events.state_owner_manifest import (
        StateOwnerBinding,
        StateOwnerSelection,
        commit_owner_transaction,
        owner_transaction_guard,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    service = _service(tmp_path)
    task_id = "claim-guarded"
    service._write_state(task_id, {"status": "PENDING"})
    install_generation(service.state_dir, EventWriterGeneration(1, "writer-1"))
    selection = StateOwnerSelection(f"task:{task_id}", "task_state", f"{task_id}.json")
    generation = EventWriterGeneration(1, "writer-1")
    request = {"task_id": task_id, "claim_id": "claim-1", "generation": 1,
               "fencing_token": "", "worker": "worker-1"}

    def transaction(tx_id, previous):
        return owner_transaction_guard(
            StateOwnerBinding("owner-1", service.state_dir, 1, tx_id),
            writer_generation=generation,
            selections=(selection,),
            previous_manifest_sha256=previous,
        )

    with transaction("tx-acquire", None) as context:
        acquired = service.acquire_work_claim(request, owner_context=context)
        first = commit_owner_transaction(context)
    assert acquired["status"] == "CLAIMED"
    claim = acquired["claim"]
    request.update({"claim_id": claim["claim_id"], "generation": claim["generation"],
                    "fencing_token": claim["fencing_token"]})

    with transaction("tx-recover", first.manifest_sha256) as context:
        recovered = service.recover_work_claim(request, reason="TEST", owner_context=context)
        second = commit_owner_transaction(context)
    assert recovered["claim"]["generation"] == 2
    request.update({"generation": 2, "fencing_token": recovered["claim"]["fencing_token"]})

    with transaction("tx-release", second.manifest_sha256) as context:
        released = service.release_work_claim(request, owner_context=context)
        third = commit_owner_transaction(context)
    assert released == {"status": "RELEASED", "task_id": task_id}
    assert third.state == "COMMITTED"

    from nexus.events.state_owner_manifest import OwnerConflict

    before = (service.state_dir / f"{task_id}.json").read_bytes()
    with pytest.raises(OwnerConflict):
        service.acquire_work_claim(request, owner_context=context)
    assert (service.state_dir / f"{task_id}.json").read_bytes() == before


def test_constructor_bound_context_protects_public_workclaim_without_keyword(tmp_path):
    from nexus.events.state_owner_manifest import (
        StateOwnerBinding,
        StateOwnerSelection,
        commit_owner_transaction,
        owner_transaction_guard,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation

    base = _service(tmp_path)
    task_id = "constructor-bound"
    base._write_state(task_id, {"status": "PENDING"})
    install_generation(base.state_dir, EventWriterGeneration(1, "writer-1"))
    selection = StateOwnerSelection(f"task:{task_id}", "task_state", f"{task_id}.json")
    request = {"task_id": task_id, "claim_id": "claim-constructor", "worker": "worker-1"}
    token = EventWriterGeneration(1, "writer-1")
    binding = StateOwnerBinding("owner-1", base.state_dir, 1, "tx-constructor")
    with owner_transaction_guard(binding, writer_generation=token, selections=(selection,)) as context:
        service = _service(tmp_path)
        service._owner_context = context
        result = service.acquire_work_claim(request)
        commit_owner_transaction(context)
    assert result["status"] == "CLAIMED"
    assert json.loads((base.state_dir / f"{task_id}.json").read_text())["work_claim"]["claim_id"] == "claim-constructor"


def test_owner_context_denies_stale_generation_before_state_bytes(tmp_path):
    import hashlib
    import json
    from nexus.events.state_owner_manifest import (
        OwnerConflict,
        StateOwnerBinding,
        StateOwnerSelection,
        owner_transaction_guard,
    )
    from nexus.events.writer_generation import EventWriterGeneration, install_generation, manifest_path

    service = _service(tmp_path)
    task_id = "stale-owner"
    service._write_state(task_id, {"status": "PENDING"})
    install_generation(service.state_dir, EventWriterGeneration(1, "writer-1"))
    token = EventWriterGeneration(1, "writer-1")
    selection = StateOwnerSelection(f"task:{task_id}", "task_state", f"{task_id}.json")
    binding = StateOwnerBinding("owner-1", service.state_dir, 1, "tx-stale")
    before = (service.state_dir / f"{task_id}.json").read_bytes()
    with owner_transaction_guard(binding, writer_generation=token, selections=(selection,)) as context:
        payload = {
            "schema": "nexus.event_writer_generation.v1",
            "store": "event_log",
            "event_log": "event_log.jsonl",
            "lock": "event_log.lock",
            "generation": 2,
            "writer_id": "writer-2",
        }
        payload["manifest_digest"] = hashlib.sha256(
            json.dumps({k: payload[k] for k in payload if k != "manifest_digest"}, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        manifest_path(service.state_dir).write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(OwnerConflict):
            service._write_state(task_id, {"status": "STALE"}, owner_context=context)
    assert (service.state_dir / f"{task_id}.json").read_bytes() == before
