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
    "pr-bindings-preflight.yml",
    "pytest.yml",
    "security.yml",
    "trusted-deletion-anchor.yml",
    "trusted-dependency-contract.yml",
    "trusted-impact-gate.yml",
    "typecheck.yml",
    "wiki-governance.yml",
)
# Core-protected workflows change only with an Owner-signed manifest
# (.nexus-core/config.toml [deletion_exception].protected_paths).
PROTECTED = (
    "nexus-core-issue-completion.yml",
    "trusted-deletion-anchor.yml",
)
# Already own a concurrency policy.
UNTOUCHED = (
    "nexus-core-issue-completion.yml",
    "deletion-guard.yml",
    "fast-start-v2-invalidator.yml",
    "repository-intelligence.yml",
    # Own per-PR group (cancel-in-progress) plus a debounce step (#2012).
    "repository-intelligence-comment.yml",
    # Own per-PR group keyed by issue number too: comment runs must serialize (#2290).
    "review-record-present.yml",
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


def test_protected_workflows_keep_their_owner_signed_policies() -> None:
    config = (ROOT / ".nexus-core" / "config.toml").read_text(encoding="utf-8")
    for name in PROTECTED:
        assert f".github/workflows/{name}" in config
    # The Core gate keeps its own per-PR group (changed only with the Owner manifest).
    assert _load("nexus-core-issue-completion.yml")["concurrency"] == {
        "group": (
            "nexus-core-issue-completion-${{ github.event.pull_request.number || "
            "format('precheck-{0}-{1}', github.event.client_payload.head_sha, "
            "github.event.client_payload.issue_number) }}"
        ),
        "cancel-in-progress": True,
    }
    # The anchor keeps 'edited': its merge-lane binding lives in the PR body.
    anchor = _load("trusted-deletion-anchor.yml")
    assert "edited" in anchor[True]["pull_request_target"]["types"]


def test_core_issue_gate_is_not_rerun_by_body_edits() -> None:
    # A skipped required 'verify' job would report success, so 'edited' cannot be
    # narrowed to marker edits inside the workflow; it is dropped instead.
    gate = _load("nexus-core-issue-completion.yml")
    assert gate[True] == {
        "pull_request_target": {"types": ["opened", "synchronize", "reopened"]},
        # Precheck at agent completion (#2018); never re-run by PR body edits.
        "repository_dispatch": {"types": ["nexus-core-precheck"]},
    }
    assert gate["jobs"]["run"]["outputs"]["outcome"] == "${{ steps.gate.outputs.outcome }}"
    (verify_step,) = gate["jobs"]["verify"]["steps"]
    assert verify_step["with"]["gate-outcome"] == "${{ needs.run.outputs.outcome }}"


def test_every_pr_workflow_is_classified() -> None:
    pr_workflows = set()
    for path in WORKFLOWS.glob("*.yml"):
        # PyYAML parses the bare key `on` as boolean True.
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        triggers = doc.get("on", doc.get(True)) or {}
        if isinstance(triggers, dict) and {"pull_request", "pull_request_target"} & set(triggers):
            pr_workflows.add(path.name)
    assert pr_workflows <= set(CHANGED) | set(UNTOUCHED)


def _render_core_group(event: dict[str, Any]) -> str:
    """Render the Core gate's group for one event: `number || format(...)` only."""
    import re

    group = _load("nexus-core-issue-completion.yml")["concurrency"]["group"]
    match = re.fullmatch(
        r"nexus-core-issue-completion-\$\{\{ github\.event\.pull_request\.number \|\| "
        r"format\('([^']*)', ([^)]*)\) \}\}",
        group,
    )
    assert match, group
    number = (event.get("pull_request") or {}).get("number")
    if number:
        return f"nexus-core-issue-completion-{number}"
    values = []
    for arg in match.group(2).split(", "):
        node: Any = event
        assert arg.startswith("github.event."), arg
        for key in arg.removeprefix("github.event.").split("."):
            node = (node or {}).get(key)
        values.append("" if node is None else str(node))
    return "nexus-core-issue-completion-" + match.group(1).format(*values)


def test_core_precheck_group_is_per_head_and_issue() -> None:
    head = "a" * 40
    issue_5 = _render_core_group({"client_payload": {"head_sha": head, "issue_number": 5}})
    issue_7 = _render_core_group({"client_payload": {"head_sha": head, "issue_number": 7}})
    again_5 = _render_core_group({"client_payload": {"head_sha": head, "issue_number": 5}})
    other_head = _render_core_group({"client_payload": {"head_sha": "b" * 40, "issue_number": 5}})
    # Two Issues on the same head never cancel each other; a repeat for the same
    # head and Issue still supersedes the older run.
    assert issue_5 != issue_7
    assert issue_5 == again_5
    assert issue_5 != other_head
    assert issue_5 == f"nexus-core-issue-completion-precheck-{head}-5"
    # The pull_request path is unchanged: one group per PR number.
    pr = {"pull_request": {"number": 42}, "client_payload": {}}
    assert _render_core_group(pr) == "nexus-core-issue-completion-42"
