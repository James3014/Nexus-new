from __future__ import annotations

import json
from importlib.metadata import distribution
from pathlib import Path

import nexus_learning.closure_effectiveness as canonical_closure
import nexus_learning.contracts as canonical_contracts
import nexus_learning.episode_projection as canonical_projection
import nexus_learning.outcome_memory as canonical_memory
from nexus.contracts import learning_experience as legacy_contracts
from nexus.learning import learning_closure_effectiveness as legacy_closure
from nexus.learning import learning_episode_projection as legacy_projection
from nexus.learning import outcome_memory as legacy_memory

CANONICAL_LEARNING_COMMIT = "3b8ece75fac4d2554245c29590748a84c5c671d5"


def test_forwarding_facades_bind_canonical_symbol_identity() -> None:
    assert legacy_contracts.LearningExperience is canonical_contracts.LearningExperience
    assert legacy_memory.OutcomeMemoryManager is canonical_memory.OutcomeMemoryManager
    assert legacy_memory.EpisodeOutcomeRecord is canonical_memory.EpisodeOutcomeRecord
    assert legacy_projection.project_learning_entries is canonical_projection.project_learning_entries
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
