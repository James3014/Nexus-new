"""CLI contract tests for the session-independent workflow doctor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts" / "engine" / "nexus_cli.py"
ENTRYPOINT = ROOT / "scripts" / "ops" / "nexus-workflow-doctor"


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "workflow-doctor@example.invalid")
    _git(repo, "config", "user.name", "Workflow Doctor")
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "fixture")
    return repo


def _env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(ROOT)
    env["NEXUS_WORKFLOW_DOCTOR_SNAPSHOT"] = str(ROOT)
    return env


def test_standalone_workflow_doctor_emits_json(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = subprocess.run(
        [str(ENTRYPOINT), "--json", "--repo-root", str(repo)],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "nexus.workflow_doctor.v1"
    assert payload["source"]["status"] == "OBSERVED"
    assert payload["claim_ceiling"] == "READ_ONLY_WORKFLOW_OBSERVATION"


def test_nexus_workflow_doctor_works_without_legacy_extra(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "workflow",
            "doctor",
            "--json",
            "--repo-root",
            str(repo),
        ],
        cwd=ROOT,
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema"] == "nexus.workflow_doctor.v1"
    assert payload["source"]["status"] == "OBSERVED"
