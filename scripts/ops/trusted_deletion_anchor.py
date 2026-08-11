#!/usr/bin/env python3
"""Fail-closed plumbing for the trusted deletion-evidence bootstrap anchor.

This module is deliberately independent of repository code.  The controller
and verifier may read untrusted Git objects, but never import them.  The
executor receives this exact module in the controller bundle and is the only
job allowed to run the packaged source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "trusted-deletion-anchor.v1"
WORKFLOW_PATH = ".github/workflows/trusted-deletion-anchor.yml"
SHA_LENGTH = 40
REQUIRED_EVIDENCE_KEYS = {
    "schema_version",
    "status",
    "workflow_identity",
    "run_id",
    "base_sha",
    "head_sha",
    "base_tree",
    "head_tree",
    "bundle_sha256",
    "raw_diff_sha256",
    "test_inventory_sha256",
    "node_ids",
    "source_archive_sha256",
    "git_bundle_sha256",
    "executor",
}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_object_id(value: bytes) -> str:
    return hashlib.sha1(value).hexdigest()


def _exact_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != SHA_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be an exact SHA")
    return value


def _event_value(event: dict[str, Any], *path: str) -> Any:
    value: Any = event
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing event identity: {'.'.join(path)}")
        value = value[key]
    return value


def _identity(event: dict[str, Any]) -> dict[str, Any]:
    repository = _event_value(event, "repository", "full_name")
    default_branch = _event_value(event, "repository", "default_branch")
    workflow_ref = event.get("workflow_ref")
    expected_ref = f"{repository}/{WORKFLOW_PATH}@refs/heads/{default_branch}"
    if event.get("event_name") != "pull_request_target" or workflow_ref != expected_ref:
        raise ValueError("workflow identity is not trusted default-branch pull_request_target")
    workflow_sha = _exact_sha(event.get("workflow_sha"), "workflow_sha")
    run_id = event.get("run_id")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("run_id must be a positive integer")
    base_repo = _event_value(event, "pull_request", "base", "repo", "full_name")
    if base_repo != repository:
        raise ValueError("base repository drift")
    return {
        "repository": repository,
        "default_branch": default_branch,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "run_id": run_id,
    }


def build_manifest(
    event: dict[str, Any],
    *,
    raw_diff: bytes,
    test_inventory: list[str],
    source_archive: bytes,
    git_bundle: bytes = b"",
    base_tree: str | None = None,
    head_tree: str | None = None,
) -> dict[str, Any]:
    """Create the controller's immutable, hash-bound manifest."""

    identity = _identity(event)
    base_sha = _exact_sha(_event_value(event, "pull_request", "base", "sha"), "base_sha")
    head_sha = _exact_sha(_event_value(event, "pull_request", "head", "sha"), "head_sha")
    if not test_inventory or any(
        not isinstance(path, str) or not path.startswith("tests/") or ".." in Path(path).parts
        for path in test_inventory
    ):
        raise ValueError("test inventory is missing or unsafe")
    base_tree = _exact_sha(base_tree or _git_object_id(base_sha.encode()), "base_tree")
    head_tree = _exact_sha(head_tree or _git_object_id(head_sha.encode()), "head_tree")
    node_ids = sorted(_sha(path.encode()) for path in test_inventory)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "CONTROLLER_COMPLETE",
        "workflow_identity": identity,
        "run_id": identity["run_id"],
        "base_sha": base_sha,
        "head_sha": head_sha,
        "base_tree": base_tree,
        "head_tree": head_tree,
        "raw_diff_sha256": _sha(raw_diff),
        "test_inventory": sorted(test_inventory),
        "test_inventory_sha256": _sha(_json(sorted(test_inventory))),
        "node_ids": node_ids,
        "source_archive_sha256": _sha(source_archive),
        "git_bundle_sha256": _sha(git_bundle),
    }
    unsigned = (
        _json(manifest) + source_archive + raw_diff + _json(sorted(test_inventory)) + git_bundle
    )
    manifest["bundle_sha256"] = _sha(unsigned)
    return manifest


