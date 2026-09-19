"""Regression guard for exact-base CI disk cleanup before head tests."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"


def _impact_steps() -> list[dict[str, object]]:
    payload = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return list(payload["jobs"]["impact-gate"]["steps"])


def _step(name: str) -> dict[str, object]:
    for step in _impact_steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"missing workflow step: {name}")


def test_exact_base_resources_are_released_before_exact_head() -> None:
    names = [str(step.get("name", "")) for step in _impact_steps()]
    base_index = names.index("Run mapped tests on exact base source")
    release_index = names.index("Release exact-base resources before exact head")
    head_index = names.index("Run mapped tests on exact head")
    assert base_index < release_index < head_index

    run = str(_step("Release exact-base resources before exact head")["run"])
    assert 'git worktree remove --force "$BASE_WORKTREE"' in run
    assert "git worktree prune" in run
    assert "uv cache clean" in run
    assert 'df -h "$RUNNER_TEMP" "$GITHUB_WORKSPACE"' in run


def test_final_exact_base_cleanup_is_idempotent_after_early_release() -> None:
    run = str(_step("Remove exact base worktree")["run"])
    assert 'if [ -d "$BASE_WORKTREE" ]; then' in run
    assert 'git worktree remove --force "$BASE_WORKTREE"' in run
    assert "git worktree prune" in run
