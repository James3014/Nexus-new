"""Issue #430: exact-base artifacts must identify the evaluated PR head."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PR_HEAD_OR_PUSH_SHA = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
)
OLD_ARTIFACT_IDENTITY = "${{ github.sha }}"

WORKFLOWS = {
    "ruff": (".github/workflows/lint.yml", "Ruff"),
    "bandit": (".github/workflows/security.yml", "Bandit"),
    "pyright": (".github/workflows/typecheck.yml", "Pyright"),
    "wiki": (".github/workflows/wiki-governance.yml", "Wiki"),
}


def _workflow(gate: str) -> dict[str, Any]:
    path, _ = WORKFLOWS[gate]
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def _steps(gate: str) -> list[dict[str, Any]]:
    jobs = _workflow(gate)["jobs"]
    assert len(jobs) == 1
    return list(next(iter(jobs.values()))["steps"])


def _step(gate: str, name: str) -> dict[str, Any]:
    for step in _steps(gate):
        if step.get("name") == name:
            return step
    raise AssertionError(f"{gate}: missing workflow step {name!r}")


@pytest.mark.parametrize("gate", sorted(WORKFLOWS))
def test_checkout_head_evaluation_and_artifact_share_one_identity_contract(gate: str) -> None:
    """Every exact-base evidence artifact names the immutable revision evaluated."""
    _, tool = WORKFLOWS[gate]
    checkout = _step(gate, "Checkout exact head")
    upload = _step(gate, f"Upload {tool} evidence")

    assert checkout["with"]["ref"] == PR_HEAD_OR_PUSH_SHA
    assert upload["with"]["name"].endswith(PR_HEAD_OR_PUSH_SHA)
    assert upload["with"]["name"] != f"exact-base-{gate}-{OLD_ARTIFACT_IDENTITY}"
    assert OLD_ARTIFACT_IDENTITY not in upload["with"]["name"]

    head_bindings = [
        step.get("env", {}).get("HEAD_SHA")
        for step in _steps(gate)
        if "HEAD_SHA" in step.get("env", {})
    ]
    assert head_bindings, f"{gate}: no evaluation HEAD_SHA binding"
    assert head_bindings == [PR_HEAD_OR_PUSH_SHA] * len(head_bindings)


@pytest.mark.parametrize("gate", sorted(WORKFLOWS))
def test_old_merge_ref_artifact_identity_is_a_negative_witness(gate: str) -> None:
    """A pull-request artifact must not fall back to the synthetic merge ref."""
    _, tool = WORKFLOWS[gate]
    artifact_name = _step(gate, f"Upload {tool} evidence")["with"]["name"]
    assert artifact_name.count(PR_HEAD_OR_PUSH_SHA) == 1
    assert artifact_name.count(OLD_ARTIFACT_IDENTITY) == 0
