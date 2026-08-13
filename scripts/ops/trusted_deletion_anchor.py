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
import os
import platform
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "trusted-deletion-anchor.v3"
RUNTIME_SCHEMA_VERSION = "trusted-deletion-runtime.v1"
WORKFLOW_PATH = ".github/workflows/trusted-deletion-anchor.yml"
SHA_LENGTH = 40
BASE_REF = "refs/trusted-anchor/base"
HEAD_REF = "refs/trusted-anchor/head"
WORKFLOW_REF = "refs/trusted-anchor/workflow"
RUNTIME_FILENAMES = ("runtime.tar", "runtime-metadata.json", "requirements.txt")
GOLDEN_EVALUATOR_PATH = "scripts/ops/run_golden_behavior_eval.py"
PYTEST_PLUGINS = ["pytest", "pytest_asyncio", "pytest_timeout"]
UV_VERSION = "uv 0.9.2"
REQUIRED_EVIDENCE_KEYS = {
    "schema_version",
    "status",
    "workflow_identity",
    "run_id",
    "base_sha",
    "head_sha",
    "base_tree",
    "head_tree",
    "test_tree",
    "bundle_sha256",
    "raw_diff_sha256",
    "test_inventory_sha256",
    "node_ids",
    "source_archive_sha256",
    "git_bundle_sha256",
    "pyproject_sha256",
    "uv_lock_sha256",
    "requirements_sha256",
    "runtime_archive_sha256",
    "runtime_metadata_sha256",
    "runtime_identity",
    "golden_evaluator_sha256",
    "golden_corpus_sha256",
    "golden_test_corpus_sha256",
    "golden_topology_sha256",
    "golden_report_sha256",
    "golden_report",
    "executor",
}


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_object_id(value: bytes) -> str:
    return hashlib.sha1(value).hexdigest()


def _runtime_probe() -> dict[str, str]:
    return {
        "implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "cache_tag": sys.implementation.cache_tag or "",
        "soabi": sysconfig.get_config_var("SOABI") or "",
        "platform": sysconfig.get_platform(),
        "machine": platform.machine(),
        "system": platform.system(),
    }


def _runtime_subprocess_env(home: Path) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    environment = {
        "HOME": str(home),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": os.environ.get("RUNNER_TEMP", tempfile.gettempdir()),
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CACHE": "1",
        "UV_PYTHON_DOWNLOADS": "never",
    }
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        if os.environ.get(key):
            environment[key] = os.environ[key]
    return environment


