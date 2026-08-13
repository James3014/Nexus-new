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
        lambda _request: {"workforce_admission": {"overall_decision": "ALLOW"}},
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


def test_unreadable_or_non_array_manifest_fails_closed(tmp_path: Path):
    consumer = NightshiftQueueConsumer(lambda _request: {}, lambda _item: None)
    path = tmp_path / "pending.json"
    path.write_text("{}", encoding="utf-8")
    assert consumer.consume_file(path)[0]["reason"] == "manifest_must_be_array"
    path.write_text("not json", encoding="utf-8")
    assert consumer.consume_file(path)[0]["reason"] == "manifest_unreadable"


def test_nightshift_producer_emits_option_b_contract(tmp_path: Path):
    runner = AutoResearchNightShift(project_root=tmp_path, task="producer task")
    runner._append_to_pending_manifest("producer task", "target.py", "deadbeef", 0.9, str(tmp_path))
    item = json.loads((tmp_path / ".nexus/nightshift/pending.json").read_text(encoding="utf-8"))[0]
    assert item["schema"] == SCHEMA
    assert item["demand_role"] == "bounded_candidate_generation"
    assert item["mutation_intent"] is False
    assert all(value is False for value in item["worker_permissions"].values())
