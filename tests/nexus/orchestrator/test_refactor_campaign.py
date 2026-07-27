from pathlib import Path

import pytest

from nexus.orchestrator.refactor_campaign import RefactorCampaignCoordinator, RefactorWave


def test_campaign_advances_waves_from_competition_to_checkpointed_integration(tmp_path):
    class FakeCompetition:
        state_dir = tmp_path / "competition-state"

        def __init__(self):
            self.counter = 0

        def submit(self, request, providers):
            self.counter += 1
            return {"competition_id": f"competition-{self.counter}", "status": "SUBMITTED"}

        def get(self, competition_id):
            return {"competition_id": competition_id, "status": "WINNER_SELECTED"}

        def integrate_winner(self, competition_id, integration_branch):
            return {
                "competition_id": competition_id,
                "status": "INTEGRATED",
                "integration": {
                    "integration_commit_sha": "b" * 40,
                },
            }

    coordinator = RefactorCampaignCoordinator(FakeCompetition(), state_dir=tmp_path / "campaigns")
    state = coordinator.create(
        "repo-refactor",
        {
            "controller_repo_root": str(tmp_path / "repo"),
            "target_worktree_root": str(tmp_path / "targets"),
            "target_base_revision": "a" * 40,
        },
        [
            RefactorWave("wave-1", "refactor module one", ("nexus/a.py",)),
            RefactorWave("wave-2", "refactor module two", ("nexus/b.py",)),
        ],
        ["codex", "opencode"],
    )
    assert state["status"] == "READY"

    running = coordinator.advance("repo-refactor")
    assert running["status"] == "WAVE_RUNNING"
    complete_one = coordinator.advance("repo-refactor")
    assert complete_one["status"] == "WAVE_COMPLETE"
    assert complete_one["base_request"]["target_base_revision"] == "b" * 40
    running_two = coordinator.advance("repo-refactor")
    assert running_two["status"] == "WAVE_RUNNING"


def test_campaign_rejects_unbounded_or_invalid_wave_scope(tmp_path):
    coordinator = RefactorCampaignCoordinator(object(), state_dir=tmp_path / "campaigns")

    with pytest.raises(ValueError, match="bounded"):
        coordinator.create(
            "bad",
            {},
            [RefactorWave("wave", "bad", tuple(f"file-{i}" for i in range(3)))],
            ["codex", "opencode"],
            max_scope_entries=2,
        )