def _archive_runtime(site_packages: Path) -> bytes:
    if not site_packages.is_dir():
        raise ValueError("runtime site-packages is missing")
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        root = tarfile.TarInfo("site-packages")
        root.type = tarfile.DIRTYPE
        root.mode = 0o755
        root.mtime = 0
        archive.addfile(root)
        for path in sorted(site_packages.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise ValueError("runtime contains unsupported filesystem entry")
            relative = path.relative_to(site_packages).as_posix()
            member = tarfile.TarInfo(f"site-packages/{relative}")
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            member.mtime = 0
            if path.is_dir():
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                archive.addfile(member)
            else:
                member.size = path.stat().st_size
                member.mode = 0o644
                with path.open("rb") as source:
                    archive.addfile(member, source)
    return stream.getvalue()


def _build_runtime(args: argparse.Namespace) -> None:
    repo = Path(args.repo_root)
    workflow_sha = _exact_sha(args.workflow_sha, "workflow_sha")
    for revision_path in ("pyproject.toml", "uv.lock"):
        _git(repo, "cat-file", "-e", f"{workflow_sha}:{revision_path}")
    pyproject = _git(repo, "show", f"{workflow_sha}:pyproject.toml", binary=True)
    uv_lock = _git(repo, "show", f"{workflow_sha}:uv.lock", binary=True)
    assert isinstance(pyproject, bytes) and isinstance(uv_lock, bytes)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="trusted-runtime-build-") as directory:
        build_root = Path(directory)
        contract = build_root / "contract"
        contract.mkdir()
        (contract / "pyproject.toml").write_bytes(pyproject)
        (contract / "uv.lock").write_bytes(uv_lock)
        requirements_path = build_root / "requirements.txt"
        environment = _runtime_subprocess_env(build_root / "home")
        subprocess.run(
            [
                args.uv_executable,
                "export",
                "--frozen",
                "--no-default-groups",
                "--group",
                "dev",
                "--no-emit-project",
                "--no-emit-workspace",
                "--no-emit-local",
                "--output-file",
                str(requirements_path),
            ],
            cwd=contract,
            env=environment,
            check=True,
            capture_output=True,
        )
        requirements = requirements_path.read_bytes()
        site_packages = build_root / "site-packages"
        subprocess.run(
            [
                args.uv_executable,
                "pip",
                "install",
                "--target",
                str(site_packages),
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--no-cache",
                "--no-python-downloads",
                "--python",
                sys.executable,
                "--requirements",
                str(requirements_path),
            ],
            cwd=contract,
            env=environment,
            check=True,
            capture_output=True,
        )
        uv_version = subprocess.run(
            [args.uv_executable, "--version"],
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if uv_version != UV_VERSION:
            raise ValueError("runtime builder identity mismatch")
        runtime_archive = _archive_runtime(site_packages)
    metadata = {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "runtime_probe": _runtime_probe(),
        "builder": {"uv_version": uv_version},
        "pyproject_sha256": _sha(pyproject),
        "uv_lock_sha256": _sha(uv_lock),
        "requirements_sha256": _sha(requirements),
        "pytest_plugins": PYTEST_PLUGINS,
    }
    (output / "runtime.tar").write_bytes(runtime_archive)
    (output / "runtime-metadata.json").write_bytes(_json(metadata) + b"\n")
    (output / "requirements.txt").write_bytes(requirements)


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
    pull_request_number = _event_value(event, "pull_request", "number")
    if type(pull_request_number) is not int or pull_request_number <= 0:
        raise ValueError("pull request number must be a positive integer")
    return {
        "event_name": event["event_name"],
        "repository": repository,
        "default_branch": default_branch,
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "run_id": run_id,
        "pull_request_number": pull_request_number,
    }


def build_manifest(
    event: dict[str, Any],
    *,
    raw_diff: bytes,
    test_inventory: list[str],
    source_archive: bytes,
    git_bundle: bytes = b"",
    pyproject: bytes = b"",
    uv_lock: bytes = b"",
    requirements: bytes = b"",
    runtime_archive: bytes = b"",
    runtime_metadata: bytes = b"{}",
    runtime_identity: dict[str, Any] | None = None,
    golden_evaluator: bytes = b"",
    golden_corpus: bytes = b"",
    golden_test_corpus: bytes = b"",
    golden_topology: bytes = b"",
    base_tree: str | None = None,
    head_tree: str | None = None,
    test_tree: str | None = None,
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
    test_tree = _exact_sha(test_tree or _git_object_id(b"tests:" + head_sha.encode()), "test_tree")
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
        "test_tree": test_tree,
        "raw_diff_sha256": _sha(raw_diff),
        "test_inventory": sorted(test_inventory),
        "test_inventory_sha256": _sha(_json(sorted(test_inventory))),
        "node_ids": node_ids,
        "source_archive_sha256": _sha(source_archive),
        "git_bundle_sha256": _sha(git_bundle),
        "pyproject_sha256": _sha(pyproject),
        "uv_lock_sha256": _sha(uv_lock),
        "requirements_sha256": _sha(requirements),
        "runtime_archive_sha256": _sha(runtime_archive),
        "runtime_metadata_sha256": _sha(runtime_metadata),
        "runtime_identity": runtime_identity or {},
        "golden_evaluator_sha256": _sha(golden_evaluator),
        "golden_corpus_sha256": _sha(golden_corpus),
        "golden_test_corpus_sha256": _sha(golden_test_corpus),
        "golden_topology_sha256": _sha(golden_topology),
    }
    unsigned = (
        _json(manifest)
        + source_archive
        + raw_diff
        + _json(sorted(test_inventory))
        + git_bundle
        + requirements
        + runtime_archive
        + runtime_metadata
        + golden_evaluator
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
    requirements: bytes | None = None,
    runtime_archive: bytes | None = None,
    runtime_metadata: bytes | None = None,
    golden_evaluator: bytes | None = None,
    recomputed_pyproject: bytes | None = None,
    recomputed_uv_lock: bytes | None = None,
    recomputed_base_tree: str | None = None,
    recomputed_head_tree: str | None = None,
    recomputed_test_tree: str | None = None,
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
        for key in ("base_sha", "head_sha", "base_tree", "head_tree", "test_tree"):
            if evidence[key] != manifest[key]:
                raise ValueError(f"{key} mismatch")
        if (
            recomputed_base_tree is None
            or recomputed_head_tree is None
            or recomputed_base_tree != manifest["base_tree"]
            or recomputed_head_tree != manifest["head_tree"]
            or recomputed_test_tree != manifest["test_tree"]
        ):
            raise ValueError("trees do not match immutable base/head/test commits")
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
            "pyproject_sha256",
            "uv_lock_sha256",
            "requirements_sha256",
            "runtime_archive_sha256",
            "runtime_metadata_sha256",
            "runtime_identity",
            "golden_evaluator_sha256",
            "golden_corpus_sha256",
            "golden_test_corpus_sha256",
            "golden_topology_sha256",
            "node_ids",
        ):
            if evidence[key] != manifest[key]:
                raise ValueError(f"{key} mismatch")
        executor = evidence["executor"]
        if not isinstance(executor, dict) or executor.get("exit_code") != 0:
            raise ValueError("executor result is not successful")
        if executor.get("selected_tests") != manifest["test_inventory"]:
            raise ValueError("test selection mismatch")
        if executor.get("pytest_plugins") != PYTEST_PLUGINS:
            raise ValueError("pytest plugin identity mismatch")
        if executor.get("runtime_probe") != manifest["runtime_identity"].get("runtime_probe"):
            raise ValueError("executor runtime identity mismatch")
        golden_report = evidence["golden_report"]
        if not isinstance(golden_report, dict):
            raise ValueError("Golden report is missing")
        if evidence["golden_report_sha256"] != _sha(_json(golden_report)):
            raise ValueError("Golden report digest mismatch")
        if evidence["golden_evaluator_sha256"] != manifest["golden_evaluator_sha256"]:
            raise ValueError("Golden evaluator identity mismatch")
        if (
            golden_report.get("schema") != "nexus.golden_behavior_eval.v1"
            or golden_report.get("source_revision") != manifest["head_sha"]
            or golden_report.get("source_tree") != manifest["head_tree"]
            or golden_report.get("root_binding_mode") != "explicit_sha_bound"
            or golden_report.get("trusted_evaluator_sha256") != manifest["golden_evaluator_sha256"]
            or golden_report.get("evaluator_identity") != manifest["golden_evaluator_sha256"]
            or golden_report.get("corpus_identity") != manifest["golden_corpus_sha256"]
            or golden_report.get("test_corpus_identity") != manifest["golden_test_corpus_sha256"]
            or golden_report.get("topology_identity") != manifest["golden_topology_sha256"]
            or golden_report.get("workspace_dirty") is not False
            or golden_report.get("validation_errors") != []
            or golden_report.get("collection_exit_code") != 0
            or golden_report.get("pytest_exit_code") != 0
        ):
            raise ValueError("Golden report identity or status mismatch")
        cases = golden_report.get("case_evidence")
        if (
            not isinstance(cases, list)
            or len(cases) != golden_report.get("case_count")
            or golden_report.get("selected_case_count") != golden_report.get("case_count")
        ):
            raise ValueError("Golden report case set is incomplete")
        case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
        if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
            raise ValueError("Golden report case identity is malformed")
        for case in cases:
            if case.get("status") == "covered":
                witnesses = case.get("witnesses")
                if (
                    not isinstance(witnesses, list)
                    or not witnesses
                    or any(
                        witness.get("collection_status") != "collected"
                        or witness.get("execution_status") != "passed"
                        for witness in witnesses
                        if isinstance(witness, dict)
                    )
                ):
                    raise ValueError("Golden covered witness did not pass")
            elif case.get("status") != "finding":
                raise ValueError("Golden case status is invalid")
        if source_archive is not None:
            if _sha(source_archive) != manifest["source_archive_sha256"]:
                raise ValueError("source archive digest mismatch")
        if git_bundle is not None and _sha(git_bundle) != manifest["git_bundle_sha256"]:
            raise ValueError("Git object bundle digest mismatch")
        if requirements is not None and _sha(requirements) != manifest["requirements_sha256"]:
            raise ValueError("requirements digest mismatch")
        if (
            runtime_archive is not None
            and _sha(runtime_archive) != manifest["runtime_archive_sha256"]
        ):
            raise ValueError("runtime archive digest mismatch")
        if runtime_metadata is not None:
            if _sha(runtime_metadata) != manifest["runtime_metadata_sha256"]:
                raise ValueError("runtime metadata digest mismatch")
            metadata = json.loads(runtime_metadata)
            if metadata != manifest["runtime_identity"]:
                raise ValueError("runtime identity mismatch")
            if (
                metadata.get("schema_version") != RUNTIME_SCHEMA_VERSION
                or metadata.get("pytest_plugins") != PYTEST_PLUGINS
                or metadata.get("builder") != {"uv_version": UV_VERSION}
            ):
                raise ValueError("runtime contract mismatch")
        if (
            golden_evaluator is not None
            and _sha(golden_evaluator) != manifest["golden_evaluator_sha256"]
        ):
            raise ValueError("trusted Golden evaluator digest mismatch")
        if (
            recomputed_pyproject is not None
            and _sha(recomputed_pyproject) != manifest["pyproject_sha256"]
        ):
            raise ValueError("trusted pyproject digest mismatch")
        if (
            recomputed_uv_lock is not None
            and _sha(recomputed_uv_lock) != manifest["uv_lock_sha256"]
        ):
            raise ValueError("trusted lock digest mismatch")
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
            and requirements is not None
            and runtime_archive is not None
            and runtime_metadata is not None
            and golden_evaluator is not None
        ):
            unsigned = dict(manifest)
            unsigned.pop("bundle_sha256", None)
            expected_bundle = _sha(
                _json(unsigned)
                + source_archive
                + raw_diff
                + _json(sorted(test_inventory))
                + git_bundle
                + requirements
                + runtime_archive
                + runtime_metadata
                + golden_evaluator
            )
            if expected_bundle != manifest["bundle_sha256"]:
                raise ValueError("bundle digest mismatch")
    except (KeyError, TypeError, ValueError):
        return "IMPACT_UNKNOWN"
    return "PASS"


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode().strip()


