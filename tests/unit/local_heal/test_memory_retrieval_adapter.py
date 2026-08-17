import json
from datetime import datetime, timedelta, timezone

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


def _with_applicability(episode, **fields):
    episode = dict(episode)
    episode.update(fields)
    return episode


def _iso_utc(offset):
    return (datetime.now(timezone.utc) + offset).isoformat()


def _naive_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


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
    assert lessons[0].episode_id.startswith("lep:")
    assert lessons[0].attempt_id == "attempt-1"
    assert lessons[0].action_id == "action-1"
    assert lessons[0].qualification_status == "QUALIFIED"
    assert lessons[0].validity_state == "active"
    assert lessons[0].evidence_ref == "test_verifier"
    assert adapter.last_metadata["accepted"] == 1
    assert adapter.last_metadata["no_memory_match"] is False
    assert adapter.last_metadata["retrieval_receipt"]["schema"] == "nexus.retrieval_receipt.v1"
    assert adapter.last_metadata["retrieval_receipt"]["status"] == "PASS"
    assert adapter.last_metadata["retrieval_receipt_hash"].startswith("sha256:")
    lineage = adapter.last_metadata["selected_lesson_lineage"]
    assert lineage == [
        {
            "lesson_id": lessons[0].finding_id,
            "episode_id": lessons[0].episode_id,
            "source_task_id": "github-issue-999-cross-task",
            "source_attempt_id": "attempt-1",
            "source_action_id": "action-1",
            "qualification_status": "QUALIFIED",
            "validity_state": "active",
            "evidence_ref": "test_verifier",
            "source": "canonical_episodic_memory",
            "retrieval_receipt_hash": adapter.last_metadata["retrieval_receipt_hash"],
        }
    ]


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


def test_reranked_path_excludes_same_task_and_receipt_matches_final_selection(tmp_path):
    same = _episode(task_id="github-issue-292-same-task", idempotency_key="ep-292-rerank-same")
    cross = _episode(task_id="github-issue-999-cross-task", idempotency_key="ep-292-rerank-cross")
    _write_ledger(tmp_path, [json.dumps(same), json.dumps(cross)])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    lessons = adapter.retrieve_reranked(
        query_text="canonical receipt",
        limit=5,
        task_id="github-issue-292-same-task",
    )

    assert [lesson.task_id for lesson in lessons] == ["github-issue-999-cross-task"]
    assert adapter.last_metadata["rejected_same_task"] == 1
    receipt = adapter.last_metadata["retrieval_receipt"]
    selected = [item for item in receipt["results"] if item["selected"]]
    assert [item["source_id"] for item in selected] == [lesson.episode_id for lesson in lessons]
    assert receipt["selected_count"] == len(lessons)
    assert len(adapter.last_metadata["selected_lesson_lineage"]) == len(lessons)


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


