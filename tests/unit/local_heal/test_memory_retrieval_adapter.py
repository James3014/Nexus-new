import json

from nexus.contracts.learning_experience import build_nexus_learning_episode
from nexus.services.local_heal.memory_retrieval_adapter import (
    CanonicalEpisodicMemoryLessonStore,
    LocalJsonlLessonStore,
    MemoryRetrievalAdapter,
    NexusCompositeLessonStore,
)

QUALIFICATION = {
    "repeatability": "reproducible across three attempts",
    "prevention_rule": "verify canonical receipt before replay",
    "authority_qualification": "coordinator accepted",
}


def _episode(**overrides):
    params = dict(
        task_id="github-issue-999-cross-task",
        attempt_id="attempt-1",
        action_id="action-1",
        source="canonical-test",
        terminal_outcome="SUCCEEDED",
        terminal_evidence={"verifier": "test_verifier", "verifier_status": "PASS"},
        qualification=dict(QUALIFICATION),
        lesson_disposition="graduated",
        idempotency_key="ep-999-1",
    )
    params.update(overrides)
    return build_nexus_learning_episode(**params)


def _write_ledger(tmp_path, lines):
    ledger = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    ledger.write_text(payload, encoding="utf-8")
    return ledger


def test_canonical_store_exposes_valid_terminal_episodes(tmp_path):
    _write_ledger(tmp_path, [json.dumps(_episode())])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical receipt", limit=5)

    assert len(rows) == 1
    assert rows[0]["classification"] == "verifier_pass"
    assert rows[0]["provenance"] == "test_verifier"
    assert rows[0]["source"] == "canonical_episodic_memory"
    assert rows[0]["lesson_id"] == rows[0]["episode_id"]
    assert store.last_metadata["query_succeeded"] is True
    assert store.last_metadata["result_count"] == 1