def _create_git_bundle(
    repo: Path, output: Path, base_sha: str, head_sha: str, workflow_sha: str
) -> bytes:
    """Bundle verified commits through fixed refs in an ephemeral bare clone."""

    with tempfile.TemporaryDirectory(prefix="trusted-anchor-bundle-") as directory:
        ephemeral = Path(directory) / "repo.git"
        subprocess.run(["git", "init", "--bare", str(ephemeral)], check=True, capture_output=True)
        _git(ephemeral, "fetch", "--no-tags", str(repo), base_sha, head_sha, workflow_sha)
        for ref, revision in (
            (BASE_REF, base_sha),
            (HEAD_REF, head_sha),
            (WORKFLOW_REF, workflow_sha),
        ):
            _git(ephemeral, "cat-file", "-e", f"{revision}^{{commit}}")
            _git(ephemeral, "update-ref", ref, revision)
            if _git(ephemeral, "rev-parse", f"{ref}^{{commit}}") != revision:
                raise ValueError(f"failed to bind {ref}")
        subprocess.run(
            ["git", "bundle", "create", str(output), BASE_REF, HEAD_REF, WORKFLOW_REF],
            cwd=ephemeral,
            check=True,
            capture_output=True,
        )
        if not output.is_file() or output.stat().st_size == 0:
            raise ValueError("Git object bundle is empty")
        subprocess.run(
            ["git", "bundle", "verify", str(output)],
            cwd=ephemeral,
            check=True,
            capture_output=True,
        )
    return output.read_bytes()


