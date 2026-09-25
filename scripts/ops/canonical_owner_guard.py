"""Mechanical regression guard for canonical-owner boundaries after repository split.

The guard freezes the repository-split boundary at the exact Nexus-new main
revision that opened Issue #1137. Historical compatibility snapshots remain in
place, but changes after that boundary may not silently reintroduce canonical
implementation ownership into Nexus-new.

This is an architecture guard, not a new ownership registry. The owner mapping
below mirrors existing repository authority documents and the capability
discovery index.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Any

OWNERSHIP_FREEZE_BASELINE = "4ddb4652842f9958eeb05feebec6cd3dd4d3f348"

CANONICAL_OWNERS: dict[str, dict[str, Any]] = {
    "nexus-core": {
        "repository": "James3014/nexus-core",
        "description": "Evidence Trust Core + Completion Certification truth",
        "frozen_prefixes": ("product/", "tests/product/"),
        "frozen_file_prefixes": ("tests/benchmark/test_core_v1_",),
        "forbidden_local_roots": ("nexus_core/",),
    },
    "nexus-learning": {
        "repository": "James3014/nexus-learning",
        "description": "Evidence-bounded learning, outcome/effectiveness measurement",
        "canonical_package": "nexus_learning",
        "frozen_prefixes": ("nexus/learning/",),
        "frozen_exact_paths": ("nexus/contracts/learning_experience.py",),
        "forbidden_local_roots": ("nexus_learning/",),
        "forwarding_modules": (
            "nexus/learning/learning_closure_effectiveness.py",
            "nexus/learning/learning_episode_projection.py",
            "nexus/learning/outcome_memory.py",
            "nexus/contracts/learning_experience.py",
        ),
    },
    "nexus-open-swe-runtime": {
        "repository": "James3014/nexus-open-swe-runtime",
        "description": "Replaceable external execution runtime and model transport",
        "canonical_package": "nexus_open_swe_runtime",
        "frozen_prefixes": ("runtimes/open_swe/",),
        "forbidden_local_roots": ("nexus_open_swe_runtime/",),
    },
    "nexus-runtime": {
        "repository": "James3014/nexus-runtime",
        "description": "Execution coordination and runtime execution contracts",
        "canonical_package": "nexus_runtime",
        "forbidden_local_roots": ("nexus_runtime/", "nexus/runtime/"),
        "forwarding_modules": (
            "nexus/services/runtime_compat.py",
            "nexus/services/unified_runtime.py",
        ),
    },
    "repository-intelligence-engine": {
        "repository": "James3014/repository-intelligence-engine",
        "description": "Deterministic repository/PR/CI advisory intelligence",
        "forbidden_local_roots": (
            "repository_intelligence/",
            "repository_intelligence_engine/",
            "nexus/repository_intelligence/",
        ),
    },
}

GUARD_OWN_PATHS = {
    "scripts/ops/canonical_owner_guard.py",
    "tests/ops/test_canonical_owner_guard.py",
}


def _normalise_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _matches_prefix(path: str, prefix: str) -> bool:
    norm = _normalise_path(path)
    clean = _normalise_path(prefix).rstrip("/")
    return norm == clean or norm.startswith(clean + "/")


def _git_paths(repo_root: Path, *args: str) -> set[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=False,
    )
    return {
        _normalise_path(item.decode("utf-8", errors="surrogateescape"))
        for item in result.stdout.split(b"\0")
        if item
    }


def collect_candidate_changed_paths(
    repo_root: Path,
    *,
    baseline_commit: str = OWNERSHIP_FREEZE_BASELINE,
) -> list[str]:
    """Return tracked and untracked paths changed after the ownership freeze."""

    repo_root = repo_root.resolve()
    subprocess.run(
        ["git", "cat-file", "-e", f"{baseline_commit}^{{commit}}"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )

    paths: set[str] = set()
    paths |= _git_paths(repo_root, "diff", "--name-only", "-z", f"{baseline_commit}..HEAD")
    paths |= _git_paths(repo_root, "diff", "--name-only", "-z")
    paths |= _git_paths(repo_root, "diff", "--cached", "--name-only", "-z")
    paths |= _git_paths(repo_root, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(paths)


def _check_forwarding_module(
    path: Path,
    *,
    canonical_package: str,
) -> list[str]:
    """Require retained facades to delegate instead of re-owning implementation."""

    if not path.exists():
        return [f"MISSING_FORWARDING_MODULE: {path}"]

    try:
        content = path.read_text(encoding="utf-8")
        parsed = ast.parse(content, filename=str(path))
    except Exception as exc:
        return [f"UNPARSEABLE_MODULE: {path}: {exc}"]

    issues: list[str] = []
    has_canonical_reference = (
        canonical_package in content
        or "CANONICAL_IMPLEMENTATION_MODULE" in content
        or "_RUNTIME" in content
    )
    if not has_canonical_reference:
        issues.append(f"FORWARDING_FACADE_MISSING_CANONICAL_REFERENCE: {path}")

    for node in ast.walk(parsed):
        if isinstance(node, ast.ClassDef):
            issues.append(f"LOCAL_CLASS_IN_FORWARDING_FACADE: {path}:{node.name}")

    return issues


def _check_changed_paths(changed_files: list[str]) -> list[str]:
    """Reject post-freeze edits that move canonical implementation back in-tree."""

    issues: list[str] = []
    for raw in changed_files:
        path = _normalise_path(raw)
        if path in GUARD_OWN_PATHS:
            continue

        for owner, cfg in CANONICAL_OWNERS.items():
            if path in cfg.get("frozen_exact_paths", ()):
                issues.append(f"FROZEN_OWNER_PATH_MODIFICATION: {path} belongs to {owner}")

            for prefix in cfg.get("frozen_prefixes", ()):
                if _matches_prefix(path, prefix):
                    issues.append(
                        f"FROZEN_OWNER_SNAPSHOT_MODIFICATION: {path} belongs to {owner}:{prefix}"
                    )

            for prefix in cfg.get("frozen_file_prefixes", ()):
                if path.startswith(_normalise_path(prefix)):
                    issues.append(
                        f"FROZEN_OWNER_TEST_MODIFICATION: {path} belongs to {owner}:{prefix}"
                    )

            for prefix in cfg.get("forbidden_local_roots", ()):
                if _matches_prefix(path, prefix):
                    issues.append(
                        f"SECOND_CANONICAL_IMPLEMENTATION_ROOT: {path} conflicts with {owner}"
                    )

    return sorted(set(issues))


def audit_repository_ownership(
    repo_root: Path,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Audit retained facades plus every post-freeze candidate path."""

    repo_root = repo_root.resolve()
    issues: list[str] = []

    for cfg in CANONICAL_OWNERS.values():
        canonical_package = cfg.get("canonical_package")
        if canonical_package:
            for rel_path in cfg.get("forwarding_modules", ()):
                issues.extend(
                    _check_forwarding_module(
                        repo_root / rel_path,
                        canonical_package=canonical_package,
                    )
                )

    try:
        paths = (
            collect_candidate_changed_paths(repo_root)
            if changed_files is None
            else sorted({_normalise_path(path) for path in changed_files})
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        issues.append(f"OWNERSHIP_BASELINE_UNAVAILABLE: {exc}")
        paths = []

    issues.extend(_check_changed_paths(paths))

    return {
        "schema": "nexus.canonical_owner_audit.v1",
        "baseline_commit": OWNERSHIP_FREEZE_BASELINE,
        "status": "PASS" if not issues else "FAIL",
        "owners_checked": list(CANONICAL_OWNERS),
        "changed_paths_checked": paths,
        "issue_count": len(issues),
        "issues": sorted(issues),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify canonical-owner boundaries after the repository split"
    )
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Optional explicit paths; otherwise derive changes since the frozen baseline",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    result = audit_repository_ownership(
        Path(args.repo_root),
        changed_files=args.changed_files,
    )
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Canonical-Owner Boundary Guard: {result['status']}")
        print(f"Baseline: {result['baseline_commit']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  - {issue}")

    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
