from __future__ import annotations
import json
import multiprocessing
from pathlib import Path
import pytest
from nexus.events.effect_journal import EffectJournal, EffectIdentityMismatch, EffectJournalError, _digest_record, deterministic_effect_id
from nexus.events.writer_generation import EventWriterGeneration, GenerationError, install_generation

def journal(tmp_path):
    root = tmp_path / "project"; root.mkdir()
    token = EventWriterGeneration(1, "test-writer")
    install_generation(root, token)
    return root, EffectJournal(root, token)

def test_reserve_complete_replay_and_binding(tmp_path):
    root, j = journal(tmp_path); calls=[]
    ident={"task_id":"t1","workspace_revision":"w1","planner_decision_id":"p","attempt":1,"action":"online","subject_revision":"s","request_digest":"r"}
    out=j.execute(identity=ident, subject="t1", request_digest="r", dispatch=lambda: calls.append(1) or {"ok": True}, reconcile=lambda _: None)
    assert out == {"ok": True} and calls == [1]
    assert j.execute(identity=ident, subject="t1", request_digest="r", dispatch=lambda: calls.append(2), reconcile=lambda _: None)=={"ok": True}
    assert calls == [1]
    with pytest.raises(EffectIdentityMismatch): j.reserve(identity=ident, subject="other", request_digest="r")

def test_uncertain_is_reconcile_only(tmp_path):
    root,j=journal(tmp_path); ident={"task_id":"t","workspace_revision":"w","planner_decision_id":"p","attempt":1,"action":"local","subject_revision":"s","request_digest":"r"}
    with pytest.raises(RuntimeError): j.execute(identity=ident, subject="t", request_digest="r", dispatch=lambda: (_ for _ in ()).throw(RuntimeError("crash")), reconcile=lambda _: None)
    assert j.get(deterministic_effect_id(ident))["state"] == "UNKNOWN"
    calls=[]; observed=j.execute(identity=ident, subject="t", request_digest="r", dispatch=lambda: calls.append(1), reconcile=lambda rec: {"operation_id": rec["operation_id"], "effect_id": rec["effect_id"], "subject": rec["subject"], "request_digest": rec["request_digest"], "generation": rec["generation"], "result": {"observed": rec["effect_id"]}}); assert observed["observed"]
    assert calls == []

def test_malformed_and_symlink_fail_closed(tmp_path):
    root,j=journal(tmp_path); p=j.path; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('{"schema":"bad"}')
    with pytest.raises(EffectJournalError): j.get("x")
    p.unlink(); p.symlink_to(tmp_path / "missing")
    with pytest.raises(EffectJournalError): j.get("x")

def test_identity_and_completed_records_are_strict(tmp_path):
    _, j = journal(tmp_path)
    ident={"task_id":"strict","workspace_revision":"w","planner_decision_id":"p","attempt":1,"action":"a","subject_revision":"s","request_digest":"d"}
    with pytest.raises(EffectJournalError): j.reserve(identity={"junk":"not-a-task"}, subject="strict", request_digest="d")
    j.execute(identity=ident, subject="strict", request_digest="d", dispatch=lambda: {"ok": True}, reconcile=None)
    with pytest.raises(EffectIdentityMismatch): j.transition(deterministic_effect_id(ident), "COMPLETED", result={"ok": False})
    assert j.get(deterministic_effect_id(ident))["result"] == {"ok": True}
    with pytest.raises(EffectIdentityMismatch): j.reconcile(deterministic_effect_id(ident), {"bad": True})


def test_completed_result_digest_tamper_is_rejected_before_replay(tmp_path):
    _, j = journal(tmp_path)
    ident = {"task_id": "digest", "workspace_revision": "w", "planner_decision_id": "p", "attempt": 1, "action": "online", "subject_revision": "s", "request_digest": "d"}
    effect = deterministic_effect_id(ident)
    assert j.execute(identity=ident, subject="digest", request_digest="d", dispatch=lambda: {"original": True}, reconcile=None) == {"original": True}
    data = json.loads(j.path.read_text(encoding="utf-8"))
    record = data["records"][effect]
    record["result"] = {"forged": True}
    record["record_digest"] = _digest_record(record)
    j.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EffectJournalError, match="EFFECT_RESULT_TAMPERED"):
        j.get(effect)


def test_generation_advance_retains_history_but_fences_old_writer(tmp_path):
    root, old = journal(tmp_path)
    old_identity = {"task_id": "gen1", "workspace_revision": "w", "planner_decision_id": "p1", "attempt": 1, "action": "online", "subject_revision": "s", "request_digest": "old"}
    old_effect = deterministic_effect_id(old_identity)
    assert old.execute(identity=old_identity, subject="gen1", request_digest="old", dispatch=lambda: {"generation": 1}, reconcile=None) == {"generation": 1}
    before = old.path.read_bytes()
    old_record_before = json.loads(before)["records"][old_effect]

    new_token = EventWriterGeneration(2, "writer-2")
    install_generation(root, new_token, expected_generation=1)
    new = EffectJournal(root, new_token)
    assert new.get(old_effect)["generation"] == 1

    new_identity = {"task_id": "gen2", "workspace_revision": "w", "planner_decision_id": "p2", "attempt": 1, "action": "online", "subject_revision": "s", "request_digest": "new"}
    new_effect = deterministic_effect_id(new_identity)
    assert new.execute(identity=new_identity, subject="gen2", request_digest="new", dispatch=lambda: {"generation": 2}, reconcile=None) == {"generation": 2}
    assert new.get(old_effect)["generation"] == 1
    assert new.get(new_effect)["generation"] == 2
    assert json.loads(old.path.read_bytes())["records"][old_effect] == old_record_before

    with pytest.raises(GenerationError, match="GENERATION_REQUIRED"):
        old.get(new_effect)
    assert old.path.read_bytes() != before
    with pytest.raises(EffectIdentityMismatch, match="EFFECT_IDENTITY_MISMATCH"):
        new.reserve(identity=old_identity, subject="gen1", request_digest="old")


@pytest.mark.parametrize("bad_generation", [True, 0, 2, "2"])
def test_record_generation_is_positive_int_and_not_future(tmp_path, bad_generation):
    _, j = journal(tmp_path)
    identity = {"task_id": "generation-record", "workspace_revision": "w", "planner_decision_id": "p", "attempt": 1, "action": "online", "subject_revision": "s", "request_digest": "d"}
    effect = deterministic_effect_id(identity)
    j.execute(identity=identity, subject="generation-record", request_digest="d", dispatch=lambda: {"ok": True}, reconcile=None)
    data = json.loads(j.path.read_text(encoding="utf-8"))
    record = data["records"][effect]
    record["generation"] = bad_generation
    record["record_digest"] = _digest_record(record)
    j.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EffectJournalError, match="EFFECT_JOURNAL_MALFORMED"):
        j.get(effect)
