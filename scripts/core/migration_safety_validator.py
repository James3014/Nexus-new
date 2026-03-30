#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


class CheckResult:
    def __init__(self, ok: bool, message: str) -> None:
        self.ok = ok
        self.message = message


REQUIRED_MANIFEST_KEYS = ("version:", "defaults:", "tasks:")
BASELINE_TAG_PREFIXES = ("baseline-", "v")


def _run_git(project_root: Path, *args: str) -> CheckResult:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(project_root), *args],
            stderr=subprocess.STDOUT,
        ).decode("utf-8", errors="ignore")
        return CheckResult(True, out.strip())
    except subprocess.CalledProcessError as exc:
        return CheckResult(False, exc.output.decode("utf-8", errors="ignore").strip())
    except FileNotFoundError:
        return CheckResult(False, "git not found")


def check_manifest_contract(project_root: Path) -> CheckResult:
    manifest = project_root / "task_manifest.yaml"
    if not manifest.exists():
        return CheckResult(False, "task_manifest.yaml missing")

    text = manifest.read_text(encoding="utf-8")
    missing = [key for key in REQUIRED_MANIFEST_KEYS if key not in text]
    if missing:
        return CheckResult(False, f"task_manifest contract missing keys: {', '.join(missing)}")
    return CheckResult(True, "task_manifest contract OK")


def check_baseline_tag(project_root: Path) -> CheckResult:
    tags = _run_git(project_root, "tag", "--list")
    if not tags.ok:
        return CheckResult(False, f"failed to list tags: {tags.message}")
    tag_list = [line.strip() for line in tags.message.splitlines() if line.strip()]
    has_baseline = any(tag.startswith(BASELINE_TAG_PREFIXES) for tag in tag_list)
    if not has_baseline:
        return CheckResult(False, "baseline tag missing (expect prefix baseline- or v)")
    return CheckResult(True, f"baseline tag OK ({len(tag_list)} tag(s))")


def check_scope_guard(project_root: Path) -> CheckResult:
    changed = _run_git(project_root, "diff", "--name-only", "HEAD")
    if not changed.ok:
        return CheckResult(False, f"failed to inspect changed files: {changed.message}")

    allowed = (
        "nexus/services/",
        "nexus/engine/",
        "scripts/ops/",
        "scripts/core/",
        "tests/",
        "docs/",
    )
    ignored = (
        "task_manifest.yaml",
        "ci_benchmark.csv",
        "muse_nexus.egg-info/",
        "worktrees/",
        "benchmarks/click",
    )
    violations = [
        path
        for path in changed.message.splitlines()
        if path
        and not any(path.startswith(prefix) for prefix in allowed)
        and not any(path.startswith(prefix) for prefix in ignored)
    ]
    if violations:
        return CheckResult(False, f"scope guard violation: {', '.join(violations[:8])}")
    return CheckResult(True, "scope guard OK")


def run(project_root: Path, check_scope: bool = False) -> int:
    checks = [
        ("manifest", check_manifest_contract(project_root)),
        ("baseline_tag", check_baseline_tag(project_root)),
    ]
    if check_scope:
        checks.append(("scope_guard", check_scope_guard(project_root)))

    failed = False
    for name, result in checks:
        icon = "✅" if result.ok else "❌"
        print(f"{icon} {name}: {result.message}")
        failed = failed or not result.ok
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus migration safety gate")
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parents[2]),
        help="Repository root path",
    )
    parser.add_argument(
        "--check-scope-guard",
        action="store_true",
        help="Also enforce scope guard against HEAD diff",
    )
    args = parser.parse_args()
    return run(Path(args.project_root), check_scope=args.check_scope_guard)


if __name__ == "__main__":
    raise SystemExit(main())
