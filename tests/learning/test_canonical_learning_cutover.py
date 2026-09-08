from __future__ import annotations

import json
from importlib.metadata import distribution
from pathlib import Path

import nexus_learning.closure_effectiveness as canonical_closure
import nexus_learning.contracts as canonical_contracts
import nexus_learning.episode_projection as canonical_projection
import nexus_learning.outcome_memory as canonical_memory
import pytest

from nexus.contracts import learning_experience as legacy_contracts
from nexus.learning import learning_closure_effectiveness as legacy_closure
from nexus.learning import learning_episode_projection as legacy_projection
from nexus.learning import outcome_memory as legacy_memory

CANONICAL_LEARNING_COMMIT = "8d29d31db63eccfda707e76cad31d88f2814b42d"


def test_forwarding_facades_bind_canonical_symbol_identity() -> None:
    assert legacy_contracts.LearningExperience is canonical_contracts.LearningExperience
    assert legacy_memory.OutcomeMemoryManager is canonical_memory.OutcomeMemoryManager
    assert legacy_memory.EpisodeOutcomeRecord is canonical_memory.EpisodeOutcomeRecord
    assert (
        legacy_projection.project_learning_entries is canonical_projection.project_learning_entries
    )
    assert (
        legacy_closure.canonical_learning_episode_path
        is canonical_closure.canonical_learning_episode_path
    )
    assert legacy_closure.append_learning_episode is canonical_closure.append_learning_episode


def test_installed_canonical_learning_is_exact_git_commit() -> None:
    dist = distribution("nexus-learning")
    direct_url = dist.read_text("direct_url.json")
    assert direct_url, "nexus-learning must be installed from the exact canonical Git source"
    provenance = json.loads(direct_url)
    assert provenance.get("vcs_info", {}).get("vcs") == "git"
    assert provenance.get("vcs_info", {}).get("commit_id") == CANONICAL_LEARNING_COMMIT
    assert provenance.get("vcs_info", {}).get("requested_revision") == CANONICAL_LEARNING_COMMIT


def test_explicit_state_root_is_single_writer_and_cwd_independent(
    tmp_path: Path, monkeypatch
) -> None:
    project_root = tmp_path / "canonical-project"
    unrelated_cwd = tmp_path / "unrelated-cwd"
    project_root.mkdir()
    unrelated_cwd.mkdir()
    monkeypatch.chdir(unrelated_cwd)

    record = legacy_memory.EpisodeOutcomeRecord.from_task(
        task_id="g8-learning-cutover",
        task_type="consumer-cutover",
        task_desc="prove canonical Learning single-writer state-root binding",
        solved=True,
        wall_duration_sec=1.0,
        total_tokens_used=1,
        trust_mismatch=False,
        idempotency_key="g8-learning-cutover-idempotency",
        terminal_outcome="SUCCEEDED",
        qualification_evidence_present=True,
        terminal_evidence={"verifier_status": "PASS"},
    )

    first = legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
        record, project_root=project_root
    )
    duplicate = legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
        record, project_root=project_root
    )

    assert first["status"] == "PASS"
    assert duplicate["status"] == "IDEMPOTENT_DUPLICATE"

    outcome_path = project_root / ".nexus" / "memory" / "outcome_history.jsonl"
    assert outcome_path.is_file()
    assert len(outcome_path.read_text(encoding="utf-8").splitlines()) == 1
    assert not (unrelated_cwd / ".nexus").exists()


def _record(task_id: str, idempotency_key: str) -> legacy_memory.EpisodeOutcomeRecord:
    return legacy_memory.EpisodeOutcomeRecord.from_task(
        task_id=task_id,
        task_type="consumer-cutover",
        task_desc="canonical consumer tail boundary",
        solved=True,
        wall_duration_sec=1.0,
        total_tokens_used=1,
        trust_mismatch=False,
        idempotency_key=idempotency_key,
        terminal_outcome="SUCCEEDED",
        qualification_evidence_present=True,
    )


def test_facade_preserves_canonical_history_and_policy_across_unterminated_tail(
    tmp_path: Path,
) -> None:
    first = _record("A", "key-A")
    second = _record("B", "key-B")
    third = _record("C", "key-C")
    state_root = legacy_memory.LearningStateRoot.from_project_root(tmp_path)

    legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(first, project_root=state_root)
    storage = state_root.outcome_history_path
    storage.write_bytes(
        storage.read_bytes() + json.dumps(second.to_dict(), sort_keys=True).encode("utf-8")
    )
    result = legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
        third, project_root=state_root
    )

    rows = legacy_memory.OutcomeMemoryManager.load_recent_records(project_root=state_root)
    assert [row["task_id"] for row in rows] == ["A", "B", "C"]
    assert result["policy"]["source_experiences"] == ["A", "B", "C"]
    policy = json.loads(state_root.dynamic_policy_path.read_text(encoding="utf-8"))
    assert policy["source_experiences"] == ["A", "B", "C"]