def verify_evidence(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    *,
    source_archive: bytes | None = None,
    raw_diff: bytes | None = None,
    test_inventory: list[str] | None = None,
    git_bundle: bytes | None = None,
) -> str:
    """Validate only recomputable evidence; every ambiguity is unknown."""

    try:
        if set(evidence) != REQUIRED_EVIDENCE_KEYS:
            raise ValueError("fixed schema mismatch")
        if evidence["schema_version"] != SCHEMA_VERSION or evidence["status"] != "COMPLETE":
            raise ValueError("execution did not complete")
        serialized = json.dumps(evidence, ensure_ascii=True, sort_keys=True).lower()
        if "ghs_" in serialized or "token" in serialized or "authorization" in serialized:
            raise ValueError("credential-bearing evidence")
        for key in ("base_sha", "head_sha", "base_tree", "head_tree"):
            if evidence[key] != manifest[key]:
                raise ValueError(f"{key} mismatch")
        if (
            evidence["run_id"] != manifest["run_id"]
            or evidence["workflow_identity"] != manifest["workflow_identity"]
        ):
            raise ValueError("workflow identity mismatch")
        for key in (
            "bundle_sha256",
            "raw_diff_sha256",
            "test_inventory_sha256",
            "source_archive_sha256",
            "git_bundle_sha256",
            "node_ids",
        ):
            if evidence[key] != manifest[key]:
                raise ValueError(f"{key} mismatch")
        executor = evidence["executor"]
        if not isinstance(executor, dict) or executor.get("exit_code") != 0:
            raise ValueError("executor result is not successful")
        if executor.get("selected_tests") != manifest["test_inventory"]:
            raise ValueError("test selection mismatch")
        if source_archive is not None:
            if _sha(source_archive) != manifest["source_archive_sha256"]:
                raise ValueError("source archive digest mismatch")
        if git_bundle is not None and _sha(git_bundle) != manifest["git_bundle_sha256"]:
            raise ValueError("Git object bundle digest mismatch")
        if raw_diff is not None and _sha(raw_diff) != manifest["raw_diff_sha256"]:
            raise ValueError("raw diff digest mismatch")
        if test_inventory is not None:
            inventory = sorted(test_inventory)
            if _sha(_json(inventory)) != manifest["test_inventory_sha256"]:
                raise ValueError("test inventory digest mismatch")
        if (
            source_archive is not None
            and raw_diff is not None
            and test_inventory is not None
            and git_bundle is not None
        ):
            unsigned = dict(manifest)
            unsigned.pop("bundle_sha256", None)
            expected_bundle = _sha(
                _json(unsigned)
                + source_archive
                + raw_diff
                + _json(sorted(test_inventory))
                + git_bundle
            )
            if expected_bundle != manifest["bundle_sha256"]:
                raise ValueError("bundle digest mismatch")
    except (KeyError, TypeError, ValueError):
        return "IMPACT_UNKNOWN"
    return "PASS"


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode().strip()


def _controller(args: argparse.Namespace) -> None:
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    repo = Path(args.repo_root)
    head_sha = _exact_sha(_event_value(event, "pull_request", "head", "sha"), "head_sha")
    _git(repo, "fetch", "--no-tags", "--depth=1", "origin", head_sha)
    base_sha = _exact_sha(_event_value(event, "pull_request", "base", "sha"), "base_sha")
    for revision in (base_sha, head_sha):
        _git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
    raw_diff = _git(repo, "diff", "--raw", "-z", "--no-renames", base_sha, head_sha, binary=True)
    assert isinstance(raw_diff, bytes)
    inventory = _git(repo, "ls-tree", "-r", "--name-only", head_sha, "--", "tests", binary=False)
    assert isinstance(inventory, str)
    selected = [
        path
        for path in inventory.splitlines()
        if path in {"tests/ops/test_pr_impact_gate.py", "tests/ops/test_select_tests.py"}
    ]
    if not selected:
        raise ValueError("trusted test inventory is empty")
    source_archive = _git(repo, "archive", "--format=tar", head_sha, binary=True)
    assert isinstance(source_archive, bytes)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    git_bundle_path = output / "git-objects.bundle"
    _git(repo, "bundle", "create", str(git_bundle_path), base_sha, head_sha)
    git_bundle = git_bundle_path.read_bytes()
    manifest = build_manifest(
        event,
        raw_diff=raw_diff,
        test_inventory=selected,
        source_archive=source_archive,
        base_tree=_git(repo, "rev-parse", f"{base_sha}^{{tree}}"),
        head_tree=_git(repo, "rev-parse", f"{head_sha}^{{tree}}"),
        git_bundle=git_bundle,
    )
    (output / "source.tar").write_bytes(source_archive)
    (output / "raw-diff.bin").write_bytes(raw_diff)
    (output / "test-inventory.json").write_bytes(_json(selected) + b"\n")
    (output / "manifest.json").write_bytes(_json(manifest) + b"\n")
    (output / "trusted_deletion_anchor.py").write_bytes(Path(__file__).read_bytes())


