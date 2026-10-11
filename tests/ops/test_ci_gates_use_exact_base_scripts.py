"""CI gates must not execute the candidate's own copy of the gate logic (#1754)."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


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
