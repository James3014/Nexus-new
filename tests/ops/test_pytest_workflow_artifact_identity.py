"""Issue #424: pytest exact-base impact artifact identity contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/pytest.yml"

EXACT_HEAD_EXPRESSION = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
)
OLD_ARTIFACT_NAME = "exact-base-impact-${{ github.sha }}"


def _load_workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps_from_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow["jobs"]["impact-gate"]["steps"]


def _steps() -> list[dict[str, Any]]:
    return _steps_from_workflow(_load_workflow())


def _step_from_workflow(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    for step in _steps_from_workflow(workflow):
        if step.get("name") == name:
            return step
    raise AssertionError(f"pytest workflow step {name!r} not found")


def _step(name: str) -> dict[str, Any]:
    return _step_from_workflow(_load_workflow(), name)


def _triggers(workflow: dict[str, Any]) -> dict[str, Any]:
    # PyYAML's YAML 1.1 loader parses the unquoted `on` key as True.
    return workflow.get("on", workflow.get(True))


def _artifact_name() -> str:
    return _step("Archive impact evidence 📦")["with"]["name"]


def _assert_exact_head_identity_contract(workflow: dict[str, Any]) -> None:
    checkout_ref = _step_from_workflow(workflow, "Checkout exact head")["with"]["ref"]
    resolved_head = _step_from_workflow(workflow, "Resolve exact comparison base")["env"][
        "HEAD_SHA"
    ]
    artifact_name = _step_from_workflow(workflow, "Archive impact evidence 📦")["with"]["name"]

    assert checkout_ref == EXACT_HEAD_EXPRESSION
    assert resolved_head == EXACT_HEAD_EXPRESSION
    assert artifact_name == f"exact-base-impact-{EXACT_HEAD_EXPRESSION}"


def test_artifact_expression_selects_pr_head_and_push_sha_fallback() -> None:
    artifact_name = _artifact_name()
    assert artifact_name == f"exact-base-impact-{EXACT_HEAD_EXPRESSION}"

    # The exact expression documents both branches: pull_request events use the
    # PR head, while push events use github.sha.
    assert "github.event_name == 'pull_request'" in artifact_name
    assert "github.event.pull_request.head.sha" in artifact_name
    assert "|| github.sha" in artifact_name


def test_checkout_head_resolution_and_artifact_share_exact_identity() -> None:
    _assert_exact_head_identity_contract(_load_workflow())


def test_old_github_sha_only_artifact_name_is_absent() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    assert OLD_ARTIFACT_NAME not in workflow_text
    assert _artifact_name() != OLD_ARTIFACT_NAME


def test_old_github_sha_only_artifact_name_is_rejected() -> None:
    workflow = _load_workflow()
    upload = _step_from_workflow(workflow, "Archive impact evidence 📦")
    upload["with"]["name"] = OLD_ARTIFACT_NAME

    with pytest.raises(AssertionError):
        _assert_exact_head_identity_contract(workflow)


def test_pytest_workflow_triggers_and_permissions_are_unchanged() -> None:
    workflow = _load_workflow()
    assert _triggers(workflow) == {
        "push": {"branches": ["main", "master", "feature/**"]},
        "pull_request": {"branches": ["main", "master"]},
        "workflow_dispatch": None,
        "schedule": [{"cron": "17 3 * * *"}],
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["impact-run"]["if"] == (
        "github.event_name != 'workflow_dispatch' && github.event_name != 'schedule'"
    )
    # The required gate classifies the parallel base/head runs (#2220). It must
    # run even when a run side fails: a skipped required check counts as passed.
    gate = workflow["jobs"]["impact-gate"]
    assert gate["name"] == "Exact-base impact gate"
    assert gate["needs"] == "impact-run"
    assert gate["if"] == (
        "always() && github.event_name != 'workflow_dispatch' && github.event_name != 'schedule'"
    )


def test_exact_base_classification_contract_is_unchanged() -> None:
    classification = _step("Classify exact-base regression")
    run = classification["run"]

    # The verdict comes from the exact-base classifier, not the candidate copy (#1754).
    assert '"${{ steps.trusted-impact.outputs.gate }}" classify' in run
    assert ".venv/bin/python scripts/ops/pr_impact_gate.py classify" not in run
    assert "--base-result .ci-impact/base-result.json" in run
    assert "--head-result .ci-impact/head-result.json" in run
    assert "--output .ci-impact/classification.json" in run
    assert classification["env"] == {"NEXUS_TEST_MODE": "CI", "PYTHONPATH": "."}


def test_impact_classifier_is_extracted_from_exact_base() -> None:
    extract = _step("Extract exact-base impact classifier")
    assert extract["env"] == {"BASE_SHA": "${{ steps.base.outputs.sha }}"}
    assert 'git show "$BASE_SHA:$f"' in extract["run"]
    assert "scripts/ops/pr_impact_gate.py scripts/ops/select_tests.py" in extract["run"]


def test_impact_artifact_path_retention_and_failure_behavior_are_unchanged() -> None:
    upload = _step("Archive impact evidence 📦")
    assert upload["if"] == "always()"
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["path"] == "${{ runner.temp }}/nexus-ci-impact/"
    assert upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["retention-days"] == 7


@pytest.mark.parametrize(
    ("event_name", "github_sha", "pull_request_head_sha", "expected_sha"),
    [
        ("pull_request", "push-sha", "pr-head-sha", "pr-head-sha"),
        ("push", "push-sha", "pr-head-sha", "push-sha"),
    ],
)
def test_exact_head_expression_truth_table(
    event_name: str,
    github_sha: str,
    pull_request_head_sha: str,
    expected_sha: str,
) -> None:
    """Keep the intended PR-head/push-SHA branch semantics explicit."""
    expression = _artifact_name().removeprefix("exact-base-impact-")
    assert expression == EXACT_HEAD_EXPRESSION
    selected_sha = pull_request_head_sha if event_name == "pull_request" else github_sha
    assert selected_sha == expected_sha


def test_impact_gate_fails_unless_both_run_sides_succeeded() -> None:
    verify = _step("Verify both run sides and assemble evidence")
    assert verify["env"]["RUN_RESULT"] == "${{ needs.impact-run.result }}"
    run = verify["run"]
    assert 'if [ "$RUN_RESULT" != "success" ]; then' in run
    assert "different impact plans" in run
    assert "does not bind the exact base/head revisions" in run
    names = [step["name"] for step in _steps()]
    assert names.index("Verify both run sides and assemble evidence") < names.index(
        "Classify exact-base regression"
    )


def test_impact_run_sides_split_base_and_head() -> None:
    job = _load_workflow()["jobs"]["impact-run"]
    assert job["strategy"]["matrix"]["side"] == ["base", "head"]
    assert job["strategy"]["fail-fast"] is False
    steps = {step["name"]: step for step in job["steps"]}
    assert steps["Run mapped tests on exact base source"]["if"] == "matrix.side == 'base'"
    assert steps["Run mapped tests on exact head"]["if"] == "matrix.side == 'head'"
    upload = steps["Upload exact-base run evidence"]["with"]["name"]
    assert upload == f"exact-base-impact-${{{{ matrix.side }}}}-{EXACT_HEAD_EXPRESSION}"


def test_impact_map_coverage_is_advisory_and_pr_only() -> None:
    job = _load_workflow()["jobs"]["impact-map-coverage"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job.get("permissions") is None  # inherits contents: read
    (checkout,) = [step for step in job["steps"] if step["name"] == "Checkout exact head"]
    assert checkout["with"]["persist-credentials"] is False
