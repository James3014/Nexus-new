"""PR-triggered workflows cancel superseded runs without touching main/scheduled runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
EXPECTED_GROUP = (
    "${{ github.workflow }}-pr-${{ github.event.pull_request.number || github.run_id }}"
)
CHANGED = (
    "fast-start-v2-shadow.yml",
    "git-history-secret-audit.yml",
    "lint.yml",
    "nexus-core-effectiveness-g1.yml",
    "policy-lane-gate.yml",
    "pytest.yml",
    "security.yml",
    "trusted-impact-gate.yml",
    "typecheck.yml",
    "wiki-governance.yml",
)
# Core-protected (needs Owner signature) or already own a concurrency policy.
UNTOUCHED = (
    "nexus-core-issue-completion.yml",
    "trusted-deletion-anchor.yml",
    "fast-start-v2-invalidator.yml",
    "repository-intelligence.yml",
)


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", CHANGED)
def test_pr_workflow_cancels_superseded_runs_per_pr(name: str) -> None:
    concurrency = _load(name)["concurrency"]
    assert concurrency == {"group": EXPECTED_GROUP, "cancel-in-progress": True}


@pytest.mark.parametrize("name", CHANGED)
def test_non_pr_events_never_share_a_group(name: str) -> None:
    # The fallback must be unique per run, never github.ref (would cancel main pushes).
    assert "github.ref" not in _load(name)["concurrency"]["group"]


def test_protected_workflows_are_not_modified_by_this_policy() -> None:
    config = (ROOT / ".nexus-core" / "config.toml").read_text(encoding="utf-8")
    for name in UNTOUCHED[:2]:
        assert f".github/workflows/{name}" in config
    assert "pull_request.number || github.run_id" not in (
        WORKFLOWS / "nexus-core-issue-completion.yml"
    ).read_text(encoding="utf-8")
    assert "concurrency" not in _load("trusted-deletion-anchor.yml")


def test_every_pr_workflow_is_classified() -> None:
    pr_workflows = set()
    for path in WORKFLOWS.glob("*.yml"):
        # PyYAML parses the bare key `on` as boolean True.
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        triggers = doc.get("on", doc.get(True)) or {}
        if isinstance(triggers, dict) and {"pull_request", "pull_request_target"} & set(triggers):
            pr_workflows.add(path.name)
    assert pr_workflows <= set(CHANGED) | set(UNTOUCHED)
