from __future__ import annotations

import pytest

from nexus.contracts.learning_experience import (
    build_nexus_learning_episode,
    validate_nexus_learning_episode,
)
from nexus.learning.outcome_memory import EpisodeOutcomeRecord


def test_episode_identity_and_stages_are_stable_and_fail_closed() -> None:
    kwargs = dict(
        task_id="task-1", attempt_id="attempt-1", action_id="action-1", source="learn_mode",
        terminal_outcome="SUCCEEDED", terminal_evidence={"verifier_status": "PASS"},
        retrieved_lesson_ids=["lesson-b", "lesson-a"], applied_lesson_ids=["lesson-a"],
        qualification={"repeatability": True, "prevention_rule": "rule", "authority_qualification": True},
    )
    first = build_nexus_learning_episode(**kwargs)
    second = build_nexus_learning_episode(**kwargs)
    assert first["schema"] == "nexus.learning_episode.v1"
    assert first["source_schema"] == "nexus.learning_episode.v1"
    assert first["episode_id"] == second["episode_id"]
    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["stages"]["outcome_measured"] is True
    assert first["stages"]["outcome_uplift_observed"] is False
    assert first["qualification_status"] == "QUALIFIED"


def test_applied_lessons_are_bounded_by_retrieval() -> None:
    episode = build_nexus_learning_episode(
        task_id="task-subset", retrieved_lesson_ids=["known"], applied_lesson_ids=["known", "forged"]
    )
    assert episode["applied_lesson_ids"] == ["known"]


def test_episode_without_terminal_evidence_cannot_claim_uplift() -> None:
    episode = build_nexus_learning_episode(
        task_id="task-2", attempt_id="attempt-1", action_id="action-1", source="router",
        terminal_outcome="SUCCEEDED", qualification={"uplift_observed": True},
    )
    assert episode["qualification_status"] == "UNQUALIFIED"
    assert episode["stages"]["outcome_uplift_observed"] is False

    status_only = build_nexus_learning_episode(
        task_id="task-status-only", terminal_outcome="SUCCEEDED", terminal_evidence={"status": "PASS"}
    )
    assert status_only["stages"]["outcome_measured"] is False
    episode["stages"]["outcome_uplift_observed"] = True
    with pytest.raises(ValueError, match="UPLIFT_WITHOUT_OUTCOME"):
        validate_nexus_learning_episode(episode)


def test_uplift_requires_paired_memory_verifiers_with_same_fingerprint() -> None:
    base = dict(
        task_id="paired", terminal_outcome="SUCCEEDED",
        qualification={"repeatability": True, "prevention_rule": "rule", "authority_qualification": True, "uplift_observed": True},
    )
    missing = build_nexus_learning_episode(**base, terminal_evidence={"verifier_status": "missing"})
    assert missing["stages"]["outcome_uplift_observed"] is False
    paired = {
        "task_fingerprint": "fp-1",
        "memory_off": {"task_fingerprint": "fp-1", "verifier_status": "fail", "artifact": "off.json"},
        "memory_on": {"task_fingerprint": "fp-1", "verifier_status": "pass", "artifact": "on.json"},
    }
    observed = build_nexus_learning_episode(**base, terminal_evidence={"paired_verifier": paired})
    assert observed["stages"]["outcome_uplift_observed"] is True
    mismatched = dict(paired, memory_on=dict(paired["memory_on"], task_fingerprint="other"))
    rejected = build_nexus_learning_episode(**base, terminal_evidence={"paired_verifier": mismatched})
    assert rejected["stages"]["outcome_uplift_observed"] is False

def test_outcome_memory_derives_stable_episode_id_and_keeps_evidence() -> None:
    record = EpisodeOutcomeRecord.from_task(
        task_id="task-3", task_type="bug", task_desc="desc", solved=True,
        wall_duration_sec=1, total_tokens_used=2, trust_mismatch=False,
        attempt_id="attempt-1", action_id="action-1", source_schema="nexus.learning_episode.v1",
        terminal_evidence={"verifier_status": "PASS"},
        receipts=[{"name": "repair", "selected": True, "invoked": True, "evidence_present": True, "gate_passed": True}],
    )
    assert record.episode_id.startswith("lep:")
    assert record.qualification_evidence_present is True
    assert record.stages["outcome_measured"] is True


def test_outcome_memory_bounds_applied_lessons_and_uplift_to_evidence() -> None:
    record = EpisodeOutcomeRecord.from_task(
        task_id="task-4", task_type="bug", task_desc="desc", solved=True,
        wall_duration_sec=1, total_tokens_used=2, trust_mismatch=False,
        retrieved_lesson_ids=["kept"], applied_lesson_ids=["kept", "forged"],
        terminal_evidence={"verifier_status": "pass"},
        stages={"outcome_uplift_observed": True},
    )
    assert record.applied_lesson_ids == ["kept"]
    assert record.stages["outcome_uplift_observed"] is False
