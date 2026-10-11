"""Behavioral contract for the Claude Code HANDOFF.md hooks under .claude/."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _hook(repo: Path, name: str, payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    return subprocess.run(
        ["bash", str(repo / ".claude" / "hooks" / name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=repo,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    shutil.copytree(HOOKS, tmp_path / ".claude" / "hooks")
    (tmp_path / "a.txt").write_text("a\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "init")
    head = _git(tmp_path, "rev-parse", "--short", "HEAD")
    (tmp_path / "HANDOFF.md").write_text(f"# HANDOFF\n更新 · HEAD `{head}`\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "handoff")
    return tmp_path


def test_settings_wire_session_start_and_stop_hooks() -> None:
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    commands = {
        event: [h["command"] for entry in settings["hooks"][event] for h in entry["hooks"]]
        for event in ("SessionStart", "Stop")
    }
    assert any("handoff-inject.sh" in c for c in commands["SessionStart"])
    assert any("handoff-check.sh" in c for c in commands["Stop"])


def test_inject_prints_handoff_without_drift_for_handoff_only_commit(repo: Path) -> None:
    result = _hook(repo, "handoff-inject.sh", {"session_id": "s1"})
    assert result.returncode == 0
    assert "# HANDOFF" in result.stdout
    assert "內容可能已過期" not in result.stdout


def test_inject_reports_code_commits_after_recorded_head(repo: Path) -> None:
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-qm", "code")
    result = _hook(repo, "handoff-inject.sh", {"session_id": "s1"})
    assert "之後還有 1 個 commit" in result.stdout


def test_stop_blocks_once_when_code_changed_without_handoff(repo: Path) -> None:
    _hook(repo, "handoff-inject.sh", {"session_id": "s1"})
    assert _hook(repo, "handoff-check.sh", {"session_id": "s1"}).returncode == 0

    (repo / "a.txt").write_text("changed\n")
    blocked = _hook(repo, "handoff-check.sh", {"session_id": "s1", "stop_hook_active": False})
    assert blocked.returncode == 2
    assert "HANDOFF.md 尚未更新" in blocked.stderr

    again = _hook(repo, "handoff-check.sh", {"session_id": "s1", "stop_hook_active": True})
    assert again.returncode == 0

    with (repo / "HANDOFF.md").open("a") as handle:
        handle.write("- updated\n")
    assert _hook(repo, "handoff-check.sh", {"session_id": "s1"}).returncode == 0


def test_stop_blocks_oversized_handoff(repo: Path) -> None:
    _hook(repo, "handoff-inject.sh", {"session_id": "s1"})
    with (repo / "HANDOFF.md").open("a") as handle:
        handle.write("x\n" * 200)
    result = _hook(repo, "handoff-check.sh", {"session_id": "s1"})
    assert result.returncode == 2
    assert "150" in result.stderr
