import json
from pathlib import Path

from nexus.app.nightshift_runner_service import AutoResearchNightShift
from nexus.services.nightshift_queue_consumer import (
    REQUIRED_CONTROLS,
    SCHEMA,
    NightshiftQueueConsumer,
)


def _item(**overrides):
    item = {
        "schema": SCHEMA,
        "demand_role": "bounded_candidate_generation",
        "required_controls": sorted(REQUIRED_CONTROLS),
        "mutation_intent": False,
        "external_verification_required": True,
        "worker_permissions": {key: False for key in ("commit", "push", "approve", "integrate")},
        "task": "bounded task",
        "commit_sha": "abc123",
    }
    item.update(overrides)
    return item


def test_dispatch_requires_canonical_allow_and_is_idempotent(tmp_path: Path):
    dispatched = []
    consumer = NightshiftQueueConsumer(
        lambda _request: {
            "workforce_admission": {"overall_decision": "ALLOW"},
            "gateway_invocation_authority": {"status": "ALLOW", "gate_passed": True},
        },
        dispatched.append,
    )
    path = tmp_path / "pending.json"
    path.write_text(json.dumps([_item(), _item()]), encoding="utf-8")

    result = consumer.consume_file(path)

    assert [entry["status"] for entry in result] == ["DISPATCHED", "SKIP"]
    assert len(dispatched) == 1


def test_malformed_tampered_or_non_allow_manifest_never_dispatches(tmp_path: Path):
    dispatched = []
    consumer = NightshiftQueueConsumer(
        lambda _request: {"workforce_admission": {"overall_decision": "BLOCK"}},
        dispatched.append,
    )
    path = tmp_path / "pending.json"
    path.write_text(
        json.dumps([_item(required_controls=[]), _item(mutation_intent=True), {"schema": SCHEMA}]),
        encoding="utf-8",
    )

    result = consumer.consume_file(path)

    assert all(entry["status"] == "BLOCK" for entry in result)
    assert dispatched == []


def test_fake_allow_without_canonical_authority_never_dispatches(tmp_path: Path):
    dispatched = []
    consumer = NightshiftQueueConsumer(
        lambda _request: {"workforce_admission": {"overall_decision": "ALLOW"}},
        dispatched.append,
    )
    path = tmp_path / "pending.json"
    path.write_text(json.dumps([_item()]), encoding="utf-8")
    assert consumer.consume_file(path)[0]["status"] == "BLOCK"
    assert dispatched == []


def test_unreadable_or_non_array_manifest_fails_closed(tmp_path: Path):
    consumer = NightshiftQueueConsumer(lambda _request: {}, lambda _item: None)
    path = tmp_path / "pending.json"
    path.write_text("{}", encoding="utf-8")
    assert consumer.consume_file(path)[0]["reason"] == "manifest_must_be_array"
    path.write_text("not json", encoding="utf-8")
    assert consumer.consume_file(path)[0]["reason"] == "manifest_unreadable"


def test_success_marks_all_duplicate_entries_and_restart_dispatches_once(tmp_path: Path):
    dispatched = []
    item = _item()
    consumer = NightshiftQueueConsumer(
        lambda _request: {
            "workforce_admission": {"overall_decision": "ALLOW"},
            "gateway_invocation_authority": {"status": "ALLOW", "gate_passed": True},
        },
        dispatched.append,
        project_root=tmp_path,
    )
    path = tmp_path / ".nexus/nightshift/pending.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([item, dict(item)]), encoding="utf-8")
    assert consumer.consume_file(path)[0]["status"] == "DISPATCHED"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert all(entry["disposition"] == "DISPATCHED" for entry in stored)
    restarted = NightshiftQueueConsumer(
        lambda _request: {}, dispatched.append, project_root=tmp_path
    )
    assert all(entry["status"] == "SKIP" for entry in restarted.consume_file(path))
    assert len(dispatched) == 1


def test_noncanonical_manifest_path_is_blocked(tmp_path: Path):
    consumer = NightshiftQueueConsumer(
        lambda _request: {}, lambda _item: None, project_root=tmp_path
    )
    path = tmp_path / "other.json"
    path.write_text("[]", encoding="utf-8")
    assert consumer.consume_file(path)[0]["reason"] == "noncanonical_manifest_path"


def test_nightshift_producer_emits_option_b_contract(tmp_path: Path):
    runner = AutoResearchNightShift(project_root=tmp_path, task="producer task")
    runner._append_to_pending_manifest("producer task", "target.py", "deadbeef", 0.9, str(tmp_path))
    item = json.loads((tmp_path / ".nexus/nightshift/pending.json").read_text(encoding="utf-8"))[0]
    assert item["schema"] == SCHEMA
    assert item["demand_role"] == "bounded_candidate_generation"
    assert item["mutation_intent"] is False
    assert all(value is False for value in item["worker_permissions"].values())


def test_nightshift_bindings_follow_policy_route_not_hardcoded_model():
    from types import SimpleNamespace

    import pytest

    from nexus.services.model_workforce_policy import WorkforcePolicyError
    from nexus.services.nightshift_queue_consumer import (
        NIGHTSHIFT_ONLINE_ROLE,
        build_nightshift_workforce_bindings,
    )

    class _Loader:
        def __init__(self, route, workers):
            self.route, self.workers = route, workers

        def load(self):
            return SimpleNamespace(workers=self.workers)

        def resolve_route(self, role):
            assert role == NIGHTSHIFT_ONLINE_ROLE
            return self.route

    worker = SimpleNamespace(worker_id="policy_worker_x", model="model-x", provider="p")
    bindings = build_nightshift_workforce_bindings(
        controls=("verifier", "parser"),
        policy_loader=_Loader("policy_worker_x", {"policy_worker_x": worker}),
    )
    assert bindings == {
        "online": {"worker_id": "policy_worker_x", "controls": ["parser", "verifier"]}
    }

    with pytest.raises(WorkforcePolicyError):
        build_nightshift_workforce_bindings(policy_loader=_Loader("absent_worker", {}))


