#!/usr/bin/env python3
"""Verify Wiki governance inventory closure.

Runs all governance checks and produces a final closure receipt.

CLI:
    --write      write closure receipt
    --check      verify closure is complete
    --repo-root PATH
    --vault-root PATH
    --output-dir PATH
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA = "nexus.wiki.governance-closure-receipt.v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_check(script_path: Path, args: list[str], repo_root: Path) -> bool:
    """Run a check script and return True if it passes."""
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Wiki governance inventory closure"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Write closure receipt")
    group.add_argument("--check", action="store_true", help="Check closure is complete")
    parser.add_argument("--repo-root", type=str, default=".", help="Repository root")
    parser.add_argument("--vault-root", type=str, help="Wiki vault root")
    parser.add_argument("--output-dir", type=str, help="Output directory for receipt")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    vault_root = (
        Path(args.vault_root)
        if args.vault_root
        else repo_root / "nexus_wiki_vault"
    )
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else vault_root / "99_Schema" / "generated"
    )

    # Define checks
    checks = [
        {
            "name": "committed_tree_reproducibility",
            "script": repo_root / "scripts" / "ops" / "check_wiki_committed_reproducibility.py",
            "args": ["--check", "--repo-root", str(repo_root), "--ref", "HEAD"],
            "description": "Committed-tree reproducibility gate",
        },
        {
            "name": "classifier_determinism",
            "script": repo_root / "scripts" / "ops" / "classify_wiki_unresolved_links.py",
            "args": ["--check"],
            "description": "Unresolved-link classifier determinism",
        },
        {
            "name": "link_repair_receipt",
            "script": repo_root / "scripts" / "ops" / "apply_wiki_link_repairs.py",
            "args": ["--check"],
            "description": "Link repair receipt verification",
        },
        {
            "name": "compiler_tests",
            "script": repo_root / "tests" / "ops" / "test_build_wiki_agent_index.py",
            "args": [],
            "description": "Compiler test suite",
        },
        {
            "name": "reproducibility_tests",
            "script": repo_root / "tests" / "ops" / "test_wiki_committed_reproducibility.py",
            "args": [],
            "description": "Reproducibility test suite",
        },
        {
            "name": "classifier_tests",
            "script": repo_root / "tests" / "ops" / "test_classify_wiki_unresolved_links.py",
            "args": [],
            "description": "Classifier test suite",
        },
        {
            "name": "repair_tests",
            "script": repo_root / "tests" / "ops" / "test_apply_wiki_link_repairs.py",
            "args": [],
            "description": "Repair test suite",
        },
    ]

    # Run checks
    results: list[dict[str, Any]] = []
    all_passed = True

    for check in checks:
        passed = run_check(check["script"], check["args"], repo_root)
        results.append(
            {
                "name": check["name"],
                "description": check["description"],
                "passed": passed,
            }
        )
        if not passed:
            all_passed = False

    # Build receipt
    receipt = {
        "schema": SCHEMA,
        "authority": "derived_non_authoritative",
        "status": "closed" if all_passed else "open",
        "checks": results,
        "total_checks": len(results),
        "passed_checks": sum(1 for r in results if r["passed"]),
        "failed_checks": sum(1 for r in results if not r["passed"]),
    }

    if args.write:
        output_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = output_dir / "governance-closure-receipt.json"
        receipt_path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if all_passed:
            print("OK: governance closure verified, all checks passed")
        else:
            print(f"FAIL: {receipt['failed_checks']} checks failed")
            sys.exit(1)

    elif args.check:
        if not all_passed:
            print(f"DRIFT: {receipt['failed_checks']} governance checks failed")
            sys.exit(1)
        print("CHECK PASSED: governance closure complete")


if __name__ == "__main__":
    main()
