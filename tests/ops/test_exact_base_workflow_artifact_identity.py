"""Issue #430: exact-base workflow artifact identity contract regression tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

HEAD_SHA_EXPRESSION = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
)
STALE_SHA_EXPRESSION = "${{ github.sha }}"

EXACT_BASE_WORKFLOWS: dict[str, dict[str, Any]] = {
    "ruff": {
        "workflow": ".github/workflows/lint.yml",
        "job": "lint",
        "artifact_prefix": "exact-base-ruff-",
        "upload_step_name": "Upload Ruff evidence",
    },
    "bandit": {
        "workflow": ".github/workflows/security.yml",
        "job": "bandit",
        "artifact_prefix": "exact-base-bandit-",
        "upload_step_name": "Upload Bandit evidence",
    },
    "pyright": {
        "workflow": ".github/workflows/typecheck.yml",
        "job": "typecheck",
        "artifact_prefix": "exact-base-pyright-",
        "upload_step_name": "Upload Pyright evidence",
    },
    "wiki": {
        "workflow": ".github/workflows/wiki-governance.yml",
        "job": "wiki-governance",
        "artifact_prefix": "exact-base-wiki-",
        "upload_step_name": "Upload Wiki evidence",
    },
}


def _load_workflow(workflow_relpath: str) -> dict[str, Any]:
    path = REPO_ROOT / workflow_relpath
    assert path.is_file(), f"Workflow file not found: {path}"
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(content, dict), f"Invalid YAML content in {workflow_relpath}"
    return content


def _get_job_steps(workflow_data: dict[str, Any], job_id: str) -> list[dict[str, Any]]:
    jobs = workflow_data.get("jobs", {})
    assert job_id in jobs, f"Job {job_id!r} not found in workflow jobs: {list(jobs)}"
    steps = jobs[job_id].get("steps", [])
    assert isinstance(steps, list) and steps, f"Job {job_id!r} has no steps"
    return steps


@pytest.mark.parametrize("gate", sorted(EXACT_BASE_WORKFLOWS))
def test_checkout_uses_exact_head_identity_contract(gate: str) -> None:
    spec = EXACT_BASE_WORKFLOWS[gate]
    data = _load_workflow(spec["workflow"])
    steps = _get_job_steps(data, spec["job"])

    checkout_steps = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout")]
    assert len(checkout_steps) == 1, f"Expected 1 checkout step in {spec['workflow']}"
    checkout_step = checkout_steps[0]

    with_block = checkout_step.get("with", {})
    assert (
        with_block.get("ref") == HEAD_SHA_EXPRESSION
    ), f"{spec['workflow']}: checkout ref mismatch"


@pytest.mark.parametrize("gate", sorted(EXACT_BASE_WORKFLOWS))
def test_evaluation_head_sha_env_bindings_match_contract(gate: str) -> None:
    spec = EXACT_BASE_WORKFLOWS[gate]
    data = _load_workflow(spec["workflow"])
    steps = _get_job_steps(data, spec["job"])

    head_sha_steps = [s for s in steps if "HEAD_SHA" in s.get("env", {})]
    assert (
        len(head_sha_steps) >= 2
    ), f"Expected at least 2 steps with HEAD_SHA env in {spec['workflow']}"

    for step in head_sha_steps:
        step_name = step.get("name", "<unnamed>")
        head_sha_val = step["env"]["HEAD_SHA"]
        assert (
            head_sha_val == HEAD_SHA_EXPRESSION
        ), f"{spec['workflow']} step {step_name!r}: HEAD_SHA env mismatch"


@pytest.mark.parametrize("gate", sorted(EXACT_BASE_WORKFLOWS))
def test_upload_artifact_name_shares_identity_contract_and_rejects_stale_sha(
    gate: str,
) -> None:
    spec = EXACT_BASE_WORKFLOWS[gate]
    data = _load_workflow(spec["workflow"])
    steps = _get_job_steps(data, spec["job"])

    upload_steps = [
        s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")
    ]
    assert len(upload_steps) == 1, f"Expected 1 upload-artifact step in {spec['workflow']}"
    upload_step = upload_steps[0]

    artifact_name = upload_step.get("with", {}).get("name")
    expected_artifact_name = f"{spec['artifact_prefix']}{HEAD_SHA_EXPRESSION}"
    stale_artifact_name = f"{spec['artifact_prefix']}{STALE_SHA_EXPRESSION}"

    assert (
        artifact_name == expected_artifact_name
    ), f"{spec['workflow']}: artifact name mismatch (got {artifact_name!r}, expected {expected_artifact_name!r})"

    # Negative witness verification
    assert (
        artifact_name != stale_artifact_name
    ), f"{spec['workflow']}: artifact name still uses stale sha suffix"
    assert (
        STALE_SHA_EXPRESSION not in artifact_name.replace(HEAD_SHA_EXPRESSION, "")
    ), f"{spec['workflow']}: stale sha expression detected outside bound contract"


@pytest.mark.parametrize("gate", sorted(EXACT_BASE_WORKFLOWS))
def test_artifact_identity_matches_checkout_ref_and_head_sha(gate: str) -> None:
    spec = EXACT_BASE_WORKFLOWS[gate]
    data = _load_workflow(spec["workflow"])
    steps = _get_job_steps(data, spec["job"])

    checkout_step = next(
        s for s in steps if str(s.get("uses", "")).startswith("actions/checkout")
    )
    checkout_ref = checkout_step["with"]["ref"]

    upload_step = next(
        s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")
    )
    artifact_name = upload_step["with"]["name"]
    artifact_suffix = artifact_name[len(spec["artifact_prefix"]) :]

    assert (
        artifact_suffix == checkout_ref
    ), f"{spec['workflow']}: artifact suffix does not match checkout ref"

    for step in steps:
        if "HEAD_SHA" in step.get("env", {}):
            head_sha = step["env"]["HEAD_SHA"]
            assert (
                artifact_suffix == head_sha
            ), f"{spec['workflow']}: artifact suffix does not match HEAD_SHA in {step.get('name')}"
