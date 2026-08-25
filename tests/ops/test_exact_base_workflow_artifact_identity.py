"""Issue #430: exact-base workflow artifact identity contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

EXACT_HEAD_EXPRESSION = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
)

WORKFLOWS: dict[str, dict[str, Any]] = {
    "ruff": {
        "workflow": ".github/workflows/lint.yml",
        "upload_step": "Upload Ruff evidence",
        "expected_artifact": f"exact-base-ruff-{EXACT_HEAD_EXPRESSION}",
        "rejected_artifact": "exact-base-ruff-${{ github.sha }}",
    },
    "bandit": {
        "workflow": ".github/workflows/security.yml",
        "upload_step": "Upload Bandit evidence",
        "expected_artifact": f"exact-base-bandit-{EXACT_HEAD_EXPRESSION}",
        "rejected_artifact": "exact-base-bandit-${{ github.sha }}",
    },
    "pyright": {
        "workflow": ".github/workflows/typecheck.yml",
        "upload_step": "Upload Pyright evidence",
        "expected_artifact": f"exact-base-pyright-{EXACT_HEAD_EXPRESSION}",
        "rejected_artifact": "exact-base-pyright-${{ github.sha }}",
    },
    "wiki": {
        "workflow": ".github/workflows/wiki-governance.yml",
        "upload_step": "Upload Wiki evidence",
        "expected_artifact": f"exact-base-wiki-{EXACT_HEAD_EXPRESSION}",
        "rejected_artifact": "exact-base-wiki-${{ github.sha }}",
    },
}


def _load_workflow(name: str) -> dict[str, Any]:
    path = REPO_ROOT / WORKFLOWS[name]["workflow"]
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(name: str) -> list[dict[str, Any]]:
    jobs = _load_workflow(name)["jobs"]
    assert len(jobs) == 1
    return list(jobs.values())[0]["steps"]


def _step(name: str, step_name: str) -> dict[str, Any]:
    for step in _steps(name):
        if step.get("name") == step_name:
            return step
    raise AssertionError(f"{name}: step {step_name!r} not found")


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_checkout_ref_uses_exact_head_expression(name: str) -> None:
    checkout = _step(name, "Checkout exact head")
    ref = checkout.get("with", {}).get("ref")
    assert ref == EXACT_HEAD_EXPRESSION


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_head_sha_binding_uses_exact_head_expression(name: str) -> None:
    impact = _step(name, "Decide cheap exact-base impact")
    assert impact.get("env", {}).get("HEAD_SHA") == EXACT_HEAD_EXPRESSION

    for step in _steps(name):
        if step.get("name") == "Resolve exact revisions and worktree":
            assert step.get("env", {}).get("HEAD_SHA") == EXACT_HEAD_EXPRESSION


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_upload_artifact_uses_exact_head_expression(name: str) -> None:
    cfg = WORKFLOWS[name]
    upload = _step(name, cfg["upload_step"])
    artifact_name = upload.get("with", {}).get("name")
    assert artifact_name == cfg["expected_artifact"]


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_upload_artifact_rejects_plain_github_sha(name: str) -> None:
    cfg = WORKFLOWS[name]
    upload = _step(name, cfg["upload_step"])
    artifact_name = upload.get("with", {}).get("name")
    assert artifact_name != cfg["rejected_artifact"]
    assert "${{ github.sha }}" not in artifact_name


@pytest.mark.parametrize("name", sorted(WORKFLOWS))
def test_workflow_shares_unified_exact_head_identity_contract(name: str) -> None:
    cfg = WORKFLOWS[name]
    checkout_ref = _step(name, "Checkout exact head").get("with", {}).get("ref")
    impact_head_sha = (
        _step(name, "Decide cheap exact-base impact").get("env", {}).get("HEAD_SHA")
    )
    artifact_name = _step(name, cfg["upload_step"]).get("with", {}).get("name")

    assert checkout_ref == EXACT_HEAD_EXPRESSION
    assert impact_head_sha == EXACT_HEAD_EXPRESSION
    assert artifact_name.endswith(EXACT_HEAD_EXPRESSION)