def _controller(args: argparse.Namespace) -> None:
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    repo = Path(args.repo_root)
    base_sha = _exact_sha(_event_value(event, "pull_request", "base", "sha"), "base_sha")
    head_sha = _exact_sha(_event_value(event, "pull_request", "head", "sha"), "head_sha")
    workflow_sha = _exact_sha(event.get("workflow_sha"), "workflow_sha")
    _git(repo, "fetch", "--no-tags", "--unshallow", "origin", base_sha, head_sha)
    if _git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise ValueError("controller repository remains shallow")
    trees: dict[str, str] = {}
    for label, revision in (("base", base_sha), ("head", head_sha)):
        _git(repo, "cat-file", "-e", f"{revision}^{{commit}}")
        tree = _exact_sha(_git(repo, "rev-parse", f"{revision}^{{tree}}"), f"{label}_tree")
        _git(repo, "cat-file", "-e", f"{tree}^{{tree}}")
        trees[label] = tree
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
    runtime_dir = Path(args.runtime_dir)
    if not runtime_dir.is_dir() or any(
        not (runtime_dir / name).is_file() for name in RUNTIME_FILENAMES
    ):
        raise ValueError("runtime bundle is incomplete")
    pyproject = _git(repo, "show", f"{workflow_sha}:pyproject.toml", binary=True)
    uv_lock = _git(repo, "show", f"{workflow_sha}:uv.lock", binary=True)
    head_pyproject = _git(repo, "show", f"{head_sha}:pyproject.toml", binary=True)
    head_uv_lock = _git(repo, "show", f"{head_sha}:uv.lock", binary=True)
    assert all(
        isinstance(value, bytes) for value in (pyproject, uv_lock, head_pyproject, head_uv_lock)
    )
    if head_pyproject != pyproject or head_uv_lock != uv_lock:
        raise ValueError("PR dependency contract drifts from trusted default")
    requirements = (runtime_dir / "requirements.txt").read_bytes()
    runtime_archive = (runtime_dir / "runtime.tar").read_bytes()
    runtime_metadata = (runtime_dir / "runtime-metadata.json").read_bytes()
    runtime_identity = json.loads(runtime_metadata)
    golden_evaluator = _git(repo, "show", f"{workflow_sha}:{GOLDEN_EVALUATOR_PATH}", binary=True)
    golden_corpus = _git(repo, "show", f"{head_sha}:tests/golden_behavior/corpus.py", binary=True)
    golden_test_corpus = _git(
        repo, "show", f"{head_sha}:tests/golden_behavior/test_corpus.py", binary=True
    )
    topology_paths = _git(
        repo, "ls-tree", "-r", "--name-only", head_sha, "tests/golden_behavior", binary=False
    )
    assert isinstance(topology_paths, str)
    golden_topology = b"\n".join(
        path.encode() + b":" + _git(repo, "show", f"{head_sha}:{path}", binary=True)
        for path in sorted(topology_paths.splitlines())
        if path.endswith(".py")
    )
    assert isinstance(golden_evaluator, bytes)
    if (
        runtime_identity.get("schema_version") != RUNTIME_SCHEMA_VERSION
        or runtime_identity.get("pyproject_sha256") != _sha(pyproject)
        or runtime_identity.get("uv_lock_sha256") != _sha(uv_lock)
        or runtime_identity.get("requirements_sha256") != _sha(requirements)
        or runtime_identity.get("runtime_probe") != _runtime_probe()
        or runtime_identity.get("pytest_plugins") != PYTEST_PLUGINS
        or runtime_identity.get("builder") != {"uv_version": UV_VERSION}
    ):
        raise ValueError("runtime metadata does not match trusted contract")
    git_bundle = _create_git_bundle(repo, git_bundle_path, base_sha, head_sha, workflow_sha)
    manifest = build_manifest(
        event,
        raw_diff=raw_diff,
        test_inventory=selected,
        source_archive=source_archive,
        base_tree=trees["base"],
        head_tree=trees["head"],
        test_tree=_git(repo, "rev-parse", f"{head_sha}:tests"),
        git_bundle=git_bundle,
        pyproject=pyproject,
        uv_lock=uv_lock,
        requirements=requirements,
        runtime_archive=runtime_archive,
        runtime_metadata=runtime_metadata,
        runtime_identity=runtime_identity,
        golden_evaluator=golden_evaluator,
        golden_corpus=golden_corpus,
        golden_test_corpus=golden_test_corpus,
        golden_topology=golden_topology,
    )
    (output / "source.tar").write_bytes(source_archive)
    (output / "raw-diff.bin").write_bytes(raw_diff)
    (output / "test-inventory.json").write_bytes(_json(selected) + b"\n")
    (output / "manifest.json").write_bytes(_json(manifest) + b"\n")
    (output / "run_golden_behavior_eval.py").write_bytes(golden_evaluator)
    for name in RUNTIME_FILENAMES:
        (output / name).write_bytes((runtime_dir / name).read_bytes())
    (output / "external-anchor.json").write_bytes(
        _json(
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_sha256": _sha((output / "manifest.json").read_bytes()),
                "workflow_identity": manifest["workflow_identity"],
                "base_sha": manifest["base_sha"],
                "head_sha": manifest["head_sha"],
            }
        )
        + b"\n"
    )
    (output / "trusted_deletion_anchor.py").write_bytes(Path(__file__).read_bytes())