def test_consumer_ignores_tampered_manifest_bindings_and_controls(tmp_path: Path):
    from nexus.services.nightshift_queue_consumer import (
        build_nightshift_workforce_bindings,
        resolve_nightshift_online_worker,
    )

    seen = []

    def _runner(request):
        seen.append(request)
        return {"workforce_admission": {"overall_decision": "BLOCK"}}

    honest = _item(task="honest")
    tampered = _item(
        task="tampered",
        workforce_bindings={
            "online": {
                "worker_id": "codex_luna",
                "provider": "codex",
                "model": "other-model",
                "controls": ["task_card", "allowed_files", "mandatory_commands", "verifier"],
                "explicit_experiment_authorization": True,
            }
        },
        provided_controls=["task_card"],
        required_controls=sorted(REQUIRED_CONTROLS) + ["task_card"],
    )
    path = tmp_path / "pending.json"
    path.write_text(json.dumps([honest, tampered]), encoding="utf-8")

    NightshiftQueueConsumer(_runner, lambda _item: None).consume_file(path)

    assert len(seen) == 2
    expected = build_nightshift_workforce_bindings()
    for request in seen:
        assert request.route["workforce_bindings"] == expected
        assert request.route["provider"] == resolve_nightshift_online_worker().provider
    assert seen[0].route == {**seen[1].route}
    assert "task_card" not in expected["online"]["controls"]


def test_policy_load_failure_sends_empty_bindings_and_blocks(tmp_path: Path, monkeypatch):
    """#2257: a failing policy load must reach the empty-bindings BLOCK path.

    Before the fix ``WorkforcePolicyError`` was imported inside the same ``try``
    whose ``except`` clause named it, so an import failure raised ``NameError``
    instead of falling through to the fail-closed branch.
    """
    import nexus.services.nightshift_queue_consumer as consumer
    from nexus.services.model_workforce_policy import WorkforcePolicyError

    def _raise(*_args, **_kwargs):
        raise WorkforcePolicyError("policy unavailable")

    monkeypatch.setattr(consumer, "build_nightshift_workforce_bindings", _raise)
    seen = []

    def _runner(request):
        seen.append(request)
        return {"workforce_admission": {"overall_decision": "BLOCK"}}

    dispatched = []
    path = tmp_path / "pending.json"
    path.write_text(json.dumps([_item(task="no-policy")]), encoding="utf-8")

    result = consumer.NightshiftQueueConsumer(_runner, dispatched.append).consume_file(path)

    assert dispatched == []
    assert len(seen) == 1
    assert seen[0].route["workforce_bindings"] == {}
    assert "provider" not in seen[0].route
    assert [entry["status"] for entry in result] == ["BLOCK"]
    assert result[0]["reason"] == "workforce_admission_not_allow"


def test_policy_module_import_failure_blocks_instead_of_name_error(tmp_path: Path, monkeypatch):
    """#2257: the discriminating case. Before the fix ``WorkforcePolicyError`` was
    imported inside the ``try``; with the policy module unimportable the import
    raised, the ``except`` clause evaluated an unbound name and ``consume_file``
    died with ``NameError``. Now the name is bound at module level and an
    ``ImportError`` from the policy load falls through to the BLOCK path."""
    import sys

    import nexus.services.nightshift_queue_consumer as consumer

    assert "WorkforcePolicyError" in vars(consumer)
    # ``None`` in sys.modules makes ``from nexus.services.model_workforce_policy
    # import ...`` raise ImportError (the lazy import inside the policy resolver).
    monkeypatch.setitem(sys.modules, "nexus.services.model_workforce_policy", None)
    seen = []

    def _runner(request):
        seen.append(request)
        return {"workforce_admission": {"overall_decision": "BLOCK"}}

    dispatched = []
    path = tmp_path / "pending.json"
    path.write_text(json.dumps([_item(task="no-policy-module")]), encoding="utf-8")

    result = consumer.NightshiftQueueConsumer(_runner, dispatched.append).consume_file(path)

    assert dispatched == []
    assert len(seen) == 1
    assert seen[0].route["workforce_bindings"] == {}
    assert [entry["status"] for entry in result] == ["BLOCK"]


def test_concurrent_append_during_consume_keeps_both_effects(tmp_path: Path):
    dispatched = []
    producer = AutoResearchNightShift(project_root=tmp_path, task="task-b")

    def _dispatcher(item):
        producer._append_to_pending_manifest("task-b", "target.py", "bbb222", 0.9, str(tmp_path))
        dispatched.append(item)

    consumer = NightshiftQueueConsumer(
        lambda _request: {
            "workforce_admission": {"overall_decision": "ALLOW"},
            "gateway_invocation_authority": {"status": "ALLOW", "gate_passed": True},
        },
        _dispatcher,
        project_root=tmp_path,
    )
    path = tmp_path / ".nexus/nightshift/pending.json"
    path.parent.mkdir(parents=True)
    item_a = _item(task="task-a", commit_sha="aaa111")
    path.write_text(json.dumps([item_a]), encoding="utf-8")

    consumer.consume_file(path)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert len(stored) == 2
    entry_a = next(entry for entry in stored if entry.get("task") == "task-a")
    assert entry_a["disposition"] == "DISPATCHED"
    assert any(entry.get("task") == "task-b" for entry in stored)
