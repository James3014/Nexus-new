import json
import os
import subprocess
from pathlib import Path

from scripts.ops.task_authority_freshness_check import validate


def _git(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Freshness Test")
    _git(repo, "config", "user.email", "freshness@example.test")
    (repo / "README").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "base")
    head = _git(repo, "rev-parse", "HEAD")
    tasks = repo / "tasks" / "campaign"
    tasks.mkdir(parents=True)
    card = tasks / "01-card.md"
    card.write_text(
        "# Card\n\n- task_id: `done-task`\n- status: INTEGRATED\n",
        encoding="utf-8",
    )
    index = tasks / "INDEX.md"
    index.write_text(
        """# Campaign\n\n## Ordered Cards\n1. [01-card.md](01-card.md) - `done-task`\n\n## Current Frontier\n`owner-gate`\n\n## Completed Cards\n- `done-task`: integrated at `HEAD_PLACEHOLDER`\n\n## Blocked Cards\n- `owner-gate`: owner decision required\n""".replace("HEAD_PLACEHOLDER", head[:12]),
        encoding="utf-8",
    )
    _git(repo, "add", "tasks")
    _git(repo, "commit", "-m", "add campaign authority")
    return repo, index, head


def test_fresh_index_passes_and_reports_worktree_identity(tmp_path):
    repo, index, _ = _repo(tmp_path)

    result = validate(repo, index)

    assert result["decision"] == "PASS"
    assert result["branch"] == "main"
    assert result["dirty"] is False
    assert result["current_frontier"] == "owner-gate"
    assert result["task_cards"][0]["task_id"] == "done-task"


def test_completed_frontier_is_blocked(tmp_path):
    repo, index, _ = _repo(tmp_path)
    index.write_text(index.read_text(encoding="utf-8").replace("`owner-gate`", "`done-task`", 1), encoding="utf-8")

    result = validate(repo, index)

    assert result["decision"] == "BLOCK"
    assert any(item["code"] == "CURRENT_FRONTIER_ALREADY_COMPLETED" for item in result["findings"])


def test_missing_card_is_blocked(tmp_path):
    repo, index, _ = _repo(tmp_path)
    (repo / "tasks/campaign/01-card.md").unlink()

    result = validate(repo, index)

    assert result["decision"] == "BLOCK"
    assert any(item["code"] == "TASK_CARD_MISSING" for item in result["findings"])


def test_non_ancestor_completed_commit_is_blocked(tmp_path):
    repo, index, base_head = _repo(tmp_path)
    _git(repo, "checkout", "-b", "side")
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    _git(repo, "add", "side.txt")
    _git(repo, "commit", "-m", "side-only")
    side_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "main")
    index.write_text(
        index.read_text(encoding="utf-8").replace(base_head[:12], side_commit[:12]),
        encoding="utf-8",
    )

    result = validate(repo, index)

    assert result["decision"] == "BLOCK"
    assert any(item["code"] == "COMPLETED_COMMIT_NOT_ANCESTOR" for item in result["findings"])


def test_nonterminal_card_hash_mismatch_is_blocked(tmp_path):
    repo, index, _ = _repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state = {
        "task_id": "done-task",
        "status": "WORKER_RUNNING",
        "task_card_path": str(repo / "tasks/campaign/01-card.md"),
        "task_card_hash": "0" * 64,
    }
    (state_dir / "done-task.json").write_text(json.dumps(state), encoding="utf-8")

    result = validate(repo, index, state_dir=state_dir)

    assert result["decision"] == "BLOCK"
    assert any(item["code"] == "STATE_CARD_HASH_MISMATCH" for item in result["findings"])


def test_retained_card_hash_mismatch_is_warning_only(tmp_path):
    repo, index, _ = _repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state = {
        "task_id": "done-task",
        "status": "RETAINED_FOR_REVIEW",
        "task_card_path": str(repo / "tasks/campaign/01-card.md"),
        "task_card_hash": "0" * 64,
    }
    (state_dir / "done-task.json").write_text(json.dumps(state), encoding="utf-8")

    result = validate(repo, index, state_dir=state_dir)

    assert result["decision"] == "WARN"
    assert any(item["code"] == "STATE_CARD_HASH_MISMATCH" for item in result["findings"])


def test_unrelated_lifecycle_state_is_ignored(tmp_path):
    repo, index, _ = _repo(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state = {
        "task_id": "other-campaign-task",
        "status": "RETAINED_FOR_REVIEW",
        "task_card_path": str(repo / "tasks/other-campaign/01-card.md"),
        "task_card_hash": "0" * 64,
    }
    (state_dir / "other-campaign-task.json").write_text(json.dumps(state), encoding="utf-8")

    result = validate(repo, index, state_dir=state_dir)

    assert result["decision"] == "PASS"
    assert result["lifecycle_checks"] == []
