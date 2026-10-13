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
    assert "BASE_SHA" in run
    assert '"$scanner_rev:$script_path"' in run
    assert 'python3 "$trusted_scanner"' in run
    assert "python3 scripts/ops/git_history_secret_scan.py" not in run


def _audit_workflow() -> dict:
    return yaml.safe_load((WORKFLOWS / "git-history-secret-audit.yml").read_text(encoding="utf-8"))


def test_secret_audit_runs_from_default_branch_workflow() -> None:
    data = _audit_workflow()
    # PyYAML parses the bare key `on` as boolean True.
    triggers = data.get("on", data.get(True))
    assert "pull_request_target" in triggers
    assert "pull_request" not in triggers
    assert triggers["pull_request_target"]["branches"] == ["main"]
    assert {"push", "schedule", "workflow_dispatch"} <= set(triggers)
    job = data["jobs"]["full-history-secret-audit"]
    assert job["name"] == "Full published Git history secret audit"


def test_secret_audit_is_read_only_and_never_executes_pr_content() -> None:
    data = _audit_workflow()
    assert data["permissions"] == {"contents": "read"}
    job = data["jobs"]["full-history-secret-audit"]
    assert "permissions" not in job
    text = (WORKFLOWS / "git-history-secret-audit.yml").read_text(encoding="utf-8")
    assert "actions/checkout" not in text  # no PR-controlled workspace at all
    assert "persist-credentials: true" not in text
    for forbidden in ("uv sync", "PYTHONPATH", "pip install", "requirements", "./scripts"):
        assert forbidden not in text
    for step in job["steps"]:
        for line in step.get("run", "").splitlines():
            stripped = line.strip()
            # Only the base-extracted scanner and inline -c code may run Python.
            if stripped.startswith(("python", "bash ", "sh ", "./")):
                assert stripped.startswith(('python3 "$trusted_scanner"', "python3 -c ")), line
    # fork PR heads are fetched as data through the pull ref
    assert "refs/pull/$PR_NUMBER/head" in text


def test_secret_audit_scanner_comes_from_base_sha_with_pr_head_binding() -> None:
    steps = _steps("git-history-secret-audit.yml")
    fetch = next(s for s in steps if s.get("name", "").startswith("Fetch every published"))
    scan = next(s for s in steps if s.get("name") == "Run full-history secret scan")
    assert scan["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert scan["env"]["PUSH_SHA"] == "${{ github.sha }}"
    assert fetch["env"]["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert 'scanner_rev="$BASE_SHA"' in scan["run"]
    assert '"$scanner_rev:$script_path"' in scan["run"]
    assert "scripts/ops/git_history_secret_scan.py" in scan["run"]
    assert 'cat-file blob "$script_blob_id"' in scan["run"]
    assert "100644 blob $script_blob_id" in scan["run"]
    assert "published ref collides with PR head data ref" in fetch["run"]
    assert fetch["run"].index("show-ref --verify") < fetch["run"].index("refs/pull/$PR_NUMBER/head")
    assert 'p["source_revision"] == sys.argv[1]' in scan["run"]
    assert 'p["published_ref_snapshot_sha256"] == sys.argv[2]' in scan["run"]


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