def _executor(args: argparse.Namespace) -> None:
    bundle = Path(args.bundle_dir)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    source_archive = (bundle / "source.tar").read_bytes()
    git_bundle = (bundle / "git-objects.bundle").read_bytes()
    if _sha(source_archive) != manifest.get("source_archive_sha256") or _sha(
        git_bundle
    ) != manifest.get("git_bundle_sha256"):
        raise ValueError("source or Git bundle identity mismatch")
    source = bundle / "source"
    source.mkdir()
    with tarfile.open(fileobj=BytesIO(source_archive)) as archive:
        archive.extractall(source, filter=_executor_archive_filter)
    _prepare_executor_git_context(bundle, source, manifest)
    requirements = (bundle / "requirements.txt").read_bytes()
    runtime_archive = (bundle / "runtime.tar").read_bytes()
    runtime_metadata_bytes = (bundle / "runtime-metadata.json").read_bytes()
    runtime_metadata = json.loads(runtime_metadata_bytes)
    if (
        _sha(requirements) != manifest.get("requirements_sha256")
        or _sha(runtime_archive) != manifest.get("runtime_archive_sha256")
        or _sha(runtime_metadata_bytes) != manifest.get("runtime_metadata_sha256")
        or runtime_metadata != manifest.get("runtime_identity")
        or runtime_metadata.get("runtime_probe") != _runtime_probe()
        or runtime_metadata.get("pytest_plugins") != PYTEST_PLUGINS
        or runtime_metadata.get("builder") != {"uv_version": UV_VERSION}
    ):
        raise ValueError("offline runtime identity mismatch")
    runtime = bundle / "runtime"
    runtime.mkdir()
    with tarfile.open(fileobj=BytesIO(runtime_archive)) as archive:
        archive.extractall(runtime, filter="data")
    site_packages = (runtime / "site-packages").resolve()
    if not site_packages.is_dir():
        raise ValueError("offline runtime site-packages is missing")
    executor_home = runtime / "home"
    executor_home.mkdir()
    environment = {
        "CI": "true",
        "HOME": str(executor_home),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PIP_NO_INDEX": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(site_packages),
        "TMPDIR": os.environ.get("RUNNER_TEMP", tempfile.gettempdir()),
        "UV_OFFLINE": "1",
    }
    plugin_probe = subprocess.run(
        [
            sys.executable,
            "-S",
            "-c",
            "import json,pytest,pytest_asyncio,pytest_timeout; "
            "print(json.dumps([pytest.__file__,pytest_asyncio.__file__,pytest_timeout.__file__]))",
        ],
        cwd=source,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    plugin_paths = json.loads(plugin_probe.stdout)
    if any(not Path(path).resolve().is_relative_to(site_packages) for path in plugin_paths):
        raise ValueError("pytest plugin resolved outside offline runtime")
    result = subprocess.run(
        [sys.executable, "-S", "-m", "pytest", *manifest["test_inventory"], "-q"],
        cwd=source,
        env=environment,
    )
    golden_report_path = bundle / "golden-report.json"
    golden_result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(bundle / "run_golden_behavior_eval.py"),
            "--repo-root",
            str(source),
            "--source-revision",
            manifest["head_sha"],
            "--source-tree",
            manifest["head_tree"],
            "--trusted-evaluator-sha256",
            manifest["golden_evaluator_sha256"],
            "--json-report",
            str(golden_report_path),
        ],
        cwd=source,
        env=environment,
    )
    if not golden_report_path.is_file():
        raise ValueError("canonical Golden report is missing")
    golden_report = json.loads(golden_report_path.read_text(encoding="utf-8"))
    evidence = {key: manifest[key] for key in REQUIRED_EVIDENCE_KEYS if key != "executor"}
    evidence["schema_version"] = SCHEMA_VERSION
    evidence["status"] = (
        "COMPLETE" if result.returncode == 0 and golden_result.returncode == 0 else "FAILED"
    )
    evidence["golden_report"] = golden_report
    evidence["golden_report_sha256"] = _sha(_json(golden_report))
    evidence["executor"] = {
        "exit_code": result.returncode,
        "selected_tests": manifest["test_inventory"],
        "pytest_plugins": PYTEST_PLUGINS,
        "runtime_probe": _runtime_probe(),
    }
    (bundle / "raw-evidence.json").write_bytes(_json(evidence) + b"\n")
    raise SystemExit(result.returncode or golden_result.returncode)


