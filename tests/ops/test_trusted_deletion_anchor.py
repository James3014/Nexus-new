from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from scripts.ops.trusted_deletion_anchor import (
    SCHEMA_VERSION,
    build_manifest,
    verify_evidence,
)


def _event() -> dict[str, object]:
    return {
        "event_name": "pull_request_target",
        "workflow_ref": "James3014/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "run_id": 1240,
        "repository": {"full_name": "James3014/Nexus-new", "default_branch": "main"},
        "pull_request": {
            "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "James3014/Nexus-new"}},
            "head": {"sha": "c" * 40, "repo": {"full_name": "fork/Nexus-new"}},
        },
    }


def _manifest() -> dict[str, object]:
    return build_manifest(
        _event(),
        raw_diff=b":100644 100644 abcdef1 abcdef2 M\tfile.py\0",
        test_inventory=["tests/ops/test_pr_impact_gate.py"],
        source_archive=b"trusted archive",
        git_bundle=b"git bundle",
    )


def _artifacts() -> tuple[bytes, bytes, list[str]]:
    return (
        b"trusted archive",
        b":100644 100644 abcdef1 abcdef2 M\tfile.py\0",
        ["tests/ops/test_pr_impact_gate.py"],
    )


def _evidence(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "workflow_identity": manifest["workflow_identity"],
        "run_id": manifest["run_id"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "base_tree": manifest["base_tree"],
        "head_tree": manifest["head_tree"],
        "bundle_sha256": manifest["bundle_sha256"],
        "raw_diff_sha256": manifest["raw_diff_sha256"],
        "test_inventory_sha256": manifest["test_inventory_sha256"],
        "node_ids": manifest["node_ids"],
        "source_archive_sha256": manifest["source_archive_sha256"],
        "git_bundle_sha256": manifest["git_bundle_sha256"],
        "executor": {"exit_code": 0, "selected_tests": manifest["test_inventory"]},
    }


def test_valid_fixed_schema_evidence_is_accepted():
    manifest = _manifest()
    source, raw_diff, inventory = _artifacts()
    bundle = b"git bundle"
    assert (
        verify_evidence(
            manifest,
            _evidence(manifest),
            source_archive=source,
            raw_diff=raw_diff,
            test_inventory=inventory,
            git_bundle=bundle,
            recomputed_base_tree=manifest["base_tree"],
            recomputed_head_tree=manifest["head_tree"],
        )
        == "PASS"
    )


def test_supplied_trees_cannot_override_immutable_commit_trees():
    manifest = _manifest()
    source, raw_diff, inventory = _artifacts()
    assert (
        verify_evidence(
            manifest,
            _evidence(manifest),
            source_archive=source,
            raw_diff=raw_diff,
            test_inventory=inventory,
            git_bundle=b"git bundle",
            recomputed_base_tree="e" * 40,
            recomputed_head_tree="f" * 40,
        )
        == "IMPACT_UNKNOWN"
    )


@pytest.mark.parametrize("status", ["SKIPPED", "NEUTRAL", "CANCELLED", "MISSING"])
def test_non_complete_status_fails_closed(status: str):
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["status"] = status
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_tampered_artifact_and_head_drift_fail_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["bundle_sha256"] = hashlib.sha256(b"replayed").hexdigest()
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["head_sha"] = "d" * 40
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_malformed_or_token_bearing_evidence_fails_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence.pop("workflow_identity")
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["token"] = "ghs_secret"
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_fork_identity_must_be_bound_to_the_event():
    event = _event()
    event["pull_request"]["head"]["sha"] = "not-a-sha"  # type: ignore[index]
    with pytest.raises(ValueError, match="exact SHA"):
        build_manifest(event, raw_diff=b"", test_inventory=[], source_archive=b"")


def test_workflow_substitution_fails_closed():
    event = _event()
    event["workflow_ref"] = (
        "fork/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main"
    )
    with pytest.raises(ValueError, match="workflow identity"):
        build_manifest(
            event,
            raw_diff=b"",
            test_inventory=["tests/ops/test_pr_impact_gate.py"],
            source_archive=b"",
        )


def test_recomputed_artifact_digest_rejects_replay():
    manifest = _manifest()
    source, raw_diff, inventory = _artifacts()
    assert (
        verify_evidence(
            manifest,
            _evidence(manifest),
            source_archive=b"replayed archive",
            raw_diff=raw_diff,
            test_inventory=inventory,
        )
        == "IMPACT_UNKNOWN"
    )


def test_workflow_is_three_job_isolated_anchor():
    workflow = yaml.safe_load(
        (Path(__file__).parents[2] / ".github/workflows/trusted-deletion-anchor.yml").read_text()
    )
    trigger = workflow.get("on", workflow.get(True))
    assert "pull_request_target" in trigger
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {
        "trusted-controller",
        "unprivileged-executor",
        "trusted-verifier",
    }
    executor = workflow["jobs"]["unprivileged-executor"]
    assert executor["permissions"] == {}
    assert all("checkout" not in step.get("uses", "") for step in executor["steps"])
    serialized = str(executor).lower()
    assert "secrets" not in serialized
    assert "cache" not in serialized
    for job in (workflow["jobs"]["trusted-controller"], workflow["jobs"]["trusted-verifier"]):
        for step in job["steps"]:
            if "checkout" in step.get("uses", ""):
                assert step["with"]["persist-credentials"] is False
