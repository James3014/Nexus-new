"""Mechanical regression guard for canonical-owner boundaries after repository split.

Enforces that Nexus-new remains a compatibility / integration host and does not
accidentally introduce a second canonical implementation of extracted domains:
- James3014/nexus-core (Evidence Trust + Completion)
- James3014/nexus-learning (Evidence-bounded Learning semantics)
- James3014/nexus-open-swe-runtime (External Open SWE execution runtime)
- James3014/nexus-runtime (Runtime coordination & execution contracts)
- James3014/repository-intelligence-engine (Deterministic Repository Intelligence)
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

CANONICAL_OWNERS: dict[str, dict[str, Any]] = {
    "nexus-core": {
        "repository": "James3014/nexus-core",
        "description": "Evidence Trust Core + Completion Certification truth",
        "forbidden_new_in_tree_modules": ("product",),
        "allowed_retained_paths": (
            "product",
            "tests/product",
            "nexus/contracts/changeset_certification.py",
            "nexus/orchestrator/canonical_core_transport.py",
        ),
    },
    "nexus-learning": {
        "repository": "James3014/nexus-learning",
        "description": "Evidence-bounded learning, outcome/effectiveness measurement",
        "canonical_package": "nexus_learning",
        "forwarding_modules": (
            "nexus/learning/learning_closure_effectiveness.py",
            "nexus/learning/learning_episode_projection.py",
            "nexus/learning/outcome_memory.py",
            "nexus/contracts/learning_experience.py",
        ),
        "allowed_retained_paths": (
            "nexus/learning",
            "nexus/contracts/learning_experience.py",
            "tests/learning",
        ),
    },
    "nexus-open-swe-runtime": {
        "repository": "James3014/nexus-open-swe-runtime",
        "description": "Replaceable external execution runtime and model transport",
        "canonical_package": "nexus_open_swe_runtime",
        "allowed_retained_paths": (
            "runtimes/open_swe",
            "nexus/services/open_swe_external_intelligence.py",
            "scripts/ops/configs/external_intelligence_open_swe_activation_v1.json",
        ),
    },
    "nexus-runtime": {
        "repository": "James3014/nexus-runtime",
        "description": "Execution coordination and runtime execution contracts",
        "canonical_package": "nexus_runtime",
        "forwarding_reference_roots": ("nexus_runtime", "runtime_compat"),
        "forwarding_modules": (
            "nexus/services/runtime_compat.py",
            "nexus/services/unified_runtime.py",
        ),
        "allowed_retained_paths": (
            "nexus/services/runtime_compat.py",
            "nexus/services/unified_runtime.py",
            "tests/services/test_runtime_compat.py",
        ),
    },
    "repository-intelligence-engine": {
        "repository": "James3014/repository-intelligence-engine",
        "description": "Deterministic repository/PR/CI advisory intelligence",
        "forbidden_import_stems": ("repository_intelligence",),
        "allowed_retained_paths": (),
    },
}


class OwnershipRegressionError(Exception):
    """Raised when an ownership regression or duplicate canonical logic is detected."""


def _check_forwarding_module(
    path: Path,
    expected_reference_roots: tuple[str, ...] = (),
) -> list[str]:
    """Verify that a forwarding facade reaches an expected canonical package/adapter."""
    issues = []
    if not path.exists():
        return [f"MISSING_FORWARDING_MODULE: {path}"]
    try:
        content = path.read_text(encoding="utf-8")
        parsed = ast.parse(content, filename=str(path))
    except Exception as exc:
        return [f"UNPARSEABLE_MODULE: {path}: {exc}"]

    reference_roots: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            reference_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            reference_roots.add(node.module.split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if (
                any(isinstance(target, ast.Name) and target.id == "CANONICAL_IMPLEMENTATION_MODULE"
                    for target in targets)
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                reference_roots.add(value.value.split(".")[0])

    if expected_reference_roots and not reference_roots.intersection(expected_reference_roots):
        issues.append(f"FORWARDING_FACADE_MISSING_CANONICAL_REFERENCE: {path}")

    # Check for direct substantial class definitions that are not just thin facades
    for node in ast.walk(parsed):
        if isinstance(node, ast.ClassDef):
            # If a facade defines classes, they should not contain duplicate logic
            # specifically, outcome memory or learning closure classes must not be defined locally
            if node.name in ("OutcomeMemoryManager", "LearningExperience", "UnifiedRuntime"):
                issues.append(f"DUPLICATE_CANONICAL_CLASS_IN_FACADE: {path}:{node.name}")

    return issues


def _check_forbidden_tree_imports(repo_root: Path, forbidden_stems: tuple[str, ...]) -> list[str]:
    """Verify that no active Nexus code in nexus/ imports forbidden un-extracted/duplicated stems directly."""
    issues = []
    nexus_dir = repo_root / "nexus"
    if not nexus_dir.exists():
        return issues

    for py_file in nexus_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            parsed = ast.parse(content, filename=str(py_file))
        except Exception as exc:
            issues.append(f"UNPARSEABLE_ACTIVE_MODULE: {py_file}: {exc}")
            continue

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_name = alias.name.split(".")[0]
                    if root_name in forbidden_stems:
                        issues.append(f"FORBIDDEN_IMPORT: {py_file} imports '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root_name = node.module.split(".")[0]
                    if root_name in forbidden_stems:
                        issues.append(f"FORBIDDEN_IMPORT_FROM: {py_file} imports from '{node.module}'")
    return issues


def _check_frozen_paths_for_modifications(
    repo_root: Path,
    frozen_prefixes: tuple[str, ...],
    changed_files: list[str] | None = None,
) -> list[str]:
    """Check if any newly added files land in frozen legacy paths without explicit override."""
    issues = []
    if changed_files is None:
        return issues

    for f in changed_files:
        norm = f.replace("\\", "/").strip("/")
        for prefix in frozen_prefixes:
            if norm.startswith(prefix.strip("/") + "/"):
                issues.append(f"FROZEN_PATH_MODIFICATION: {norm} belongs to frozen {prefix}")
    return issues


def audit_repository_ownership(
    repo_root: Path,
    *,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """Audit the repository against canonical ownership boundaries."""
    repo_root = repo_root.resolve()
    all_issues: list[str] = []

    # 1. Check all forwarding modules in nexus-learning and nexus-runtime
    for owner_name in ("nexus-learning", "nexus-runtime"):
        cfg = CANONICAL_OWNERS[owner_name]
        reference_roots = tuple(
            cfg.get("forwarding_reference_roots", (cfg.get("canonical_package"),))
        )
        for rel_path in cfg.get("forwarding_modules", ()):
            module_path = repo_root / rel_path
            module_issues = _check_forwarding_module(module_path, reference_roots)
            all_issues.extend(module_issues)

    # 2. Check forbidden stems (e.g. repository_intelligence directly inside nexus/)
    for owner_name, cfg in CANONICAL_OWNERS.items():
        stems = cfg.get("forbidden_import_stems", ())
        if stems:
            stem_issues = _check_forbidden_tree_imports(repo_root, stems)
            all_issues.extend(stem_issues)

    # 3. Check frozen legacy paths if changed files are provided
    if changed_files is not None:
        # product/ and runtimes/open_swe/ are frozen legacy snapshots
        frozen_prefixes = ("product/", "runtimes/open_swe/")
        frozen_issues = _check_frozen_paths_for_modifications(repo_root, frozen_prefixes, changed_files)
        all_issues.extend(frozen_issues)

    status = "PASS" if not all_issues else "FAIL"
    return {
        "schema": "nexus.canonical_owner_audit.v1",
        "status": status,
        "owners_checked": list(CANONICAL_OWNERS.keys()),
        "issue_count": len(all_issues),
        "issues": all_issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify canonical owner boundaries and guard against regression"
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repository root (defaults to current directory)",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Optional list of changed files to check for frozen path modifications",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    result = audit_repository_ownership(
        Path(args.repo_root),
        changed_files=args.changed_files,
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Canonical-Owner Boundary Guard: {result['status']}")
        if result["issues"]:
            print(f"Found {len(result['issues'])} issues:")
            for issue in result["issues"]:
                print(f"  - {issue}")

    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