def _prepare_executor_git_context(bundle: Path, source: Path, manifest: dict[str, Any]) -> None:
    identity = manifest.get("workflow_identity")
    if not isinstance(identity, dict):
        raise ValueError("workflow identity is missing")
    expected = (
        (BASE_REF, _exact_sha(manifest.get("base_sha"), "base_sha")),
        (HEAD_REF, _exact_sha(manifest.get("head_sha"), "head_sha")),
        (WORKFLOW_REF, _exact_sha(identity.get("workflow_sha"), "workflow_sha")),
    )
    subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
    git_bundle = bundle / "git-objects.bundle"
    subprocess.run(
        ["git", "bundle", "verify", str(git_bundle)],
        cwd=source,
        check=True,
        capture_output=True,
    )
    for ref, revision in expected:
        _git(source, "fetch", "--no-tags", str(git_bundle), f"{ref}:{ref}")
        if (
            _git(source, "show-ref", "--verify", ref).split()[0] != revision
            or _git(source, "rev-parse", f"{ref}^{{commit}}") != revision
        ):
            raise ValueError(f"executor Git ref mismatch: {ref}")
    _git(source, "update-ref", "--no-deref", "HEAD", manifest["head_sha"])
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", manifest["base_sha"], manifest["head_sha"]],
        cwd=source,
        capture_output=True,
    )
    if (
        ancestry.returncode != 0
        or _git(source, "rev-parse", "HEAD") != manifest["head_sha"]
        or _git(source, "rev-parse", "HEAD^{tree}") != manifest["head_tree"]
        or _git(source, "rev-parse", f"{BASE_REF}^{{tree}}") != manifest["base_tree"]
        or _git(source, "rev-parse", "HEAD:tests") != manifest["test_tree"]
        or _extracted_test_tree(source) != manifest["test_tree"]
    ):
        raise ValueError("executor Git identity mismatch")


