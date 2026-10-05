#!/usr/bin/env python3
"""Trusted PR gate for Nexus mutation admission scope.

This validates a PR-body binding against a durable admission receipt and the
exact Git change set. It does not run Core completion itself; callers must run
nexus-certify separately and make both results required for integration.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from nexus.orchestrator.mutation_admission import (
    BINDING_SCHEMA,
    MutationAdmissionError,
    MutationAdmissionStore,
    path_is_allowed,
)

_BLOCK = re.compile(
    r"<!--\s*NEXUS_MUTATION_ADMISSION_V1\s*(\{.*?\})\s*NEXUS_MUTATION_ADMISSION_V1\s*-->",
    re.DOTALL,
)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git command failed")
    return proc.stdout


def _parse_binding(body: str) -> dict[str, str]:
    matches = _BLOCK.findall(body)
    if len(matches) != 1:
        raise MutationAdmissionError("PR_ADMISSION_BINDING_REQUIRED")
    try:
        payload = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        raise MutationAdmissionError("PR_ADMISSION_BINDING_INVALID") from exc
    if set(payload) != {"schema", "admission_id", "receipt_hash"}:
        raise MutationAdmissionError("PR_ADMISSION_BINDING_INVALID")
    if payload.get("schema") != BINDING_SCHEMA:
        raise MutationAdmissionError("PR_ADMISSION_BINDING_INVALID")
    return {
        "admission_id": str(payload["admission_id"]),
        "receipt_hash": str(payload["receipt_hash"]),
    }


def evaluate(
    *,
    repository: str,
    base_sha: str,
    head_sha: str,
    pr_body: str,
    repo_root: Path,
    state_root: Path,
) -> dict[str, object]:
    try:
        binding = _parse_binding(pr_body)
        store = MutationAdmissionStore(state_root)
        receipt = store.status(
            binding["admission_id"],
            expected_receipt_hash=binding["receipt_hash"],
        )
    except MutationAdmissionError as exc:
        return {
            "schema": "nexus.mutation_integration_gate.v1",
            "status": "BLOCK",
            "repository": repository,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_paths": [],
            "scope_escape_paths": [],
            "blockers": [str(exc)],
        }

    blockers: list[str] = []
    if receipt["repository"] != repository:
        blockers.append("ADMISSION_REPOSITORY_MISMATCH")
    if receipt["base_sha"] != base_sha:
        blockers.append("ADMISSION_BASE_SHA_MISMATCH")
    current_head = _git(repo_root, "rev-parse", "HEAD").strip()
    if current_head != head_sha:
        blockers.append("PR_HEAD_SHA_MISMATCH")
    changed = [
        line.strip()
        for line in _git(
            repo_root, "diff", "--name-only", f"{base_sha}...{head_sha}", "--"
        ).splitlines()
        if line.strip()
    ]
    if not changed:
        blockers.append("EMPTY_CHANGESET")
    escapes = [path for path in changed if not path_is_allowed(path, receipt["allowed_paths"])]
    if escapes:
        blockers.append("ADMISSION_SCOPE_ESCAPE")
    return {
        "schema": "nexus.mutation_integration_gate.v1",
        "status": "PASS" if not blockers else "BLOCK",
        "repository": repository,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "admission_id": receipt["admission_id"],
        "receipt_hash": receipt["receipt_hash"],
        "execution_lane": receipt["execution_lane"],
        "authority_kind": receipt["authority_kind"],
        "changed_paths": changed,
        "scope_escape_paths": escapes,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--pr-body-file", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--json-report")
    args = parser.parse_args()

    try:
        report = evaluate(
            repository=args.repository,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            pr_body=Path(args.pr_body_file).read_text(encoding="utf-8"),
            repo_root=Path(args.repo_root).resolve(),
            state_root=Path(args.state_root).resolve(),
        )
    except (MutationAdmissionError, RuntimeError, OSError) as exc:
        report = {
            "schema": "nexus.mutation_integration_gate.v1",
            "status": "BLOCK",
            "repository": args.repository,
            "base_sha": args.base_sha,
            "head_sha": args.head_sha,
            "blockers": [str(exc)],
        }

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.json_report:
        Path(args.json_report).write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
