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

MODULE = Path(__file__).parents[2] / "scripts/ops/trusted_deletion_anchor.py"


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


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
    assert workflow["jobs"]["trusted-controller"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["trusted-verifier"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            action = step.get("uses", "")
            if action.startswith((
                "actions/checkout@",
                "actions/upload-artifact@",
                "actions/download-artifact@",
            )):
                assert len(action.split("@", 1)[1].split()[0]) == 40
                assert action.split("@", 1)[1].split()[0].isalnum()
    verifier_run = next(
        step["run"]
        for step in workflow["jobs"]["trusted-verifier"]["steps"]
        if step.get("name") == "Verify fixed schema and recomputed digests"
    )
    assert '--verify-evidence "$RUNNER_TEMP/trusted-anchor/raw-evidence.json"' in verifier_run
    serialized = str(executor).lower()
    assert "secrets" not in serialized
    assert "cache" not in serialized
    for job in (workflow["jobs"]["trusted-controller"], workflow["jobs"]["trusted-verifier"]):
        for step in job["steps"]:
            if "checkout" in step.get("uses", ""):
                assert step["with"]["persist-credentials"] is False


def _gitlink_metadata_steps(workflow: dict[str, object]) -> dict[str, dict[str, object]]:
    steps = {}
    for job_name in ("trusted-controller", "trusted-verifier"):
        matching = [
            step
            for step in workflow["jobs"][job_name]["steps"]  # type: ignore[index]
            if step.get("name") == "Install gitlink metadata for checkout post-cleanup"
        ]
        assert len(matching) == 1
        steps[job_name] = matching[0]
    return steps


def test_trusted_checkout_teardown_metadata_is_last_and_executor_free():
    workflow = yaml.safe_load(
        (Path(__file__).parents[2] / ".github/workflows/trusted-deletion-anchor.yml").read_text()
    )
    metadata_steps = _gitlink_metadata_steps(workflow)
    for job_name, step in metadata_steps.items():
        assert step["if"] == "always()"
        assert workflow["jobs"][job_name]["steps"][-1] is step  # type: ignore[index]
        run = step["run"]
        assert "git ls-files --stage -z" in run
        assert "git config --file .gitmodules" in run
        assert "gitlink_path=\"${index_entry#*$'\\t'}\"" in run
        assert 'git config --file .gitmodules "submodule.${gitlink_path}.url" .' in run
        assert "git submodule" not in run
        assert "://" not in run
        assert all(
            forbidden not in run
            for forbidden in (
                "git fetch",
                "git clone",
                "git init",
                "git update-index",
                "git checkout",
                "git cat-file",
                "git show",
                "git archive",
                "git read-tree",
            )
        )

    executor = workflow["jobs"]["unprivileged-executor"]
    assert not any(
        step.get("name") == "Install gitlink metadata for checkout post-cleanup"
        for step in executor["steps"]
    )


def test_gitlink_metadata_step_handles_real_gitlink_partial_metadata_and_hostile_path():
    workflow = yaml.safe_load(
        (Path(__file__).parents[2] / ".github/workflows/trusted-deletion-anchor.yml").read_text()
    )
    run = _gitlink_metadata_steps(workflow)["trusted-controller"]["run"]
    with TemporaryDirectory(prefix="trusted-anchor-gitlink-") as directory:
        repo = Path(directory)
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        _run_git(repo, "config", "user.email", "test@example.invalid")
        _run_git(repo, "config", "user.name", "trusted-anchor-test")
        marker = repo / "marker"
        marker.write_text("marker\n", encoding="utf-8")
        _run_git(repo, "add", "marker")
        _run_git(repo, "commit", "-m", "base")
        gitlink_path = "-hostile path"
        _run_git(
            repo,
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{_run_git(repo, 'rev-parse', 'HEAD')},{gitlink_path}",
        )
        # A URL-only entry is deliberately incomplete and must be replaced locally.
        _run_git(
            repo,
            "config",
            "--file",
            ".gitmodules",
            f"submodule.{gitlink_path}.url",
            "https://evil.invalid",
        )
        subprocess.run(["bash", "-euo", "pipefail", "-c", run], cwd=repo, check=True)
        assert (
            _run_git(repo, "config", "--file", ".gitmodules", f"submodule.{gitlink_path}.path")
            == gitlink_path
        )
        assert (
            _run_git(repo, "config", "--file", ".gitmodules", f"submodule.{gitlink_path}.url")
            == "."
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
        event["workflow_sha"] = "a" * 40
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event["pull_request"]["base"]["repo"]["full_name"] = "Nexus"  # type: ignore[index]
        event["repository"]["full_name"] = "Nexus"  # type: ignore[index]
        event["workflow_ref"] = (
            "Nexus/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main"
        )
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        subprocess.run(
            [
                sys.executable,
                str(MODULE),
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
        clone = root / "bundle-clone.git"
        subprocess.run(["git", "init", "--bare", str(clone)], check=True, capture_output=True)
        for ref, revision in (
            ("refs/trusted-anchor/base", base_sha),
            ("refs/trusted-anchor/head", head_sha),
        ):
            _run_git(clone, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(clone, "rev-parse", f"{ref}^{{commit}}") == revision
        subprocess.run(
            [sys.executable, str(MODULE), "executor", "--bundle-dir", str(bundle)], check=True
        )
        expected = {
            "--expected-workflow-ref": event["workflow_ref"],
            "--expected-workflow-sha": event["workflow_sha"],
            "--expected-run-id": str(event["run_id"]),
            "--verify-evidence": str(bundle / "raw-evidence.json"),
            "--expected-manifest-sha256": anchor["manifest_sha256"],
            "--expected-external-anchor-sha256": hashlib.sha256(
                (bundle / "external-anchor.json").read_bytes()
            ).hexdigest(),
            "--expected-event-name": event["event_name"],
            "--expected-repository": event["repository"]["full_name"],
            "--expected-default-branch": event["repository"]["default_branch"],
            "--expected-pull-request-number": str(event["pull_request"]["number"]),
            "--expected-base-sha": base_sha,
            "--expected-head-sha": head_sha,
        }
        verified = subprocess.run(
            [sys.executable, str(MODULE), "verifier", "--bundle-dir", str(bundle)]
            + [item for pair in expected.items() for item in pair],
            check=True,
            capture_output=True,
            text=True,
        )
        assert '"status": "PASS"' in verified.stdout
        tampered = dict(manifest)
        tampered["head_sha"] = "d" * 40
        tampered["head_tree"] = "e" * 40
        (bundle / "manifest.json").write_bytes(_json(tampered) + b"\n")
        anchor["manifest_sha256"] = hashlib.sha256(
            (bundle / "manifest.json").read_bytes()
        ).hexdigest()
        anchor["head_sha"] = tampered["head_sha"]
        (bundle / "external-anchor.json").write_bytes(_json(anchor) + b"\n")
        rejected = subprocess.run(
            [sys.executable, str(MODULE), "verifier", "--bundle-dir", str(bundle)]
            + [item for pair in expected.items() for item in pair],
            capture_output=True,
        )
        assert rejected.returncode != 0
