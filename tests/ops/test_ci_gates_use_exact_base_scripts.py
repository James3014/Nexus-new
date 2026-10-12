"""CI gates must not execute the candidate's own copy of the gate logic (#1754)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def _steps(workflow: str) -> list[dict]:
    data = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))
    return [step for job in data["jobs"].values() for step in job.get("steps", [])]


def test_secret_audit_runs_scanner_from_exact_base() -> None:
    scan = next(
        step
        for step in _steps("git-history-secret-audit.yml")
        if step.get("name") == "Run full-history secret scan"
    )
    run = scan["run"]
    assert "github.event.pull_request.base.sha" in run
    assert 'git show "$scanner_rev:scripts/ops/git_history_secret_scan.py"' in run
    assert 'python3 "$trusted_scanner"' in run
    assert "python3 scripts/ops/git_history_secret_scan.py" not in run


def test_exact_base_tool_gate_classifies_with_base_copy() -> None:
    for workflow in ("lint.yml", "security.yml", "typecheck.yml", "wiki-governance.yml"):
        runs = [step.get("run", "") for step in _steps(workflow)]
        invocations = [run for run in runs if "exact_base_tool_gate.py" in run and "--tool" in run]
        assert invocations, workflow
        for run in invocations:
            assert (
                '"${{ steps.revisions.outputs.base_worktree }}/scripts/ops/exact_base_tool_gate.py"'
                in run
            ), workflow
            assert ".venv/bin/python scripts/ops/exact_base_tool_gate.py" not in run, workflow


def test_bandit_and_pyright_impact_cover_runtime_code() -> None:
    for workflow in ("security.yml", "typecheck.yml"):
        text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
        assert "'nexus/**/*.py'" in text, workflow
        assert "'scripts/ops/**/*.py'" in text, workflow
        assert "-- 'nexus/core/*.py' 'nexus/core/**/*.py'" not in text, workflow


def _git_in(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _init_scan_repo(repo: Path) -> None:
    _git_in(repo, "init", "-q", "-b", "main")
    _git_in(repo, "config", "user.email", "t@t")
    _git_in(repo, "config", "user.name", "t")


def test_secret_audit_step_blocks_pat_even_when_candidate_patches_scanner(tmp_path) -> None:
    """The base-revision scanner still blocks a token when the candidate patches its own copy."""
    scanner_src = (ROOT / "scripts/ops/git_history_secret_scan.py").read_text(encoding="utf-8")
    repo = tmp_path / "r"
    (repo / "scripts/ops").mkdir(parents=True)
    _init_scan_repo(repo)
    (repo / "scripts/ops/git_history_secret_scan.py").write_text(scanner_src)
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-qm", "base")
    base = _git_in(repo, "rev-parse", "HEAD")
    (repo / "leak.txt").write_text("tok=ghp_" + "Z" * 36 + "\n")
    (repo / "scripts/ops/git_history_secret_scan.py").write_text(
        scanner_src.replace(
            "blocking = [item for item in ordered if item.blocking]", "blocking = []"
        )
    )
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-qm", "head")
    _git_in(repo, "remote", "add", "origin", str(repo))
    _git_in(repo, "update-ref", "refs/remotes/origin/pr", "HEAD")
    trusted = tmp_path / "trusted_scan.py"
    trusted.write_text(
        _git_in(repo, "show", f"{base}:scripts/ops/git_history_secret_scan.py") + "\n"
    )
    out = tmp_path / "scan.json"
    subprocess.run(
        [sys.executable, str(trusted), "--repo", str(repo), "--output", str(out)],
        capture_output=True,
    )
    payload = json.loads(out.read_text())
    assert payload["status"] != "PASS" and payload["blocking_finding_count"] >= 1
    # The candidate's own patched copy would have passed, so the check is sensitive.
    subprocess.run(
        [
            sys.executable,
            str(repo / "scripts/ops/git_history_secret_scan.py"),
            "--repo",
            str(repo),
            "--output",
            str(out),
        ],
        capture_output=True,
    )
    assert json.loads(out.read_text())["blocking_finding_count"] == 0


def test_scanner_blocks_anthropic_key_in_history(tmp_path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_scan_repo(repo)
    (repo / "cfg.txt").write_text("ANTHROPIC=sk-" + "ant-api03-" + "Q" * 90 + "AA\n")
    _git_in(repo, "add", "-A")
    _git_in(repo, "commit", "-qm", "k")
    _git_in(repo, "remote", "add", "origin", str(repo))
    _git_in(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    out = tmp_path / "scan.json"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/git_history_secret_scan.py"),
            "--repo",
            str(repo),
            "--output",
            str(out),
        ],
        capture_output=True,
    )
    payload = json.loads(out.read_text())
    assert payload["status"] != "PASS" and payload["blocking_finding_count"] >= 1