def test_episode_with_receipt_prefers_receipt_provenance(tmp_path):
    episode = _episode(
        terminal_evidence={"receipt": "receipt:canonical-999", "verifier": "test_verifier"},
        idempotency_key="ep-999-receipt",
    )
    _write_ledger(tmp_path, [json.dumps(episode)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows[0]["provenance"] == "receipt:canonical-999"


def test_adapter_returns_canonical_lessons_as_first_class_source(tmp_path):
    _write_ledger(tmp_path, [json.dumps(_episode())])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    lessons = adapter.retrieve(query_text="canonical receipt", limit=5)

    assert len(lessons) == 1
    assert lessons[0].source == "canonical_episodic_memory"
    assert lessons[0].pattern_type == "success"
    assert lessons[0].provenance == "test_verifier"
    assert lessons[0].summary == QUALIFICATION["prevention_rule"]
    assert adapter.last_metadata["accepted"] == 1
    assert adapter.last_metadata["no_memory_match"] is False


def test_default_composite_includes_canonical_store():
    composite = NexusCompositeLessonStore()

    assert any(isinstance(store, CanonicalEpisodicMemoryLessonStore) for store in composite.stores)


def test_composite_metadata_records_canonical_source(tmp_path):
    _write_ledger(tmp_path, [json.dumps(_episode())])
    composite = NexusCompositeLessonStore([
        CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    ])
    adapter = MemoryRetrievalAdapter(store=composite)

    lessons = adapter.retrieve(query_text="canonical receipt", limit=5)

    assert len(lessons) == 1
    assert lessons[0].source == "canonical_episodic_memory"
    assert adapter.last_metadata["retrieval_sources"] == ["CanonicalEpisodicMemoryLessonStore"]
    assert adapter.last_metadata["source_counts"] == {"CanonicalEpisodicMemoryLessonStore": 1}


def test_same_task_excluded_when_caller_supplies_task_identity(tmp_path):
    episode_a = _episode(task_id="github-issue-292-same-task", idempotency_key="ep-292-a")
    episode_b = _episode(task_id="github-issue-999-cross-task", idempotency_key="ep-292-b")
    _write_ledger(tmp_path, [json.dumps(episode_a), json.dumps(episode_b)])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    lessons = adapter.retrieve(
        query_text="canonical", limit=5, exclude_task_id="github-issue-292-same-task"
    )

    assert [lesson.task_id for lesson in lessons] == ["github-issue-999-cross-task"]
    assert adapter.last_metadata["rejected_same_task"] == 1
    assert adapter.last_metadata["accepted"] == 1


def test_wrong_schema_and_malformed_json_lines_fail_closed(tmp_path):
    wrong_schema = {
        "schema": "nexus.legacy.v1",
        "task_id": "task-wrong",
        "summary": "legacy row",
    }
    incomplete = _episode(idempotency_key="ep-incomplete")
    del incomplete["stages"]
    _write_ledger(
        tmp_path,
        [json.dumps(wrong_schema), "{not-json", json.dumps(incomplete)],
    )
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["query_succeeded"] is True
    assert store.last_metadata["result_count"] == 0
    assert store.last_metadata["rejected_validation"] == 1


def test_identity_mismatch_and_incomplete_records_fail_closed(tmp_path):
    mismatched = _episode(idempotency_key="ep-mismatch")
    mismatched["episode_id"] = "lep:000000000000000000000000"
    missing_terminal = _episode(idempotency_key="ep-missing-evidence")
    del missing_terminal["terminal_evidence"]
    _write_ledger(tmp_path, [json.dumps(mismatched), json.dumps(missing_terminal)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_validation"] == 2


def test_missing_terminal_provenance_fails_closed(tmp_path):
    episode = _episode(
        idempotency_key="ep-no-provenance",
        terminal_evidence={"verifier_status": "PASS"},
    )
    _write_ledger(tmp_path, [json.dumps(episode)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    adapter = MemoryRetrievalAdapter(store=store)

    rows = store.query(query_text="canonical", limit=5)
    lessons = adapter.retrieve(query_text="canonical", limit=5)

    assert rows == []
    assert lessons == []
    assert store.last_metadata["rejected_without_terminal_provenance"] == 1


def test_non_terminal_and_unqualified_records_fail_closed(tmp_path):
    failed = _episode(task_id="task-failed", terminal_outcome="FAILED", idempotency_key="ep-failed")
    unqualified = _episode(
        task_id="task-unqualified", qualification={}, idempotency_key="ep-unqualified"
    )
    replay = _episode(task_id="task-replay", idempotency_key="ep-replay")
    replay["auto_replay_allowed"] = True
    _write_ledger(
        tmp_path,
        [json.dumps(failed), json.dumps(unqualified), json.dumps(replay)],
    )
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_non_terminal"] == 2
    assert store.last_metadata["rejected_validation"] == 1


def test_duplicates_dedupe_deterministically_and_repeated_read_is_stable(tmp_path):
    original = _episode()
    twin = _episode(attempt_id="attempt-2", idempotency_key="ep-999-2")
    _write_ledger(tmp_path, [json.dumps(original), json.dumps(original), json.dumps(twin)])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    first = adapter.retrieve(query_text="canonical receipt", limit=5)
    second = adapter.retrieve(query_text="canonical receipt", limit=5)

    assert len(first) == 1
    assert first[0].occurrence_count == 2
    assert [lesson.finding_id for lesson in first] == [lesson.finding_id for lesson in second]
    assert [lesson.occurrence_count for lesson in first] == [
        lesson.occurrence_count for lesson in second
    ]
    assert first[0].provenance == second[0].provenance


def test_missing_ledger_is_fail_open_empty_and_legacy_store_remains_isolated(tmp_path):
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    assert store.query(query_text="canonical", limit=5) == []
    assert store.last_metadata["ledger_exists"] is False
    assert store.last_metadata["query_succeeded"] is True

    legacy_path = tmp_path / "learning_closure.jsonl"
    legacy_path.write_text(
        '{"lesson_id":"lh-jsonl","task_id":"C_1","classification":"success",'
        '"summary":"legacy format owner","provenance":"receipt:jsonl"}\n',
        encoding="utf-8",
    )
    composite = NexusCompositeLessonStore([
        LocalJsonlLessonStore(legacy_path),
        CanonicalEpisodicMemoryLessonStore(project_root=tmp_path),
    ])
    adapter = MemoryRetrievalAdapter(store=composite)

    lessons = adapter.retrieve(query_text="legacy format", limit=5)

    assert [lesson.finding_id for lesson in lessons] == ["lh-jsonl"]
    assert adapter.last_metadata["retrieval_sources"] == ["LocalJsonlLessonStore"]