def test_g2_version_boundary_lower_equal_accepted_future_rejected(tmp_path):
    lower = _with_applicability(_episode(idempotency_key="ep-g2-v1"), state_version=1)
    equal = _with_applicability(_episode(idempotency_key="ep-g2-v2"), state_version=2)
    future = _with_applicability(_episode(idempotency_key="ep-g2-v3"), state_version=3)
    _write_ledger(tmp_path, [json.dumps(lower), json.dumps(equal), json.dumps(future)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5, current_state={"state_version": 2})

    assert {row["episode_id"] for row in rows} == {lower["episode_id"], equal["episode_id"]}
    assert store.last_metadata["result_count"] == 2
    assert store.last_metadata["rejected_applicability_mismatch"] == 1
    assert store.last_metadata["rejected_recency"] == 0


def test_g2_non_integer_and_missing_episode_version_fails_closed(tmp_path):
    tampered = _with_applicability(_episode(idempotency_key="ep-g2-str"), state_version="2")
    missing = _episode(idempotency_key="ep-g2-missing")
    _write_ledger(tmp_path, [json.dumps(tampered), json.dumps(missing)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5, current_state={"state_version": 5})

    assert rows == []
    assert store.last_metadata["rejected_applicability_mismatch"] == 2


def test_g2_identity_dimensions_match_accepted_mismatch_and_missing_rejected(tmp_path):
    matching = _with_applicability(
        _episode(idempotency_key="ep-g2-match"),
        source_hash="sha256:abc",
        contract_revision="rev-1",
        runtime_identity="runtime-a",
    )
    mismatched = _with_applicability(
        _episode(idempotency_key="ep-g2-mismatch"),
        source_hash="sha256:other",
        contract_revision="rev-1",
        runtime_identity="runtime-a",
    )
    missing = _episode(idempotency_key="ep-g2-missing-identity")
    _write_ledger(tmp_path, [json.dumps(matching), json.dumps(mismatched), json.dumps(missing)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(
        query_text="canonical",
        limit=5,
        current_state={
            "source_revision": "sha256:abc",
            "contract_revision": "rev-1",
            "runtime_identity": "runtime-a",
        },
    )

    assert [row["episode_id"] for row in rows] == [matching["episode_id"]]
    assert store.last_metadata["rejected_applicability_mismatch"] == 2


def test_g2_recency_fresh_accepted_stale_future_missing_malformed_naive_rejected(tmp_path):
    fresh = _with_applicability(
        _episode(idempotency_key="ep-g2-fresh"), created_at=_iso_utc(timedelta(hours=-1))
    )
    stale = _with_applicability(
        _episode(idempotency_key="ep-g2-stale"), created_at=_iso_utc(timedelta(days=-4))
    )
    future = _with_applicability(
        _episode(idempotency_key="ep-g2-future"), created_at=_iso_utc(timedelta(days=1))
    )
    missing = _episode(idempotency_key="ep-g2-no-ts")
    malformed = _with_applicability(
        _episode(idempotency_key="ep-g2-bad-ts"), created_at="not-a-date"
    )
    naive = _with_applicability(_episode(idempotency_key="ep-g2-naive"), created_at=_naive_iso())
    _write_ledger(
        tmp_path,
        [json.dumps(ep) for ep in (fresh, stale, future, missing, malformed, naive)],
    )
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5, current_state={"max_age_days": 2})

    assert [row["episode_id"] for row in rows] == [fresh["episode_id"]]
    assert store.last_metadata["rejected_recency"] == 5


def test_g2_unknown_or_malformed_current_state_fails_closed_with_no_rows(tmp_path):
    _write_ledger(tmp_path, [json.dumps(_episode())])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    unknown = store.query(query_text="canonical", limit=5, current_state={"unknown_key": 1})
    assert unknown == []
    assert store.last_metadata["rejected_current_state_input"] == 1
    assert store.last_metadata["current_state_failure_reason"].startswith(
        "unknown current_state key"
    )
    wrong_type = store.query(query_text="canonical", limit=5, current_state={"state_version": "2"})
    assert wrong_type == []
    assert store.last_metadata["rejected_current_state_input"] == 1
    not_mapping = store.query(query_text="canonical", limit=5, current_state="state")

    assert not_mapping == []
    assert store.last_metadata["rejected_current_state_input"] == 1
    assert store.last_metadata["result_count"] == 0
    assert store.last_metadata["query_succeeded"] is True


def test_g2_tampered_fields_fail_closed_and_repeated_reads_are_stable(tmp_path):
    tampered = _with_applicability(_episode(idempotency_key="ep-g2-tamper"), contract_revision="")
    stable = _with_applicability(
        _episode(idempotency_key="ep-g2-stable"), contract_revision="rev-1"
    )
    _write_ledger(tmp_path, [json.dumps(tampered), json.dumps(stable)])
    ledger = tmp_path / ".nexus" / "memory" / "learning_episodes.jsonl"
    before = ledger.read_bytes()
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    first = store.query(
        query_text="canonical", limit=5, current_state={"contract_revision": "rev-1"}
    )
    assert [row["episode_id"] for row in first] == [stable["episode_id"]]
    assert store.last_metadata["rejected_applicability_mismatch"] == 1
    second = store.query(
        query_text="canonical", limit=5, current_state={"contract_revision": "rev-1"}
    )

    assert [row["episode_id"] for row in second] == [stable["episode_id"]]
    assert store.last_metadata["rejected_applicability_mismatch"] == 1
    assert ledger.read_bytes() == before


def test_g2_current_state_none_reproduces_g1(tmp_path):
    _write_ledger(tmp_path, [json.dumps(_episode())])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    baseline = adapter.retrieve(query_text="canonical receipt", limit=5)
    explicit = adapter.retrieve(query_text="canonical receipt", limit=5, current_state=None)

    assert [lesson.finding_id for lesson in baseline] == [lesson.finding_id for lesson in explicit]
    assert adapter.last_metadata["current_state_applied"] is False
    assert adapter.last_metadata["rejected_current_state_input"] == 0


def test_g2_adapter_direct_canonical_store_surfaces_counters(tmp_path):
    _write_ledger(
        tmp_path,
        [
            json.dumps(
                _with_applicability(_episode(idempotency_key="ep-g2-direct"), state_version=3)
            )
        ],
    )
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    lessons = adapter.retrieve(query_text="canonical", limit=5, current_state={"state_version": 1})

    assert lessons == []
    assert adapter.last_metadata["accepted"] == 0
    assert adapter.last_metadata["no_memory_match"] is True
    assert adapter.last_metadata["rejected_applicability_mismatch"] == 1


def test_g2_adapter_counters_aggregate_across_composite_receipts(tmp_path):
    _write_ledger(
        tmp_path,
        [
            json.dumps(_with_applicability(_episode(idempotency_key="ep-g2-a"), state_version=1)),
            json.dumps(_with_applicability(_episode(idempotency_key="ep-g2-b"), state_version=5)),
        ],
    )
    composite = NexusCompositeLessonStore([
        CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    ])
    adapter = MemoryRetrievalAdapter(store=composite)

    lessons = adapter.retrieve(query_text="canonical", limit=5, current_state={"state_version": 2})

    assert len(lessons) == 1
    assert adapter.last_metadata["accepted"] == 1
    assert adapter.last_metadata["rejected_applicability_mismatch"] == 1
    assert adapter.last_metadata["current_state_applied"] is True


def test_g2_legacy_stores_remain_isolated_under_current_state(tmp_path):
    legacy_path = tmp_path / "learning_closure.jsonl"
    legacy_path.write_text(
        '{"lesson_id":"lh-g2","task_id":"C_1","classification":"success",'
        '"summary":"legacy format owner","provenance":"receipt:jsonl"}\n',
        encoding="utf-8",
    )
    _write_ledger(
        tmp_path,
        [
            json.dumps(
                _with_applicability(_episode(idempotency_key="ep-g2-legacy"), state_version=9)
            )
        ],
    )
    composite = NexusCompositeLessonStore([
        LocalJsonlLessonStore(legacy_path),
        CanonicalEpisodicMemoryLessonStore(project_root=tmp_path),
    ])
    adapter = MemoryRetrievalAdapter(store=composite)

    lessons = adapter.retrieve(
        query_text="legacy format", limit=5, current_state={"state_version": 1}
    )

    assert [lesson.finding_id for lesson in lessons] == ["lh-g2"]
    assert adapter.last_metadata["retrieval_sources"] == ["LocalJsonlLessonStore"]
    assert adapter.last_metadata["rejected_applicability_mismatch"] == 1


def test_g2_unsupported_store_fails_closed_without_exception_leak(tmp_path):
    adapter = MemoryRetrievalAdapter(store=LocalJsonlLessonStore(tmp_path / "missing.jsonl"))

    lessons = adapter.retrieve(query_text="canonical", limit=5, current_state={"state_version": 1})

    assert lessons == []
    assert adapter.last_metadata["status"] == "current_state_unsupported"
    assert adapter.last_metadata["rejected_current_state_input"] == 1
    assert adapter.last_metadata["no_memory_match"] is True


def test_g3_later_contradict_masks_prior_canonical_episode(tmp_path):
    prior = _episode(idempotency_key="ep-g3-prior")
    invalidator = _episode(
        task_id="github-issue-g3-contradict",
        terminal_outcome="FAILED",
        terminal_evidence={"receipt": "receipt:g3-contradict", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        lesson_disposition="contradict",
        idempotency_key="ep-g3-contradict",
    )
    _write_ledger(tmp_path, [json.dumps(prior), json.dumps(invalidator)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_invalidated"] == 1
    assert store.last_metadata["invalidation_event_count"] == 1


def test_g3_later_quarantine_masks_prior_canonical_episode(tmp_path):
    prior = _episode(idempotency_key="ep-g3-quarantine-prior")
    quarantine = _episode(
        task_id="github-issue-g3-quarantine",
        terminal_outcome="FAILED",
        terminal_evidence={"receipt": "receipt:g3-quarantine", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        lesson_disposition="quarantine",
        idempotency_key="ep-g3-quarantine",
    )
    _write_ledger(tmp_path, [json.dumps(prior), json.dumps(quarantine)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_invalidated"] == 1
    assert store.last_metadata["invalidation_event_count"] == 1


def test_g3_later_retire_masks_prior_but_order_is_not_reversed(tmp_path):
    prior = _episode(idempotency_key="ep-g3-retire-prior")
    retire = _episode(
        task_id="github-issue-g3-retire",
        terminal_outcome="RETIRED",
        terminal_evidence={"receipt": "receipt:g3-retire", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        qualification={},
        lesson_disposition="retire",
        idempotency_key="ep-g3-retire",
    )
    _write_ledger(tmp_path, [json.dumps(retire), json.dumps(prior)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert [row["episode_id"] for row in rows] == [prior["episode_id"]]
    assert store.last_metadata["rejected_invalidated"] == 0
    assert store.last_metadata["invalidation_event_count"] == 0


def test_g3_tampered_invalidator_cannot_mask_prior_canonical_episode(tmp_path):
    prior = _episode(idempotency_key="ep-g3-tamper-prior")
    invalidator = _episode(
        task_id="github-issue-g3-tamper",
        terminal_outcome="FAILED",
        terminal_evidence={"receipt": "receipt:g3-tamper", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        lesson_disposition="contradict",
        idempotency_key="ep-g3-tamper",
    )
    invalidator["episode_id"] = "lep:000000000000000000000000"
    _write_ledger(tmp_path, [json.dumps(prior), json.dumps(invalidator)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert [row["episode_id"] for row in rows] == [prior["episode_id"]]
    assert store.last_metadata["rejected_invalidated"] == 0
    assert store.last_metadata["rejected_validation"] == 1


def test_g3_invalidation_event_count_truthful_cardinality_multiple_targets(tmp_path):
    """One invalidating episode targeting multiple prior episodes represents 1 event, 2 invalidated episodes."""
    prior_1 = _episode(idempotency_key="ep-g3-multi-1")
    prior_2 = _episode(idempotency_key="ep-g3-multi-2")
    invalidator = _episode(
        task_id="github-issue-g3-multi-invalidator",
        terminal_outcome="FAILED",
        terminal_evidence={"receipt": "receipt:g3-multi", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior_1["episode_id"], prior_2["episode_id"]],
        applied_lesson_ids=[prior_1["episode_id"], prior_2["episode_id"]],
        lesson_disposition="contradict",
        idempotency_key="ep-g3-multi-invalidator",
    )
    _write_ledger(tmp_path, [json.dumps(prior_1), json.dumps(prior_2), json.dumps(invalidator)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_invalidated"] == 2
    assert store.last_metadata["invalidation_event_count"] == 1
    assert store.last_metadata["invalidated_episode_count"] == 2


def test_g3_invalidation_event_count_preserves_multiple_events_for_one_target(tmp_path):
    """Two later invalidators of one episode are two events but one invalidated episode."""
    prior = _episode(idempotency_key="ep-g3-history-prior")
    first = _episode(
        task_id="github-issue-g3-history-first",
        terminal_outcome="FAILED",
        terminal_evidence={"receipt": "receipt:g3-history-first", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        lesson_disposition="contradict",
        idempotency_key="ep-g3-history-first",
    )
    second = _episode(
        task_id="github-issue-g3-history-second",
        terminal_outcome="RETIRED",
        terminal_evidence={"receipt": "receipt:g3-history-second", "verifier_status": "FAIL"},
        retrieved_lesson_ids=[prior["episode_id"]],
        applied_lesson_ids=[prior["episode_id"]],
        qualification={},
        lesson_disposition="retire",
        idempotency_key="ep-g3-history-second",
    )
    _write_ledger(tmp_path, [json.dumps(prior), json.dumps(first), json.dumps(second)])
    store = CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)

    rows = store.query(query_text="canonical", limit=5)

    assert rows == []
    assert store.last_metadata["rejected_invalidated"] == 1
    assert store.last_metadata["invalidation_event_count"] == 2
    assert store.last_metadata["invalidated_episode_count"] == 1


def test_adapter_fails_closed_when_receipt_binding_fails(tmp_path, monkeypatch):
    """Adapter retrieve/retrieve_reranked must fail closed if receipt binding fails."""
    import nexus.services.local_heal.memory_retrieval_adapter as mra

    _write_ledger(tmp_path, [json.dumps(_episode())])
    adapter = MemoryRetrievalAdapter(
        store=CanonicalEpisodicMemoryLessonStore(project_root=tmp_path)
    )

    # Force validate_retrieved_lesson_context_binding to fail
    monkeypatch.setattr(
        mra, "validate_retrieved_lesson_context_binding", lambda *args, **kwargs: False
    )

    lessons = adapter.retrieve(query_text="canonical", limit=5)
    assert lessons == []
    assert adapter.last_metadata["status"] == "binding_failed"
    assert adapter.last_metadata["failure_reason"] == "retrieval_receipt_binding_failed"
    assert adapter.last_metadata["accepted"] == 0

    reranked = adapter.retrieve_reranked(query_text="canonical", limit=5)
    assert reranked == []
    assert adapter.last_metadata["status"] == "binding_failed"
    assert adapter.last_metadata["failure_reason"] == "retrieval_receipt_binding_failed"
    assert adapter.last_metadata["accepted"] == 0
