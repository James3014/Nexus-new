from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from scripts.ops.trusted_deletion_anchor import (
    SCHEMA_VERSION,
    _json,
    build_manifest,
    verify_evidence,
)

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/trusted-deletion-anchor.yml"


def _event() -> dict[str, object]:
    return {
        "event_name": "pull_request_target",
        "workflow_ref": "James3014/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "run_id": 1240,
        "repository": {"full_name": "James3014/Nexus-new", "default_branch": "main"},
        "pull_request": {
            "number": 125,
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


def _verify(manifest: dict[str, object], evidence: dict[str, object], **overrides: object) -> str:
    return verify_evidence(
        manifest,
        evidence,
        source_archive=overrides.get("source_archive", b"trusted archive"),
        raw_diff=overrides.get("raw_diff", b":100644 100644 abcdef1 abcdef2 M\tfile.py\0"),
        test_inventory=overrides.get("test_inventory", ["tests/ops/test_pr_impact_gate.py"]),
        git_bundle=overrides.get("git_bundle", b"git bundle"),
        recomputed_base_tree=overrides.get("base_tree", manifest["base_tree"]),
        recomputed_head_tree=overrides.get("head_tree", manifest["head_tree"]),
    )


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def test_valid_fixed_schema_evidence_is_accepted():
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest)) == "PASS"


def test_supplied_trees_cannot_override_immutable_commit_trees():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), base_tree="e" * 40, head_tree="f" * 40)
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
    assert (
        _verify(manifest, _evidence(manifest), source_archive=b"replayed archive")
        == "IMPACT_UNKNOWN"
    )


def test_controller_executor_verifier_path_has_cloneable_bundle_and_external_anchor():
    with TemporaryDirectory(prefix="trusted-anchor-e2e-") as directory:
        root = Path(directory)
        origin = root / "origin.git"
        checkout = root / "checkout"
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(
            ["git", "clone", str(origin), str(checkout)], check=True, capture_output=True
        )
        _run_git(checkout, "config", "user.email", "test@example.invalid")
        _run_git(checkout, "config", "user.name", "trusted-anchor-test")
        test_path = checkout / "tests/ops/test_pr_impact_gate.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("def test_anchor_path():\n    assert True\n", encoding="utf-8")
        _run_git(checkout, "add", "tests/ops/test_pr_impact_gate.py")
        _run_git(checkout, "commit", "-m", "base")
        base_sha = _run_git(checkout, "rev-parse", "HEAD")
        test_path.write_text("def test_anchor_path():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        _run_git(checkout, "commit", "-am", "head")
        head_sha = _run_git(checkout, "rev-parse", "HEAD")
        _run_git(checkout, "push", "origin", "HEAD:main")
        event = _event()
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(checkout),
                "--output-dir",
                str(bundle),
            ],
            check=True,
        )
        manifest = json.loads((bundle / "manifest.json").read_text())
        anchor = json.loads((bundle / "external-anchor.json").read_text())
        assert (bundle / "git-objects.bundle").stat().st_size > 0
        assert (
            anchor["manifest_sha256"]
            == hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
        )
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "executor",
                "--bundle-dir",
                str(bundle),
            ],
            check=True,
        )
        expected = [
            "--expected-workflow-ref",
            event["workflow_ref"],
            "--expected-workflow-sha",
            event["workflow_sha"],
            "--expected-run-id",
            str(event["run_id"]),
            "--verify-evidence",
            str(bundle / "raw-evidence.json"),
            "--expected-manifest-sha256",
            anchor["manifest_sha256"],
            "--expected-external-anchor-sha256",
            hashlib.sha256((bundle / "external-anchor.json").read_bytes()).hexdigest(),
            "--expected-event-name",
            event["event_name"],
            "--expected-repository",
            event["repository"]["full_name"],
            "--expected-default-branch",
            event["repository"]["default_branch"],
            "--expected-pull-request-number",
            str(event["pull_request"]["number"]),
            "--expected-base-sha",
            base_sha,
            "--expected-head-sha",
            head_sha,
        ]
        verified = subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "verifier",
                "--bundle-dir",
                str(bundle),
                *expected,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        assert '"status": "PASS"' in verified.stdout
        tampered = dict(manifest)
        tampered["head_sha"] = "d" * 40
        (bundle / "manifest.json").write_bytes(_json(tampered) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    "scripts/ops/trusted_deletion_anchor.py",
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
            ).returncode
            != 0
        )


def test_workflow_is_three_job_isolated_anchor():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    trigger = workflow.get("on", workflow.get(True))
    assert "pull_request_target" in trigger
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {
        "trusted-controller",
        "unprivileged-executor",
        "trusted-verifier",
    }
    assert workflow["jobs"]["unprivileged-executor"]["permissions"] == {}
    assert workflow["jobs"]["trusted-controller"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["trusted-verifier"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            assert "actions/checkout@" not in step.get("uses", "")
            if step.get("uses", "").startswith((
                "actions/upload-artifact@",
                "actions/download-artifact@",
            )):
                assert len(step["uses"].split("@", 1)[1].split()[0]) == 40
    assert "--verify-evidence" in next(
        step["run"]
        for step in workflow["jobs"]["trusted-verifier"]["steps"]
        if step.get("name") == "Verify fixed schema and recomputed digests"
    )


def test_trusted_jobs_use_bare_exact_sha_and_allowlisted_regular_blob():
    text = WORKFLOW.read_text()
    assert "git init --bare" in text
    assert 'fetch --no-tags --depth=1 origin "$WORKFLOW_SHA"' in text
    assert 'rev-parse "$WORKFLOW_SHA^{commit}"' in text
    assert 'cat-file commit "$WORKFLOW_SHA"' in text
    assert 'ls-tree "$WORKFLOW_SHA"' in text
    assert "100644 blob" in text
    assert 'cat-file blob "$WORKFLOW_SHA:$script_path"' in text
    assert "trusted-source.receipt" in text
    assert "sha256=" in text
    assert '--repo-root "$bare_repo"' in text
    assert "actions/checkout" not in text
    assert "git checkout" not in text
    assert "git worktree" not in text
    assert "git submodule" not in text


def test_trusted_source_identity_and_token_isolation_are_fail_closed():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    text = WORKFLOW.read_text().lower()
    assert "https://github.com/$repository.git" in text
    assert "http.extraheader=authorization: bearer $trusted_token" in text
    assert "persist-credentials" not in text
    assert "credential.helper" not in text
    assert "github.token" in text
    assert "permissions: {}" in text
    for job_name in ("trusted-controller", "trusted-verifier"):
        steps = workflow["jobs"][job_name]["steps"]
        cleanup = [step for step in steps if step.get("if") == "always()"]
        assert cleanup and steps[-1] is cleanup[-1]
        assert "rm -rf" in cleanup[-1]["run"]
        assert "config" in cleanup[-1]["run"]
    executor = str(workflow["jobs"]["unprivileged-executor"]).lower()
    assert "secrets" not in executor
    assert "cache" not in executor
    assert "token" not in executor


def test_trusted_jobs_never_execute_head_code_or_materialize_a_worktree():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    for job_name in ("trusted-controller", "trusted-verifier"):
        serialized = str(workflow["jobs"][job_name]).lower()
        assert "github.event.pull_request.head" in serialized or job_name == "trusted-controller"
        assert "checkout" not in serialized
        assert "worktree" not in serialized
        assert "submodule" not in serialized
        assert "source.tar" not in serialized or job_name == "trusted-controller"
