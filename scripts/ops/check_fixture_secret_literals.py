#!/usr/bin/env python3
"""Reject contiguous, detector-shaped secret literals in test fixtures.

The repo-wide history secret audit scans every reachable blob, so one fixture
that looks like a real credential blocks main and every PR.  This lint reuses
the audit's detector table (read-only) and fails early, on the branch, before
the literal is ever pushed.

Fixtures must be built from split literals, e.g. ``"xo" + "xb-"``.  If the
offending literal is already pushed, rewrite the branch history to drop it or
delete the branch; fixing it in a later commit does not remove it from history.

Usage:
    check_fixture_secret_literals.py            # files under tests/ changed vs origin/main
    check_fixture_secret_literals.py --all      # every file under tests/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from scripts.ops.git_history_secret_scan import (
        KNOWN_HISTORICAL_FIXTURES,
        SECRET_PATH_RE,
        _fingerprint,
        _scan_bytes,
    )
except ImportError:  # executed as a plain script
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.ops.git_history_secret_scan import (
        KNOWN_HISTORICAL_FIXTURES,
        SECRET_PATH_RE,
        _fingerprint,
        _scan_bytes,
    )

TESTS_PREFIX = "tests/"

REMEDIATION = (
    "Build fake secrets from split literals so no contiguous detector-shaped "
    'string exists in the file, e.g. "xo" + "xb-" + "1234567890-abcdef". '
    "If the literal is already pushed, rewrite the branch history to remove it "
    "or delete the branch; a follow-up fix commit does not remove it from history."
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def changed_test_files(repo: Path, base: str = "origin/main") -> list[str]:
    """Test files added/changed vs the merge base with ``base``, plus untracked."""
    names = _git(
        repo, "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD", "--", "tests"
    ).splitlines()
    names += _git(
        repo, "diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--", "tests"
    ).splitlines()
    names += _git(repo, "ls-files", "--others", "--exclude-standard", "--", "tests").splitlines()
    return sorted(set(names))


def all_test_files(repo: Path) -> list[str]:
    return sorted(_git(repo, "ls-files", "--", "tests").splitlines())


def _blob_id(repo: Path, data: bytes) -> str:
    proc = subprocess.run(
        ["git", "hash-object", "--stdin"], cwd=repo, input=data, capture_output=True, check=True
    )
    return proc.stdout.decode().strip()


def history_blobs(repo: Path, base: str) -> list[tuple[str, str]]:
    """(blob oid, path) for every tests/ blob introduced by commits base..HEAD."""
    out = _git(
        repo, "log", "-m", "--format=", "--raw", "--no-abbrev", "--diff-filter=ACMR",
        f"{base}..HEAD", "--", "tests",
    )  # fmt: skip
    seen: set[tuple[str, str]] = set()
    for line in out.splitlines():
        meta, _, path = line.partition("\t")
        fields = meta.split()
        if len(fields) >= 5 and path.startswith(TESTS_PREFIX):
            seen.add((fields[3], path))
    return sorted(seen)


def scan_blob(oid: str, rel: str, data: bytes) -> list[tuple[str, str, str]]:
    """Apply the audit's content, secret-path and known-fixture rules to one blob."""
    violations: list[tuple[str, str, str]] = []
    for finding in _scan_bytes(data, subject_type="fixture", path=rel):
        if not finding.blocking:
            continue
        if (oid, rel, finding.detector, finding.fingerprint) in KNOWN_HISTORICAL_FIXTURES:
            continue
        violations.append((rel, finding.detector, finding.fingerprint))
    if (
        SECRET_PATH_RE.search(rel)
        and not rel.lower().endswith((".template", ".example", ".sample"))
        and data.strip()
    ):
        violations.append((rel, "secret_bearing_path", _fingerprint((oid + "\0" + rel).encode())))
    return violations


def scan_paths(
    repo: Path, paths: list[str], history_base: str | None = None
) -> list[tuple[str, str, str]]:
    """Return (path, detector, fingerprint) for each blocking finding.

    Scans working-tree files and, when ``history_base`` is given, every tests/
    blob introduced in ``history_base..HEAD`` (the audit reads history too).
    """
    violations: list[tuple[str, str, str]] = []
    for rel in paths:
        if not rel.startswith(TESTS_PREFIX):
            continue
        file_path = repo / rel
        if not file_path.is_file():
            continue
        data = file_path.read_bytes()
        violations.extend(scan_blob(_blob_id(repo, data), rel, data))
    if history_base is not None:
        for oid, rel in history_blobs(repo, history_base):
            data = subprocess.run(
                ["git", "cat-file", "blob", oid], cwd=repo, capture_output=True, check=True
            ).stdout
            violations.extend(scan_blob(oid, rel, data))
    return sorted(set(violations))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--all", action="store_true", help="scan the whole tests/ tree")
    parser.add_argument("--base", default="origin/main", help="base ref for the changed-file set")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    try:
        paths = all_test_files(repo) if args.all else changed_test_files(repo, args.base)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"check_fixture_secret_literals: {exc}", file=sys.stderr)
        return 2
    violations = scan_paths(repo, paths, None if args.all else args.base)
    if not violations:
        print(f"check_fixture_secret_literals: OK ({len(paths)} file(s) scanned)")
        return 0
    print("check_fixture_secret_literals: FAIL - contiguous secret-shaped literal(s) in tests:")
    for rel, detector, fingerprint in violations:
        print(f"  {rel}: {detector} (fingerprint {fingerprint[:12]})")
    print(REMEDIATION)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