def test_facade_duplicate_retry_does_not_append_second_record(tmp_path: Path) -> None:
    state_root = legacy_memory.LearningStateRoot.from_project_root(tmp_path)
    first_record = _record("A", "key-A")
    record = _record("C", "key-C")

    legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
        first_record, project_root=state_root
    )
    storage = state_root.outcome_history_path
    storage.write_bytes(storage.read_bytes().rstrip(b"\n"))
    legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(record, project_root=state_root)
    history_before = storage.read_bytes()
    duplicate = legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
        record, project_root=state_root
    )

    rows = legacy_memory.OutcomeMemoryManager.load_recent_records(project_root=state_root)
    assert duplicate["status"] == "IDEMPOTENT_DUPLICATE"
    assert [row["task_id"] for row in rows] == ["A", "C"]
    assert storage.read_bytes() == history_before
    policy = json.loads(state_root.dynamic_policy_path.read_text(encoding="utf-8"))
    assert policy["source_experiences"] == ["A", "C"]


@pytest.mark.parametrize("tail", [b'{"task_id":"partial"', b"[]", b"not-json"])
def test_facade_rejects_corrupt_unterminated_tail_without_mutation_or_policy(
    tmp_path: Path, tail: bytes
) -> None:
    state_root = legacy_memory.LearningStateRoot.from_project_root(tmp_path)
    storage = state_root.outcome_history_path
    storage.parent.mkdir(parents=True)
    storage.write_bytes(tail)
    policy_before = b'{"status":"existing-policy"}\n'
    state_root.dynamic_policy_path.write_bytes(policy_before)
    history_before = storage.read_bytes()

    with pytest.raises(ValueError, match="OUTCOME_HISTORY_TAIL_INVALID"):
        legacy_memory.OutcomeMemoryManager.save_episode_and_tune_sync(
            _record("new", "new-key"), project_root=state_root
        )

    assert storage.read_bytes() == history_before
    assert state_root.dynamic_policy_path.read_bytes() == policy_before


def _closure_episode(episode_id: str) -> dict[str, object]:
    episode = legacy_closure.normalize_learning_episode(
        task_id=episode_id, attempt_id=f"attempt-{episode_id}"
    )
    episode["episode_id"] = episode_id
    return episode


def test_closure_facade_preserves_rows_across_unterminated_tail(tmp_path: Path) -> None:
    first = _closure_episode("A")
    second = _closure_episode("B")
    third = _closure_episode("C")
    path = legacy_closure.canonical_learning_episode_path(tmp_path)

    assert legacy_closure.append_learning_episode(path, first) is True
    path.write_bytes(path.read_bytes() + json.dumps(second).encode("utf-8"))
    assert legacy_closure.append_learning_episode(path, third) is True

    rows = legacy_closure.load_canonical_learning_episodes(tmp_path)
    assert [row["episode_id"] for row in rows] == ["A", "B", "C"]


def test_closure_facade_duplicate_after_tail_repair_is_idempotent(tmp_path: Path) -> None:
    first = _closure_episode("A")
    second = _closure_episode("B")
    path = legacy_closure.canonical_learning_episode_path(tmp_path)

    assert legacy_closure.append_learning_episode(path, first) is True
    path.write_bytes(path.read_bytes() + json.dumps(second).encode("utf-8"))
    assert legacy_closure.append_learning_episode(path, _closure_episode("C")) is True
    before = path.read_bytes()

    assert legacy_closure.append_learning_episode(path, _closure_episode("C")) is True
    assert path.read_bytes() == before
    assert [
        row["episode_id"] for row in legacy_closure.load_canonical_learning_episodes(tmp_path)
    ] == [
        "A",
        "B",
        "C",
    ]


@pytest.mark.parametrize("tail", [b'{"episode_id":"partial"', b"not-json", b"[]"])
def test_closure_facade_rejects_invalid_unterminated_tail_preserving_bytes(
    tmp_path: Path, tail: bytes
) -> None:
    path = legacy_closure.canonical_learning_episode_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tail)
    before = path.read_bytes()

    assert legacy_closure.append_learning_episode(path, _closure_episode("C")) is False
    assert path.read_bytes() == before
