#!/usr/bin/env python3
"""Trusted exact-base impact gate: controller / unprivileged executor / verifier (#1754 B).

The legacy ``impact-gate`` job runs from PR-controlled ``pull_request`` YAML and
classifies plan/result files that the head copy of ``pr_impact_gate.py``
produced.  This module is the ``pull_request_target`` replacement:

* ``controller`` (default-branch code, never imports head code) derives the
  impact plan with the trusted ``pr_impact_gate``/``select_tests`` functions,
  computes the per-side run specification and writes a hash-bound bundle.
* ``executor`` (``permissions: {}``) runs the planned pytest targets on one
  side (base or head) and records only the exit code and the raw JUnit file.
* ``verifier`` (default-branch code, stdlib only) independently re-derives the
  plan from a fresh fetch of the exact base/head commits, rebuilds each
  ``PytestRunResult`` from the JUnit evidence itself and classifies with the
  trusted ``classify_regression``.  Anything malformed fails closed.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.parsers import expat

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops import pr_impact_gate as gate  # noqa: E402
from scripts.ops import select_tests  # noqa: E402
from scripts.ops import trusted_deletion_anchor as anchor  # noqa: E402

SCHEMA_VERSION = "trusted-impact-gate.v1"
WORKFLOW_PATH = ".github/workflows/trusted-impact-gate.yml"
SIDES = ("base", "head")
SIDE_REFS = {"base": anchor.BASE_REF, "head": anchor.HEAD_REF}
CODE_FILES = (
    "scripts/__init__.py",
    "scripts/ops/__init__.py",
    "scripts/ops/pr_impact_gate.py",
    "scripts/ops/select_tests.py",
    "scripts/ops/trusted_deletion_anchor.py",
    "scripts/ops/trusted_impact_gate.py",
)
BUNDLE_FILES = (
    "plan.json",
    "git-objects.bundle",
    *anchor.RUNTIME_FILENAMES,
    *(f"code/{path}" for path in CODE_FILES),
)
IMPACT_MAP_PATH = "docs/testing/test_impact_map.md"
IMPACT_INDEX_PATH = ".nexus/test_impact_index.json"
EVIDENCE_KEYS = frozenset({
    "schema_version",
    "side",
    "revision",
    "tree",
    "manifest_sha256",
    "mode",
    "pytest_args",
    "pytest_exit_code",
    "junit_sha256",
})
MAX_JUNIT_BYTES = 64 * 1024 * 1024
_GIT_ENV_OVERRIDES = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_LFS_SKIP_SMUDGE": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


class GateError(ValueError):
    """A fail-closed trust violation with an operator-readable reason."""


# --------------------------------------------------------------------------- identity


def identity(event: dict[str, Any]) -> dict[str, Any]:
    """Return the trusted PR identity, refusing forks and non-default-branch YAML."""

    if not isinstance(event, dict):
        raise GateError("event payload is not an object")
    try:
        repository = anchor._event_value(event, "repository", "full_name")
        default_branch = anchor._event_value(event, "repository", "default_branch")
        base_repo = anchor._event_value(event, "pull_request", "base", "repo", "full_name")
        base_ref = anchor._event_value(event, "pull_request", "base", "ref")
        number = anchor._event_value(event, "pull_request", "number")
        base_sha = anchor._exact_sha(
            anchor._event_value(event, "pull_request", "base", "sha"), "base_sha"
        )
        head_sha = anchor._exact_sha(
            anchor._event_value(event, "pull_request", "head", "sha"), "head_sha"
        )
        head = anchor._event_value(event, "pull_request", "head")
        workflow_sha = anchor._exact_sha(event.get("workflow_sha"), "workflow_sha")
    except ValueError as exc:
        raise GateError(str(exc)) from None
    head_repo = head.get("repo") if isinstance(head, dict) else None
    head_repo_name = head_repo.get("full_name") if isinstance(head_repo, dict) else None
    if head_repo_name != repository:
        raise GateError(
            "fork pull requests are not supported by the trusted impact gate: "
            f"head repository {head_repo_name!r} != base repository {repository!r}"
        )
    expected_ref = f"{repository}/{WORKFLOW_PATH}@refs/heads/{default_branch}"
    if event.get("event_name") != "pull_request_target" or event.get("workflow_ref") != (
        expected_ref
    ):
        raise GateError("workflow identity is not trusted default-branch pull_request_target")
    if base_repo != repository or base_ref != default_branch:
        raise GateError("pull request does not target the trusted default branch")
    run_id = event.get("run_id")
    if type(run_id) is not int or run_id <= 0:
        raise GateError("run_id must be a positive integer")
    if type(number) is not int or number <= 0:
        raise GateError("pull request number must be a positive integer")
    if base_sha == head_sha:
        raise GateError("base and head revisions are identical")
    return {
        "event_name": "pull_request_target",
        "repository": repository,
        "default_branch": default_branch,
        "workflow_ref": expected_ref,
        "workflow_sha": workflow_sha,
        "run_id": run_id,
        "pull_request_number": number,
        "base_sha": base_sha,
        "head_sha": head_sha,
    }


# --------------------------------------------------------------------------- git helpers


def _git_env(home: Path | None = None) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(_GIT_ENV_OVERRIDES)
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    if home is not None:
        environment["HOME"] = str(home)
    return environment


def _git_ok(repo: Path, *args: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, env=_git_env()
        ).returncode
        == 0
    )


def _show_or_empty(repo: Path, revision: str, path: str) -> bytes:
    if not _git_ok(repo, "cat-file", "-e", f"{revision}:{path}"):
        return b""
    value = anchor._git(repo, "show", f"{revision}:{path}", binary=True)
    assert isinstance(value, bytes)
    return value


def _regular_file(repo: Path, revision: str, path: str) -> bool:
    entry = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", revision, "--", path],
        capture_output=True,
        text=True,
        env=_git_env(),
    )
    metadata, _, listed = entry.stdout.rstrip("\n").partition("\t")
    fields = metadata.split()
    return (
        entry.returncode == 0
        and listed == path
        and len(fields) == 3
        and fields[0] in {"100644", "100755"}
        and fields[1] == "blob"
    )


def _path_exists(repo: Path, revision: str, path: str) -> bool:
    parts = Path(path).parts
    if not path or path.startswith("/") or ".." in parts:
        return False
    return _git_ok(repo, "cat-file", "-e", f"{revision}:{path}")


def _tree_files(repo: Path, revision: str) -> set[str]:
    listing = anchor._git(repo, "ls-tree", "-r", "-z", "--name-only", revision, binary=True)
    assert isinstance(listing, bytes)
    return {item.decode("utf-8") for item in listing.split(b"\0") if item}


def _trees(repo: Path, revision: str) -> tuple[str, str]:
    try:
        return gate._git_revision_trees(repo, revision)
    except ValueError as exc:
        raise GateError(f"cannot resolve exact trees for {revision}: {exc}") from None


# --------------------------------------------------------------------------- plan


def _trusted_rules(
    base_map: bytes, head_map: bytes, directory: Path
) -> tuple[list[Any], list[Any]]:
    """Return ``(base-only rules, merged rules)``.

    Merged rules are the base rows plus head rows for code paths no base row
    covers.  Head rows are *additive only*: ``combine_plans`` unions the merged
    plan's targets with the base-only plan's, so a head row -- even one whose
    code path (file or directory prefix) already exists in the base tree but
    is unmapped -- can add targets but can never remove a base-only target.
    """

    rules: dict[str, list[Any]] = {}
    for label, data in (("base", base_map), ("head", head_map)):
        path = directory / f"{label}-impact-map.md"
        path.write_bytes(data)
        rules[label] = select_tests.load_impact_rules(path)

    def covered(code_path: str) -> bool:
        return any(
            code_path == rule.code_path or code_path.startswith(f"{rule.code_path}/")
            for rule in rules["base"]
        )

    merged = [*rules["base"], *(rule for rule in rules["head"] if not covered(rule.code_path))]
    return list(rules["base"]), merged


def _trusted_index(base_index: bytes, head_index: bytes, directory: Path) -> tuple[Path, Path]:
    """Return ``(base-only index, merged index)``; head keys never replace base keys.

    Like head map rows, head index keys are additive only (see ``combine_plans``).
    """

    loaded: dict[str, dict[str, list[str]]] = {}
    for label, data in (("head", head_index), ("base", base_index)):
        path = directory / f"{label}-impact-index.json"
        path.write_bytes(data)
        loaded[label] = select_tests.load_impact_index(path)
    outputs = []
    for label, mappings in (
        ("base-only", loaded["base"]),
        ("merged", {**loaded["head"], **loaded["base"]}),
    ):
        output = directory / f"trusted-{label}-impact-index.json"
        output.write_text(json.dumps({"mappings": mappings}, sort_keys=True), encoding="utf-8")
        outputs.append(output)
    return outputs[0], outputs[1]


def combine_plans(base_only: dict[str, Any], merged: dict[str, Any]) -> dict[str, Any]:
    """Head impact data may ADD, never REMOVE.

    * Targets are the union of both plans, so every base-only target (fallback,
      mandatory Tier-2, mapped tests) for any changed path stays selected.
      The single exception: when head rows/keys map every path the base-only
      plan left unmapped (base-only ``UNMAPPED_FULL_SUITE``, merged plan
      neither unknown nor FULL_SUITE), only the ``tests`` FULL_SUITE target is
      lifted; the base-only scoped and Tier 2 targets stay selected.
    * Impact class/tier/confidence come from the merged plan but never drop
      below the base-only plan, except when the base-only plan was
      ``IMPACT_UNKNOWN`` or the FULL_SUITE fallback and head rows/keys now map
      the paths; then the merged class/tier is used, still with the union of
      the remaining targets.
    * A merged ``IMPACT_UNKNOWN`` is never replaced by the Tier 3 fallback.
    """

    combined = dict(merged)
    full_suite = gate.FULL_SUITE_IMPACT_CLASS
    # #2092: head rows may resolve a path the base map left unmapped, exactly as
    # they could resolve the former IMPACT_UNKNOWN; the base-only scoped and Tier 2
    # targets are still kept, only the tests/ fallback itself is dropped.
    head_resolved_fallback = base_only["impact_class"] == full_suite and merged[
        "impact_class"
    ] not in {gate._UNKNOWN, full_suite}
    base_targets = [
        target
        for target in base_only["pytest_targets"]
        if not (head_resolved_fallback and target in gate.FULL_SUITE_TARGETS)
    ]
    targets = list(merged["pytest_targets"])
    targets += [target for target in base_targets if target not in targets]
    combined["pytest_targets"] = targets
    combined["pytest_required"] = bool(targets) or bool(
        merged["pytest_required"] or base_only["pytest_required"]
    )
    combined["workflow_validation_required"] = bool(
        merged["workflow_validation_required"] or base_only["workflow_validation_required"]
    )
    head_resolved_unknown = (
        base_only["impact_class"] == gate._UNKNOWN and merged["impact_class"] != gate._UNKNOWN
    ) or head_resolved_fallback
    if not head_resolved_unknown:
        combined["confidence"] = min(merged["confidence"], base_only["confidence"])
        # A merged IMPACT_UNKNOWN is never replaced by a higher-tier base class
        # (the Tier 3 FULL_SUITE fallback): unknown stays unknown.
        if base_only["impact_class"] == gate._UNKNOWN or (
            base_only["tier"] > merged["tier"] and merged["impact_class"] != gate._UNKNOWN
        ):
            combined["tier"] = base_only["tier"]
            combined["impact_class"] = base_only["impact_class"]
    # A combined FULL_SUITE fallback records every path either plan left unmapped;
    # any other combined class carries no fallback.
    if combined["impact_class"] == full_suite:
        unmatched = list(merged.get("unmatched_paths", []))
        unmatched += [
            path for path in base_only.get("unmatched_paths", []) if path not in unmatched
        ]
        combined["unmatched_paths"] = unmatched
        combined["fallback"] = gate.FULL_SUITE_FALLBACK
    else:
        combined["fallback"] = ""
    reasons = list(merged["reasons"])
    if head_resolved_fallback:
        reasons.append(
            "trusted gate: head impact rows lifted only the tests/ FULL_SUITE fallback; "
            "base-only scoped and Tier 2 targets stay selected"
        )
    elif targets != merged["pytest_targets"] or head_resolved_unknown:
        reasons.append("trusted gate: head impact data may add but never remove base-only targets")
    combined["reasons"] = reasons
    return combined


@contextlib.contextmanager
def _trusted_selection(head_root: Path, rules: list[Any], index_path: Path) -> Iterator[None]:
    missing = head_root.parent / "absent-selection-data.json"
    saved = (gate.load_impact_rules, gate.select_target_details, select_tests.ROOT)
    gate.load_impact_rules = lambda *_args, **_kwargs: list(rules)
    gate.select_target_details = functools.partial(
        select_tests.select_target_details,
        index_path=index_path,
        stats_path=missing,
        history_path=missing,
    )
    select_tests.ROOT = head_root
    try:
        yield
    finally:
        gate.load_impact_rules, gate.select_target_details, select_tests.ROOT = saved


def derive_plan(repo: Path, base_sha: str, head_sha: str) -> dict[str, Any]:
    """Compute the impact plan with trusted code over the exact base/head trees.

    The head tree is materialized only as data (existence checks); nothing from
    it is imported or executed.  Two plans are built -- base-only selection
    data, and base data plus admissible head rows/index keys -- and combined
    with ``combine_plans`` so head data can add targets but never remove one.
    The verifier calls this same function, so its re-derivation is identical.
    """

    for revision in (base_sha, head_sha):
        anchor._exact_sha(revision, "revision")
        if not _git_ok(repo, "cat-file", "-e", f"{revision}^{{commit}}"):
            raise GateError(f"exact commit {revision} is unavailable")
    with tempfile.TemporaryDirectory(
        prefix="trusted-impact-plan-", ignore_cleanup_errors=True
    ) as directory:
        work = Path(directory)
        head_root = work / "head-tree"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(head_root), head_sha],
            check=True,
            capture_output=True,
            env=_git_env(work / "home"),
        )
        try:
            base_rules, merged_rules = _trusted_rules(
                _show_or_empty(repo, base_sha, IMPACT_MAP_PATH),
                _show_or_empty(repo, head_sha, IMPACT_MAP_PATH),
                work,
            )
            base_index, merged_index = _trusted_index(
                _show_or_empty(repo, base_sha, IMPACT_INDEX_PATH),
                _show_or_empty(repo, head_sha, IMPACT_INDEX_PATH),
                work,
            )
            changed = gate._git_changed_paths(base_sha, head_sha, root=head_root)
            plans = []
            for rules, index_path in ((base_rules, base_index), (merged_rules, merged_index)):
                with _trusted_selection(head_root, rules, index_path):
                    plans.append(
                        asdict(
                            gate.build_impact_plan(
                                changed, base_sha=base_sha, head_sha=head_sha, root=head_root
                            )
                        )
                    )
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(head_root)],
                capture_output=True,
                env=_git_env(work / "home"),
            )
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "prune"],
                capture_output=True,
                env=_git_env(work / "home"),
            )
    return combine_plans(plans[0], plans[1])


def plan_digest(plan: dict[str, Any]) -> str:
    """Digest exactly as ``pr_impact_gate.run_pytest_plan`` computes it."""

    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def side_spec(repo: Path, plan: dict[str, Any], side: str) -> dict[str, Any]:
    """Recompute what ``run_pytest_plan`` would do for one side, from Git only."""

    if side not in SIDES:
        raise GateError(f"unknown side {side!r}")
    revision = plan["base_sha"] if side == "base" else plan["head_sha"]
    source_tree, test_inventory_tree = _trees(repo, revision)
    bound = (
        (plan.get("base_source_tree"), plan.get("base_test_inventory_tree"))
        if side == "base"
        else (plan.get("source_tree"), plan.get("test_inventory_tree"))
    )
    if bound != (source_tree, test_inventory_tree):
        raise GateError(f"{side} trees drifted from the immutable plan binding")
    targets = [str(item) for item in plan.get("pytest_targets", []) if str(item).strip()]
    existing = [t for t in targets if _path_exists(repo, revision, t.split("::", 1)[0])]
    missing = [t for t in targets if t not in existing]
    changed = {str(path) for path in plan.get("changed_paths", [])}
    unexpected = [
        t
        for t in missing
        if not (
            side == "base"
            and t.split("::", 1)[0] in changed
            and t.split("::", 1)[0].startswith("tests/")
        )
    ]
    pytest_args: list[str] = []
    executed: list[str] = list(existing)
    if not targets:
        mode, executed, missing = "no_targets", [], []
    elif not existing:
        mode = "none_exist"
    elif "tests/core" in existing and not _regular_file(
        repo, revision, gate.OPTIONAL_BROWSER_EXCLUSION
    ):
        mode = "exclusion_defect"
    else:
        mode = "pytest"
        pytest_args = list(existing)
        if "tests/core" in existing:
            pytest_args.append(f"--ignore={gate.OPTIONAL_BROWSER_EXCLUSION}")
        pytest_args.extend(gate.full_suite_pytest_args(str(plan.get("impact_class", ""))))
    return {
        "side": side,
        "revision": revision,
        "source_tree": source_tree,
        "test_inventory_tree": test_inventory_tree,
        "mode": mode,
        "selected_targets": targets,
        "executed_targets": executed,
        "missing_targets": missing,
        "unexpected_missing_targets": unexpected,
        "pytest_args": pytest_args,
    }


# --------------------------------------------------------------------------- bundle


def _sha_file(path: Path) -> str:
    return anchor._sha(path.read_bytes())


def _check_runtime(metadata_bytes: bytes, pyproject: bytes, uv_lock: bytes, req: bytes) -> dict:
    metadata = json.loads(metadata_bytes)
    try:
        packages = anchor._trusted_external_package_contract_with_provenance(
            metadata.get("external_packages")
        )
    except ValueError as exc:
        raise GateError(str(exc)) from None
    if (
        metadata.get("schema_version") != anchor.RUNTIME_SCHEMA_VERSION
        or metadata.get("pyproject_sha256") != anchor._sha(pyproject)
        or metadata.get("uv_lock_sha256") != anchor._sha(uv_lock)
        or metadata.get("requirements_sha256") != anchor._sha(req)
        or metadata.get("runtime_probe") != anchor._runtime_probe()
        or metadata.get("pytest_plugins") != anchor.PYTEST_PLUGINS
        or metadata.get("dependency_groups") != list(anchor.TRUSTED_RUNTIME_DEPENDENCY_GROUPS)
        or metadata.get("external_packages") != packages
        or metadata.get("builder") != {"uv_version": anchor.UV_VERSION}
    ):
        raise GateError("runtime metadata does not match the trusted contract")
    return metadata


def load_manifest(bundle: Path, expected_sha256: str) -> dict[str, Any]:
    """Load the controller manifest and verify every bundle file it binds."""

    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise GateError("controller manifest is missing")
    raw = manifest_path.read_bytes()
    if anchor._sha(raw) != expected_sha256:
        raise GateError("controller manifest digest does not match the controller job output")
    try:
        manifest = json.loads(raw)
    except ValueError:
        raise GateError("controller manifest is not JSON") from None
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise GateError("controller manifest schema mismatch")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != set(BUNDLE_FILES):
        raise GateError("controller manifest file set mismatch")
    present = {
        path.relative_to(bundle).as_posix()
        for path in bundle.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if present != {*BUNDLE_FILES, "manifest.json"}:
        raise GateError("controller bundle contains missing or unexpected files")
    for name, digest in files.items():
        path = bundle / name
        if path.is_symlink() or not path.is_file() or _sha_file(path) != digest:
            raise GateError(f"bundle hash mismatch: {name}")
    return manifest


def write_bundle(
    repo: Path,
    ident: dict[str, Any],
    output: Path,
    *,
    runtime_files: dict[str, bytes],
    runtime_identity: dict[str, Any],
) -> dict[str, Any]:
    """Write the hash-bound controller bundle; the plan comes only from trusted code."""

    base_sha, head_sha = ident["base_sha"], ident["head_sha"]
    plan = derive_plan(repo, base_sha, head_sha)
    sides = {side: side_spec(repo, plan, side) for side in SIDES}
    output.mkdir(parents=True, exist_ok=False)
    (output / "plan.json").write_bytes(anchor._json(plan) + b"\n")
    anchor._create_git_bundle(
        repo, output / "git-objects.bundle", base_sha, head_sha, ident["workflow_sha"]
    )
    for name in anchor.RUNTIME_FILENAMES:
        (output / name).write_bytes(runtime_files[name])
    for path in CODE_FILES:
        destination = output / "code" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "workflow_identity": ident,
        "plan_sha256": _sha_file(output / "plan.json"),
        "plan_digest": plan_digest(plan),
        "sides": sides,
        "runtime_identity": runtime_identity,
        "files": {name: _sha_file(output / name) for name in BUNDLE_FILES},
    }
    (output / "manifest.json").write_bytes(anchor._json(manifest) + b"\n")
    return manifest


def _controller(args: argparse.Namespace) -> int:
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    ident = identity(event)
    repo = Path(args.repo_root)
    fetch_args = ["fetch", "--no-tags"]
    if anchor._git(repo, "rev-parse", "--is-shallow-repository") == "true":
        fetch_args.append("--unshallow")
    anchor._git(
        repo, *fetch_args, "origin", ident["base_sha"], ident["head_sha"], ident["workflow_sha"]
    )
    if anchor._git(repo, "rev-parse", "--is-shallow-repository") != "false":
        raise GateError("controller repository is still shallow after --unshallow")
    runtime_dir = Path(args.runtime_dir)
    runtime_files = {name: (runtime_dir / name).read_bytes() for name in anchor.RUNTIME_FILENAMES}
    runtime_identity = _check_runtime(
        runtime_files["runtime-metadata.json"],
        _show_or_empty(repo, ident["workflow_sha"], "pyproject.toml"),
        _show_or_empty(repo, ident["workflow_sha"], "uv.lock"),
        runtime_files["requirements.txt"],
    )
    manifest = write_bundle(
        repo,
        ident,
        Path(args.output_dir),
        runtime_files=runtime_files,
        runtime_identity=runtime_identity,
    )
    print(json.dumps(manifest["sides"], indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- executor


def _prepare_runtime(bundle: Path, manifest: dict[str, Any], work: Path) -> Path:
    metadata = json.loads((bundle / "runtime-metadata.json").read_bytes())
    if metadata != manifest.get("runtime_identity") or metadata.get("runtime_probe") != (
        anchor._runtime_probe()
    ):
        raise GateError("offline runtime identity mismatch")
    runtime = work / "runtime"
    runtime.mkdir()
    with tarfile.open(fileobj=BytesIO((bundle / "runtime.tar").read_bytes())) as archive:
        archive.extractall(runtime, filter="data")
    site_packages = (runtime / "site-packages").resolve()
    if anchor._verify_external_runtime_packages(site_packages) != metadata.get("external_packages"):
        raise GateError("offline external runtime package identity mismatch")
    return site_packages


def _materialize(bundle: Path, spec: dict[str, Any], work: Path) -> Path:
    source = work / "source"
    environment = _git_env(work / "git-home")
    (work / "git-home").mkdir(exist_ok=True)

    def git(*git_args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(source), *git_args],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()

    subprocess.run(
        ["git", "init", "-q", str(source)], check=True, capture_output=True, env=environment
    )
    ref = SIDE_REFS[spec["side"]]
    git("fetch", "-q", "--no-tags", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
    git("checkout", "-q", "--detach", spec["revision"])
    if (
        git("rev-parse", "HEAD") != spec["revision"]
        or git("rev-parse", "HEAD^{tree}") != spec["source_tree"]
        or git("status", "--porcelain")
    ):
        raise GateError("executor worktree does not match the exact planned tree")
    return source


def _executor(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle_dir)
    manifest = load_manifest(bundle, args.expected_manifest_sha256)
    spec = manifest["sides"][args.side]
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "side": args.side,
        "revision": spec["revision"],
        "tree": spec["source_tree"],
        "manifest_sha256": args.expected_manifest_sha256,
        "mode": spec["mode"],
        "pytest_args": spec["pytest_args"],
        "pytest_exit_code": None,
        "junit_sha256": None,
    }
    if spec["mode"] == "pytest":
        work = Path(tempfile.mkdtemp(prefix=f"trusted-impact-{args.side}-"))
        site_packages = _prepare_runtime(bundle, manifest, work)
        source = _materialize(bundle, spec, work)
        home = work / "home"
        home.mkdir()
        environment = {
            "CI": "true",
            "HOME": str(home),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "PIP_NO_INDEX": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(site_packages),
            "TMPDIR": os.environ.get("RUNNER_TEMP", tempfile.gettempdir()),
            "UV_OFFLINE": "1",
            "GIT_AUTHOR_NAME": "Nexus CI",
            "GIT_AUTHOR_EMAIL": "nexus-ci@example.invalid",
            "GIT_COMMITTER_NAME": "Nexus CI",
            "GIT_COMMITTER_EMAIL": "nexus-ci@example.invalid",
        }
        junit = output / "junit.xml"
        with (output / "pytest-output.log").open("wb") as log:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-m",
                    "pytest",
                    *spec["pytest_args"],
                    "-q",
                    f"--junitxml={junit}",
                ],
                cwd=source,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        evidence["pytest_exit_code"] = completed.returncode
        if junit.is_file():
            evidence["junit_sha256"] = _sha_file(junit)
    (output / "executor-evidence.json").write_bytes(anchor._json(evidence) + b"\n")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


# --------------------------------------------------------------------------- verifier


def _node_path(module: str, files: set[str], directories: set[str]) -> str | None:
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end])
        if f"{candidate}.py" in files:
            return f"{candidate}.py"
        if end == len(parts) and candidate in directories:
            return candidate
    return None


def _under(path: str, target: str) -> bool:
    return path == target or path.startswith(f"{target}/")


def reject_dtd_and_entities(junit: bytes, side: str) -> None:
    """Stdlib-only (no defusedxml) expat pass that refuses any DTD or entity declaration."""

    def refuse(*_args: object) -> None:
        raise GateError(f"{side} junit declares a DTD or entity")

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.UnparsedEntityDeclHandler = refuse
    try:
        parser.Parse(junit, True)
    except expat.ExpatError:
        raise GateError(f"{side} junit is not well-formed XML") from None


def validate_junit(junit: bytes, spec: dict[str, Any], files: set[str]) -> None:
    """Fail closed unless the JUnit node set matches exactly the executed targets."""

    if len(junit) > MAX_JUNIT_BYTES:
        raise GateError(f"{spec['side']} junit exceeds the size limit")
    try:
        text = junit.decode("utf-8")
    except UnicodeDecodeError:
        raise GateError(f"{spec['side']} junit is not UTF-8") from None
    declaration = re.match(r"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']", text)
    if text.startswith("\ufeff") or (
        declaration and declaration.group(1).lower().replace("_", "-") not in {"utf-8", "utf8"}
    ):
        raise GateError(f"{spec['side']} junit declares a non-UTF-8 encoding")
    if "<!DOCTYPE" in text or "<!ENTITY" in text or b"<!DOCTYPE" in junit or b"<!ENTITY" in junit:
        raise GateError(f"{spec['side']} junit declares a DTD or entity")
    reject_dtd_and_entities(junit, spec["side"])
    try:
        # nosec B314: the input is size-capped, strict UTF-8, and was proven free of any
        # DOCTYPE/entity declaration by reject_dtd_and_entities (expat) above.
        root = ET.fromstring(junit)  # nosec B314
    except ET.ParseError:
        raise GateError(f"{spec['side']} junit is not well-formed XML") from None
    if root.tag not in {"testsuites", "testsuite"}:
        raise GateError(f"{spec['side']} junit root element is not a test suite")
    directories = {str(parent) for path in files for parent in Path(path).parents}
    directories.discard(".")
    targets = [target.split("::", 1)[0] for target in spec["executed_targets"]]
    ignored = [
        arg.removeprefix("--ignore=") for arg in spec["pytest_args"] if arg.startswith("--ignore=")
    ]
    covered: set[str] = set()
    outcomes: dict[str, list[bool]] = {}
    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        node = f"{classname}::{name}" if classname else name
        if not node:
            raise GateError(f"{spec['side']} junit contains an anonymous testcase")
        path = _node_path(classname or name, files, directories)
        if path is None:
            raise GateError(f"{spec['side']} junit node {node!r} maps to no file in the tree")
        if any(_under(path, item) for item in ignored) or not any(
            _under(path, target) for target in targets
        ):
            raise GateError(f"{spec['side']} junit node {node!r} is outside the planned targets")
        covered.update(target for target in targets if _under(path, target))
        nonpassing = case.find("failure") is not None or case.find("error") is not None
        outcomes.setdefault(node, []).append(nonpassing)
    for node, observed in outcomes.items():
        if len(observed) > 1 and not all(observed):
            raise GateError(f"{spec['side']} junit node {node!r} is duplicated inconsistently")
    # Only test modules (pytest.ini python_files = test_*.py) must yield results;
    # a changed conftest.py/helper or a directory may legitimately collect none.
    uncovered = sorted(
        target
        for target in set(targets) - covered
        if Path(target).name.startswith("test_") and target.endswith(".py")
    )
    if uncovered:
        raise GateError(f"{spec['side']} junit has no results for planned targets {uncovered}")
    # The relaxation above must not let a run with planned targets report an
    # empty result: at least one planned target has to yield a testcase.
    if targets and not covered:
        raise GateError(f"{spec['side']} junit has no results for any planned target")


def reconstruct_result(
    spec: dict[str, Any],
    plan: dict[str, Any],
    evidence: Any,
    junit: bytes | None,
    files: set[str],
    *,
    expected_manifest_sha256: str,
    verifier_digest: str,
) -> gate.PytestRunResult:
    """Rebuild the ``PytestRunResult`` that ``run_pytest_plan`` would have written."""

    side = spec["side"]
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_KEYS:
        raise GateError(f"{side} executor evidence schema mismatch")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "side": side,
        "revision": spec["revision"],
        "tree": spec["source_tree"],
        "manifest_sha256": expected_manifest_sha256,
        "mode": spec["mode"],
        "pytest_args": spec["pytest_args"],
    }
    for key, value in expected.items():
        if not anchor._type_strict_equal(evidence[key], value):
            raise GateError(f"{side} executor evidence {key} does not match the trusted plan")
    exit_code = evidence["pytest_exit_code"]
    junit_sha256 = evidence["junit_sha256"]
    ran = spec["mode"] == "pytest"
    if ran:
        if type(exit_code) is not int:
            raise GateError(f"{side} executor did not record a pytest exit code")
        if junit_sha256 is None:
            if junit is not None:
                raise GateError(f"{side} junit is present but unbound")
        elif junit is None or anchor._sha(junit) != junit_sha256:
            raise GateError(f"{side} junit digest mismatch")
    elif exit_code is not None or junit_sha256 is not None or junit is not None:
        raise GateError(f"{side} executor reported a pytest run that the plan does not require")

    impact_class = str(plan.get("impact_class", "IMPACT_UNKNOWN"))
    targets = spec["selected_targets"]
    digest = plan_digest(plan)
    common = {
        "junit_path": "",
        "stdout_path": "",
        "revision": spec["revision"],
        "plan_digest": digest,
        "selected_targets": targets,
        "impact_class": impact_class,
        "unexpected_missing_targets": spec["unexpected_missing_targets"],
        "verifier_digest": verifier_digest,
        "source_tree": spec["source_tree"],
        "test_inventory_tree": spec["test_inventory_tree"],
        "bound_source_tree": spec["source_tree"],
        "bound_test_inventory_tree": spec["test_inventory_tree"],
        "unmatched_paths": [str(path) for path in plan.get("unmatched_paths", [])],
    }
    if spec["mode"] == "no_targets":
        return gate.PytestRunResult(
            exit_code=5,
            status="IMPACT_UNKNOWN",
            failures=[],
            terminal_status="IMPACT_UNKNOWN",
            **common,
        )
    status = "COMPLETE"
    failures: list[str] = []
    metadata: dict[str, Any] = {}
    if spec["mode"] == "none_exist":
        exit_code = 0
    elif spec["mode"] == "exclusion_defect":
        exit_code, status = 2, "CI_BOOTSTRAP_DEFECT"
    else:
        if not isinstance(exit_code, int):
            raise GateError(f"{side} executor did not record a pytest exit code")
        if exit_code not in {0, 1} or junit is None:
            status = "CI_BOOTSTRAP_DEFECT"
        else:
            validate_junit(junit, spec, files)
            with tempfile.TemporaryDirectory(prefix="trusted-impact-junit-") as directory:
                path = Path(directory) / "junit.xml"
                path.write_bytes(junit)
                failures = gate.parse_junit_failures(path)
                metadata = gate.parse_junit_metadata(path)
    fields = {
        "collection_count": int(metadata.get("collection_count", 0)),
        "node_ids": list(metadata.get("node_ids", [])),
        "passed_node_ids": list(metadata.get("passed_node_ids", [])),
        "failed_node_ids": list(metadata.get("failed_node_ids", [])),
        "error_node_ids": list(metadata.get("error_node_ids", [])),
        "skipped_node_ids": list(metadata.get("skipped_node_ids", [])),
    }
    provenance = gate.compute_test_provenance_digest(
        revision=spec["revision"],
        source_tree=spec["source_tree"],
        test_inventory_tree=spec["test_inventory_tree"],
        plan_digest=digest,
        verifier_digest=verifier_digest,
        terminal_status=status,
        exit_code=exit_code,
        status=status,
        failures=failures,
        executed_targets=spec["executed_targets"],
        missing_targets=spec["missing_targets"],
        selected_targets=targets,
        unexpected_missing_targets=spec["unexpected_missing_targets"],
        impact_class=impact_class,
        **fields,
    )
    return gate.PytestRunResult(
        exit_code=exit_code,
        status=status,
        failures=failures,
        executed_targets=spec["executed_targets"],
        missing_targets=spec["missing_targets"],
        terminal_status=status,
        provenance_digest=provenance,
        **fields,
        **common,
    )


def _read_evidence(directory: Path) -> tuple[bytes, Any, bytes | None]:
    evidence_path = directory / "executor-evidence.json"
    if evidence_path.is_symlink() or not evidence_path.is_file():
        raise GateError(f"executor evidence is missing in {directory.name}")
    raw = evidence_path.read_bytes()
    try:
        evidence = json.loads(raw)
    except ValueError:
        raise GateError(f"executor evidence in {directory.name} is not JSON") from None
    junit_path = directory / "junit.xml"
    if junit_path.is_symlink():
        raise GateError(f"junit in {directory.name} is a symlink")
    junit = junit_path.read_bytes() if junit_path.is_file() else None
    return raw, evidence, junit


def verify(
    *,
    event: dict[str, Any],
    repo: Path,
    bundle: Path,
    evidence_dir: Path,
    expected_manifest_sha256: str,
    expected_base_evidence_sha256: str,
    job_results: dict[str, str],
    fetch: bool = True,
) -> dict[str, Any]:
    """Return the trusted classification payload, raising ``GateError`` on any doubt."""

    ident = identity(event)
    for job, result in job_results.items():
        if result != "success":
            raise GateError(f"{job} job did not succeed (result={result!r})")
    manifest = load_manifest(bundle, expected_manifest_sha256)
    if manifest.get("workflow_identity") != ident:
        raise GateError("controller manifest identity does not match the event")
    for path in CODE_FILES:
        if manifest["files"][f"code/{path}"] != _sha_file(ROOT / path):
            raise GateError(f"bundled code differs from the verifier's trusted copy: {path}")
    base_sha, head_sha = ident["base_sha"], ident["head_sha"]
    if fetch:
        anchor._git(repo, "fetch", "--no-tags", "--depth=1", "origin", base_sha, head_sha)
    plan = derive_plan(repo, base_sha, head_sha)
    plan_bytes = (bundle / "plan.json").read_bytes()
    if plan_bytes != anchor._json(plan) + b"\n" or manifest.get("plan_digest") != plan_digest(plan):
        raise GateError("controller plan differs from the independently re-derived plan")
    verifier_digest = _sha_file(Path(gate.__file__))
    results: dict[str, gate.PytestRunResult] = {}
    for side in SIDES:
        spec = side_spec(repo, plan, side)
        if manifest["sides"].get(side) != spec:
            raise GateError(f"controller {side} run specification differs from the re-derived one")
        raw, evidence, junit = _read_evidence(evidence_dir / side)
        if side == "base" and anchor._sha(raw) != expected_base_evidence_sha256:
            raise GateError("base executor evidence digest does not match its job output")
        results[side] = reconstruct_result(
            spec,
            plan,
            evidence,
            junit,
            _tree_files(repo, spec["revision"]),
            expected_manifest_sha256=expected_manifest_sha256,
            verifier_digest=verifier_digest,
        )
    classification = gate.classify_regression(results["base"], results["head"])
    return {
        "schema_version": SCHEMA_VERSION,
        "trusted_source": "default-branch-verifier",
        "pull_request_number": ident["pull_request_number"],
        "base_sha": base_sha,
        "head_sha": head_sha,
        "plan_sha256": manifest["plan_sha256"],
        **asdict(classification),
    }


def _verifier(args: argparse.Namespace) -> int:
    try:
        event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
        payload = verify(
            event=event,
            repo=Path(args.repo_root),
            bundle=Path(args.bundle_dir),
            evidence_dir=Path(args.evidence_dir),
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_base_evidence_sha256=args.expected_base_evidence_sha256,
            job_results={
                "controller": args.controller_result,
                "base executor": args.base_executor_result,
                "head executor": args.head_executor_result,
            },
        )
    except Exception as exc:  # noqa: BLE001 - every doubt fails closed with a reason
        payload = {
            "schema_version": SCHEMA_VERSION,
            "trusted_source": "default-branch-verifier",
            "classification": "TRUSTED_GATE_REJECTED",
            "blocking": True,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    # Test ids in reasons are candidate-controlled; `\u005b` decodes identically but
    # keeps the runner from reading a legacy `##[command]` in the job log.
    print(rendered.replace("##[", "##\\u005b"))
    return 1 if payload.get("blocking", True) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    controller = subparsers.add_parser("controller")
    controller.add_argument("--event-json", required=True)
    controller.add_argument("--repo-root", required=True)
    controller.add_argument("--runtime-dir", required=True)
    controller.add_argument("--output-dir", required=True)
    controller.set_defaults(function=_controller)
    executor = subparsers.add_parser("executor")
    executor.add_argument("--bundle-dir", required=True)
    executor.add_argument("--side", required=True, choices=SIDES)
    executor.add_argument("--expected-manifest-sha256", required=True)
    executor.add_argument("--output-dir", required=True)
    executor.set_defaults(function=_executor)
    verifier = subparsers.add_parser("verifier")
    verifier.add_argument("--event-json", required=True)
    verifier.add_argument("--repo-root", required=True)
    verifier.add_argument("--bundle-dir", required=True)
    verifier.add_argument("--evidence-dir", required=True)
    verifier.add_argument("--expected-manifest-sha256", required=True)
    verifier.add_argument("--expected-base-evidence-sha256", required=True)
    verifier.add_argument("--controller-result", required=True)
    verifier.add_argument("--base-executor-result", required=True)
    verifier.add_argument("--head-executor-result", required=True)
    verifier.add_argument("--output", required=True)
    verifier.set_defaults(function=_verifier)
    args = parser.parse_args(argv)
    try:
        return int(args.function(args))
    except subprocess.CalledProcessError as exc:
        stderr = anchor._bounded_subprocess_output(exc.stderr)
        print(
            f"trusted impact gate: {args.command} failed: command {exc.cmd!r} exited "
            f"{exc.returncode}: {stderr.strip()}",
            file=sys.stderr,
        )
        return 1
    except GateError as exc:
        print(f"trusted impact gate: {args.command} failed closed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