def _extracted_test_tree(source: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="trusted-anchor-index-") as directory:
        environment = {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_INDEX_FILE": str(Path(directory) / "index"),
            "HOME": directory,
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        }
        subprocess.run(
            ["git", "add", "-f", "--", "tests"],
            cwd=source,
            env=environment,
            check=True,
            capture_output=True,
        )
        root_tree = subprocess.run(
            ["git", "write-tree"],
            cwd=source,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return _git(source, "rev-parse", f"{root_tree}:tests")


def _executor_archive_filter(member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo | None:
    """Skip irrelevant external links while retaining the data filter."""

    try:
        return tarfile.data_filter(member, destination)
    except (tarfile.AbsoluteLinkError, tarfile.LinkOutsideDestinationError):
        return None


def _verifier(args: argparse.Namespace) -> None:
    bundle = Path(args.bundle_dir)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    evidence_path = Path(args.verify_evidence)
    if evidence_path != bundle / "raw-evidence.json" or not evidence_path.is_file():
        raise SystemExit(1)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    anchor = json.loads((bundle / "external-anchor.json").read_text(encoding="utf-8"))
    manifest_bytes = (bundle / "manifest.json").read_bytes()
    anchor_bytes = (bundle / "external-anchor.json").read_bytes()
    expected_identity = {
        "event_name": args.expected_event_name,
        "repository": args.expected_repository,
        "default_branch": args.expected_default_branch,
        "workflow_ref": args.expected_workflow_ref,
        "workflow_sha": _exact_sha(args.expected_workflow_sha, "workflow_sha"),
        "run_id": args.expected_run_id,
        "pull_request_number": args.expected_pull_request_number,
    }
    if (
        _sha(manifest_bytes) != args.expected_manifest_sha256
        or _sha(anchor_bytes) != args.expected_external_anchor_sha256
        or anchor.get("manifest_sha256") != args.expected_manifest_sha256
        or anchor.get("workflow_identity") != expected_identity
        or anchor.get("base_sha") != args.expected_base_sha
        or anchor.get("head_sha") != args.expected_head_sha
        or manifest.get("workflow_identity") != expected_identity
        or manifest.get("base_sha") != args.expected_base_sha
        or manifest.get("head_sha") != args.expected_head_sha
    ):
        raise SystemExit(1)
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
        subprocess.run(
            ["git", "bundle", "verify", str(bundle / "git-objects.bundle")],
            cwd=git_repo,
            check=True,
            capture_output=True,
        )
        for ref, revision in (
            (BASE_REF, manifest["base_sha"]),
            (HEAD_REF, manifest["head_sha"]),
            (WORKFLOW_REF, args.expected_workflow_sha),
        ):
            _git(git_repo, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            if (
                _git(git_repo, "show-ref", "--verify", f"refs/{ref.removeprefix('refs/')}").split()[
                    0
                ]
                != revision
            ):
                raise SystemExit(1)
            if _git(git_repo, "rev-parse", f"{ref}^{{commit}}") != revision:
                raise SystemExit(1)
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
        recomputed_base_tree = _git(git_repo, "rev-parse", f"{manifest['base_sha']}^{{tree}}")
        recomputed_head_tree = _git(git_repo, "rev-parse", f"{manifest['head_sha']}^{{tree}}")
        recomputed_test_tree = _git(git_repo, "rev-parse", f"{manifest['head_sha']}:tests")
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
        trusted_pyproject = _git(
            git_repo, "show", f"{args.expected_workflow_sha}:pyproject.toml", binary=True
        )
        trusted_uv_lock = _git(
            git_repo, "show", f"{args.expected_workflow_sha}:uv.lock", binary=True
        )
        head_pyproject = _git(
            git_repo, "show", f"{manifest['head_sha']}:pyproject.toml", binary=True
        )
        head_uv_lock = _git(git_repo, "show", f"{manifest['head_sha']}:uv.lock", binary=True)
        if head_pyproject != trusted_pyproject or head_uv_lock != trusted_uv_lock:
            raise SystemExit(1)
    status = verify_evidence(
        manifest,
        evidence,
        source_archive=(bundle / "source.tar").read_bytes(),
        raw_diff=(bundle / "raw-diff.bin").read_bytes(),
        test_inventory=json.loads((bundle / "test-inventory.json").read_text(encoding="utf-8")),
        git_bundle=git_bundle,
        requirements=(bundle / "requirements.txt").read_bytes(),
        runtime_archive=(bundle / "runtime.tar").read_bytes(),
        runtime_metadata=(bundle / "runtime-metadata.json").read_bytes(),
        golden_evaluator=(bundle / "run_golden_behavior_eval.py").read_bytes(),
        recomputed_pyproject=trusted_pyproject,
        recomputed_uv_lock=trusted_uv_lock,
        recomputed_base_tree=recomputed_base_tree,
        recomputed_head_tree=recomputed_head_tree,
        recomputed_test_tree=recomputed_test_tree,
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
    controller.add_argument("--runtime-dir", required=True)
    controller.set_defaults(function=_controller)
    runtime_builder = subparsers.add_parser("runtime-builder")
    runtime_builder.add_argument("--repo-root", required=True)
    runtime_builder.add_argument("--workflow-sha", required=True)
    runtime_builder.add_argument("--uv-executable", required=True)
    runtime_builder.add_argument("--output-dir", required=True)
    runtime_builder.set_defaults(function=_build_runtime)
    executor = subparsers.add_parser("executor")
    executor.add_argument("--bundle-dir", required=True)
    executor.set_defaults(function=_executor)
    verifier = subparsers.add_parser("verifier")
    verifier.add_argument("--bundle-dir", required=True)
    verifier.add_argument("--expected-workflow-ref", required=True)
    verifier.add_argument("--expected-workflow-sha", required=True)
    verifier.add_argument("--expected-run-id", required=True, type=int)
    verifier.add_argument("--verify-evidence", required=True)
    verifier.add_argument("--expected-manifest-sha256", required=True)
    verifier.add_argument("--expected-external-anchor-sha256", required=True)
    verifier.add_argument("--expected-event-name", required=True)
    verifier.add_argument("--expected-repository", required=True)
    verifier.add_argument("--expected-default-branch", required=True)
    verifier.add_argument("--expected-pull-request-number", required=True, type=int)
    verifier.add_argument("--expected-base-sha", required=True)
    verifier.add_argument("--expected-head-sha", required=True)
    verifier.set_defaults(function=_verifier)
    args = parser.parse_args()
    args.function(args)


if __name__ == "__main__":
    main()
