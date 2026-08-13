#!/usr/bin/env python3
"""Validate Golden Behavior from an exact PR head without importing it.

This verifier is run only by the default-branch ``pull_request_target``
workflow.  It reads the candidate corpus as a Git blob, so a PR-side workflow
with the same check name cannot provide the verifier's evidence or alter the
verifier implementation.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

CORPUS_PATH = "tests/golden_behavior/corpus.py"
REPORT_SCHEMA = "nexus.trusted_golden_verifier.v1"
SHA_LENGTH = 40


def _exact_sha(value: str, label: str) -> str:
    if len(value) != SHA_LENGTH or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{label} must be a lowercase 40-character SHA")
    return value


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout


def _case_ids(source: str) -> list[str]:
    tree = ast.parse(source, filename=CORPUS_PATH)
    ids: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "_c":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            raise ValueError("Golden corpus contains a non-literal case id")
        ids.append(node.args[0].value)
    if not ids:
        raise ValueError("Golden corpus contains no case ids")
    return ids


def verify(repo_root: Path, head_sha: str, *, output: Path | None = None) -> dict[str, Any]:
    head_sha = _exact_sha(head_sha, "head_sha")
    if _git(repo_root, "cat-file", "-t", f"{head_sha}^{{commit}}").decode().strip() != "commit":
        raise ValueError("head_sha is not a commit in the trusted fetch")
    blob = _git(repo_root, "show", f"{head_sha}:{CORPUS_PATH}")
    source = blob.decode("utf-8")
    ids = _case_ids(source)
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate_case_id: {','.join(duplicates)}")
    report = {
        "schema": REPORT_SCHEMA,
        "status": "PASS",
        "trusted_source": "default-branch-verifier",
        "head_sha": head_sha,
        "corpus_path": CORPUS_PATH,
        "corpus_sha256": hashlib.sha256(blob).hexdigest(),
        "case_count": len(ids),
    }
    if output is not None:
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.repo_root, args.head_sha, output=args.json_report)
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"trusted Golden verifier failed closed: {exc}")
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
