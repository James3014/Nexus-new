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
MIN_CASE_COUNT = 2


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


def _case_contract(source: str) -> list[tuple[str, str]]:
    tree = ast.parse(source, filename=CORPUS_PATH)
    cases: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id != "_c"
        ):
            continue
        if (
            not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            raise ValueError("Golden corpus contains a non-literal case id")
        status = "covered"
        for keyword in node.keywords:
            if keyword.arg != "status":
                continue
            if not isinstance(keyword.value, ast.Constant) or not isinstance(
                keyword.value.value, str
            ):
                raise ValueError("Golden corpus contains a non-literal case status")
            status = keyword.value.value
        if status not in {"covered", "finding"}:
            raise ValueError("Golden corpus contains an invalid case status")
        cases.append((node.args[0].value, status))
    if len(cases) < MIN_CASE_COUNT:
        raise ValueError(f"Golden corpus contains too few case ids: {len(cases)}")
    return cases


def _case_ids(source: str) -> list[str]:
    return [case_id for case_id, _ in _case_contract(source)]


def verify(
    repo_root: Path,
    head_sha: str,
    *,
    manifest_path: Path | None = None,
    evidence_path: Path | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Fail-closed exact-head Golden verification requiring sealed evidence.

    ``trusted_source=default-branch-verifier`` is emitted only after the
    sealed manifest/evidence pair supplied by the trusted default-branch
    controller validates against the exact head corpus.  Missing, unsealed,
    or substituted evidence never produces a PASS.
    """

    head_sha = _exact_sha(head_sha, "head_sha")
    if _git(repo_root, "cat-file", "-t", f"{head_sha}^{{commit}}").decode().strip() != "commit":
        raise ValueError("head_sha is not a commit in the trusted fetch")
    blob = _git(repo_root, "show", f"{head_sha}:{CORPUS_PATH}")
    source = blob.decode("utf-8")
    cases = _case_contract(source)
    ids = [case_id for case_id, _ in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate_case_id: {','.join(duplicates)}")
    if manifest_path is None or evidence_path is None:
        raise ValueError("manifest and evidence must be supplied together")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    golden_report = evidence.get("golden_report")
    if not isinstance(golden_report, dict):
        raise ValueError("sealed Golden evidence is missing")
    sealed = json.dumps(
        golden_report, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode()
    sealed_report_sha256 = hashlib.sha256(sealed).hexdigest()
    report_cases = golden_report.get("case_evidence")
    if (
        manifest.get("head_sha") != head_sha
        or golden_report.get("schema") != "nexus.golden_behavior_eval.v1"
        or evidence.get("golden_report_sha256") != sealed_report_sha256
        or evidence.get("golden_evaluator_sha256") != manifest.get("golden_evaluator_sha256")
        or golden_report.get("source_revision") != head_sha
        or golden_report.get("source_tree") != manifest.get("head_tree")
        or golden_report.get("corpus_identity") != hashlib.sha256(blob).hexdigest()
        or golden_report.get("evaluator_identity") != manifest.get("golden_evaluator_sha256")
        or golden_report.get("root_binding_mode") != "explicit_sha_bound"
        or not isinstance(report_cases, list)
        or not all(isinstance(row, dict) for row in report_cases)
        or [(row.get("case_id"), row.get("status")) for row in report_cases] != cases
    ):
        raise ValueError("sealed Golden evidence does not match the exact corpus contract")
    report = {
        "schema": REPORT_SCHEMA,
        "status": "PASS",
        "trusted_source": "default-branch-verifier",
        "head_sha": head_sha,
        "corpus_path": CORPUS_PATH,
        "corpus_sha256": hashlib.sha256(blob).hexdigest(),
        "case_count": len(ids),
        "sealed_report_sha256": sealed_report_sha256,
    }
    if output is not None:
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--anchor-evidence", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(
            args.repo_root,
            args.head_sha,
            manifest_path=args.manifest,
            evidence_path=args.anchor_evidence,
            output=args.json_report,
        )
    except (OSError, ValueError, UnicodeError) as exc:
        print(f"trusted Golden verifier failed closed: {exc}")
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
