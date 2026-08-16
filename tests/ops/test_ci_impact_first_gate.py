"""Issue #336: cheap-impact-first exact-base CI gate contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

GATES: dict[str, dict[str, Any]] = {
    "ruff": {
        "workflow": ".github/workflows/lint.yml",
        "guards": ("pyproject.toml", "ruff.toml"),
        "no_impact_step": "Record no Ruff impact",
        "reason": "no Ruff-impacted paths changed",
    },
    "bandit": {
        "workflow": ".github/workflows/security.yml",
        "guards": ("pyproject.toml", ".bandit", "bandit.yaml"),
        "no_impact_step": "Record no Bandit impact",
        "reason": "no Bandit-impacted paths changed",
    },
    "pyright": {
        "workflow": ".github/workflows/typecheck.yml",
        "guards": ("pyproject.toml", "pyrightconfig.json", "uv.lock"),
        "no_impact_step": "Record no Pyright impact",
        "reason": "no Pyright-impacted paths changed",
    },
    "wiki": {
        "workflow": ".github/workflows/wiki-governance.yml",
        "guards": ("pyproject.toml", "uv.lock"),
        "no_impact_step": "Record non-Wiki impact",
        "reason": "no Wiki-governed paths changed",
        "shared": (
            "scripts/ops/exact_base_tool_gate.py",
            "scripts/ops/wiki_ci_release_gate.py",
        ),
    },
}

IMPACT_STEP = "Decide cheap exact-base impact"
INSTALL_STEP = "Install uv and dependencies"
REQUIRED_TRUE = "steps.impact.outputs.required == 'true'"
REQUIRED_FALSE = "steps.impact.outputs.required != 'true'"


def _load(gate: str) -> dict[str, Any]:
    path = REPO_ROOT / GATES[gate]["workflow"]
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(gate: str) -> list[dict[str, Any]]:
    jobs = _load(gate)["jobs"]
    assert len(jobs) == 1
    return list(jobs.values())[0]["steps"]


def _step(gate: str, name: str) -> dict[str, Any]:
    for step in _steps(gate):
        if step.get("name") == name:
            return step
    raise AssertionError(f"{gate}: step {name!r} not found")


def _triggers(gate: str) -> dict[str, Any]:
    workflow = _load(gate)
    for key in ("on", True):
        if key in workflow:
            return workflow[key]
    raise AssertionError(f"{gate}: missing workflow trigger block")


@pytest.mark.parametrize("gate", sorted(GATES))
def test_impact_decision_precedes_dependency_install(gate: str) -> None:
    names = [step.get("name", "") for step in _steps(gate)]
    assert names.index(IMPACT_STEP) < names.index(INSTALL_STEP)
    assert _step(gate, INSTALL_STEP).get("if") == REQUIRED_TRUE


@pytest.mark.parametrize("gate", sorted(GATES))
def test_no_impact_pr_skips_install_and_emits_pass(gate: str) -> None:
    no_impact = _step(gate, GATES[gate]["no_impact_step"])
    assert no_impact.get("if") == REQUIRED_FALSE
    run = no_impact["run"]
    assert '"classification":"PASS"' in run
    assert '"blocking":false' in run
    assert GATES[gate]["reason"] in run


@pytest.mark.parametrize("gate", sorted(GATES))
def test_guard_changes_force_full_gate(gate: str) -> None:
    impact = _step(gate, IMPACT_STEP)["run"]
    for guard in GATES[gate]["guards"]:
        assert guard in impact


@pytest.mark.parametrize("gate", sorted(GATES))
def test_shared_classifier_change_forces_full_gate(gate: str) -> None:
    impact = _step(gate, IMPACT_STEP)["run"]
    shared = GATES[gate].get("shared", ("scripts/ops/exact_base_tool_gate.py",))
    for path in shared:
        assert path in impact


@pytest.mark.parametrize("gate", sorted(GATES))
def test_unknown_identity_cannot_skip_gate(gate: str) -> None:
    impact = _step(gate, IMPACT_STEP)["run"]
    assert "[0-9a-f]{40}" in impact
    assert "exit 1" in impact
    assert 'test "$(git rev-parse HEAD)" = "$HEAD_SHA"' in impact
    assert _step(gate, INSTALL_STEP).get("if") == REQUIRED_TRUE


@pytest.mark.parametrize("gate", sorted(GATES))
def test_push_and_workflow_dispatch_run_full_gate(gate: str) -> None:
    triggers = _triggers(gate)
    assert "push" in triggers
    assert "workflow_dispatch" in triggers
    impact = _step(gate, IMPACT_STEP)["run"]
    assert "GITHUB_EVENT_NAME" in impact
    assert '"pull_request"' in impact
    assert 'echo "required=true"' in impact


@pytest.mark.parametrize("gate", sorted(GATES))
def test_exact_base_execution_and_failure_reporting_preserved(gate: str) -> None:
    steps = _steps(gate)
    run_steps = [s for s in steps if "on exact base and head" in s.get("name", "")]
    assert len(run_steps) == 1
    assert run_steps[0].get("if") == REQUIRED_TRUE
    classify = [s for s in steps if s.get("name", "").startswith("Classify")]
    assert len(classify) == 1
    assert classify[0].get("if") == REQUIRED_TRUE
    classify_run = classify[0]["run"]
    assert "scripts/ops/exact_base_tool_gate.py" in classify_run
    assert "--base" in classify_run and "--head" in classify_run
    cleanup = [s for s in steps if s.get("name") == "Remove exact base worktree"]
    assert len(cleanup) == 1
    assert cleanup[0].get("if", "").startswith("always()")


def test_evidence_defaults_to_blocking_before_decision() -> None:
    for gate in sorted(GATES):
        first = _steps(gate)[0]
        assert first.get("name") == "Initialize evidence"
        assert "CI_BOOTSTRAP_DEFECT" in first["run"]