def _executor(args: argparse.Namespace) -> None:
    bundle = Path(args.bundle_dir)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source = bundle / "source"
    source.mkdir()
    with tarfile.open(bundle / "source.tar") as archive:
        archive.extractall(source, filter="data")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *manifest["test_inventory"], "-q"], cwd=source
    )
    evidence = {key: manifest[key] for key in REQUIRED_EVIDENCE_KEYS if key != "executor"}
    evidence["schema_version"] = SCHEMA_VERSION
    evidence["status"] = "COMPLETE" if result.returncode == 0 else "FAILED"
    evidence["executor"] = {
        "exit_code": result.returncode,
        "selected_tests": manifest["test_inventory"],
    }
    (bundle / "raw-evidence.json").write_bytes(_json(evidence) + b"\n")
    raise SystemExit(result.returncode)


def _verifier(args: argparse.Namespace) -> None:
    bundle = Path(args.bundle_dir)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((bundle / "raw-evidence.json").read_text(encoding="utf-8"))
    identity = manifest.get("workflow_identity")
    if not isinstance(identity, dict) or identity.get("workflow_ref") != args.expected_workflow_ref:
        raise SystemExit(1)
    if identity.get("workflow_sha") != _exact_sha(args.expected_workflow_sha, "workflow_sha"):
        raise SystemExit(1)
    if identity.get("run_id") != args.expected_run_id:
        raise SystemExit(1)
    git_bundle = (bundle / "git-objects.bundle").read_bytes()
    with tempfile.TemporaryDirectory(prefix="trusted-anchor-verify-") as directory:
        git_repo = Path(directory) / "repo.git"
        subprocess.run(["git", "init", "--bare", str(git_repo)], check=True, capture_output=True)
        _git(git_repo, "fetch", str(bundle / "git-objects.bundle"))
        recomputed_diff = _git(
            git_repo,
            "diff",
            "--raw",
            "-z",
            "--no-renames",
            manifest["base_sha"],
            manifest["head_sha"],
            binary=True,
        )
        if recomputed_diff != (bundle / "raw-diff.bin").read_bytes():
            raise SystemExit(1)
        recomputed_inventory = _git(
            git_repo,
            "ls-tree",
            "-r",
            "--name-only",
            manifest["head_sha"],
            "--",
            "tests",
        )
        selected_inventory = json.loads(
            (bundle / "test-inventory.json").read_text(encoding="utf-8")
        )
        recomputed_selected = [
            path for path in recomputed_inventory.splitlines() if path in selected_inventory
        ]
        if recomputed_selected != sorted(selected_inventory):
            raise SystemExit(1)
    status = verify_evidence(
        manifest,
        evidence,
        source_archive=(bundle / "source.tar").read_bytes(),
        raw_diff=(bundle / "raw-diff.bin").read_bytes(),
        test_inventory=json.loads((bundle / "test-inventory.json").read_text(encoding="utf-8")),
        git_bundle=git_bundle,
    )
    print(json.dumps({"status": status, "claim_ceiling": "BOOTSTRAP_ANCHOR_ONLY"}, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    controller = subparsers.add_parser("controller")
    controller.add_argument("--event-json", required=True)
    controller.add_argument("--repo-root", required=True)
    controller.add_argument("--output-dir", required=True)
    controller.set_defaults(function=_controller)
    executor = subparsers.add_parser("executor")
    executor.add_argument("--bundle-dir", required=True)
    executor.set_defaults(function=_executor)
    verifier = subparsers.add_parser("verifier")
    verifier.add_argument("--bundle-dir", required=True)
    verifier.add_argument("--expected-workflow-ref", required=True)
    verifier.add_argument("--expected-workflow-sha", required=True)
    verifier.add_argument("--expected-run-id", required=True, type=int)
    verifier.set_defaults(function=_verifier)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
