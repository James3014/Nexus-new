#!/usr/bin/env python3
"""Tests for governance closure verification."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "check_wiki_governance_closure.py"
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"


def _run_closure(
    tmp_path: Path,
    mode: str = "--write",
    **kwargs,
) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT), mode]
    args.extend(["--output-dir", str(tmp_path)])
    for key, value in kwargs.items():
        args.extend([f"--{key.replace('_', '-')}", str(value)])
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_write_mode_produces_receipt(tmp_path):
    """Write mode produces a governance closure receipt."""
    res = _run_closure(tmp_path)
    assert res.returncode == 0, res.stderr
    receipt = json.loads((tmp_path / "governance-closure-receipt.json").read_text())
    assert receipt["schema"] == "nexus.wiki.governance-closure-receipt.v1"
    assert receipt["status"] == "closed"


def test_check_mode_passes_when_all_checks_pass(tmp_path):
    """Check mode passes when all governance checks pass."""
    _run_closure(tmp_path)
    res = _run_closure(tmp_path, mode="--check")
    assert res.returncode == 0, res.stderr
    assert "CHECK PASSED" in res.stdout


def test_receipt_has_all_checks(tmp_path):
    """Receipt contains all required checks."""
    _run_closure(tmp_path)
    receipt = json.loads((tmp_path / "governance-closure-receipt.json").read_text())
    check_names = [c["name"] for c in receipt["checks"]]
    assert "committed_tree_reproducibility" in check_names
    assert "classifier_determinism" in check_names
    assert "link_repair_receipt" in check_names
    assert "compiler_tests" in check_names
    assert "reproducibility_tests" in check_names
    assert "classifier_tests" in check_names
    assert "repair_tests" in check_names


def test_receipt_counts_are_correct(tmp_path):
    """Receipt counts match actual check results."""
    _run_closure(tmp_path)
    receipt = json.loads((tmp_path / "governance-closure-receipt.json").read_text())
    assert receipt["total_checks"] == len(receipt["checks"])
    assert receipt["passed_checks"] + receipt["failed_checks"] == receipt["total_checks"]


def test_receipt_is_deterministic(tmp_path):
    """Running write twice produces identical receipts."""
    res1 = _run_closure(tmp_path)
    assert res1.returncode == 0
    receipt1 = json.loads((tmp_path / "governance-closure-receipt.json").read_text())

    res2 = _run_closure(tmp_path)
    assert res2.returncode == 0
    receipt2 = json.loads((tmp_path / "governance-closure-receipt.json").read_text())

    assert receipt1["status"] == receipt2["status"]
    assert receipt1["total_checks"] == receipt2["total_checks"]
    assert receipt1["passed_checks"] == receipt2["passed_checks"]


def test_check_mode_is_read_only(tmp_path):
    """Check mode must not modify any files."""
    _run_closure(tmp_path)
    before = (tmp_path / "governance-closure-receipt.json").read_text()

    res = _run_closure(tmp_path, mode="--check")
    assert res.returncode == 0

    after = (tmp_path / "governance-closure-receipt.json").read_text()
    assert before == after


def test_closure_receipt_contains_deterministic_artifact_identity(tmp_path):
    res = _run_closure(tmp_path)
    assert res.returncode == 0, res.stderr
    receipt = json.loads((tmp_path / "governance-closure-receipt.json").read_text())
    assert receipt["source_fingerprint"]
    assert receipt["governance_input_fingerprint"]
    assert set(receipt["artifact_hashes"]) == {
        "agent-index.json",
        "wikilink-graph.json",
        "unresolved-link-inventory.json",
    }


def test_closure_check_rejects_stale_source_fingerprint(tmp_path):
    _run_closure(tmp_path)
    receipt_path = tmp_path / "governance-closure-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["source_fingerprint"] = "stale"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    res = _run_closure(tmp_path, mode="--check")

    assert res.returncode == 1
    assert "source_fingerprint" in res.stdout


def test_closure_check_rejects_stale_governance_input_fingerprint(tmp_path):
    _run_closure(tmp_path)
    receipt_path = tmp_path / "governance-closure-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["governance_input_fingerprint"] = "stale"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    res = _run_closure(tmp_path, mode="--check")

    assert res.returncode == 1
    assert "governance_input_fingerprint" in res.stdout


def test_closure_check_rejects_artifact_hash_drift(tmp_path):
    _run_closure(tmp_path)
    receipt_path = tmp_path / "governance-closure-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["artifact_hashes"]["agent-index.json"] = "stale"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    res = _run_closure(tmp_path, mode="--check")

    assert res.returncode == 1
    assert "artifact_hashes" in res.stdout


def test_closure_check_rejects_missing_identity_fields(tmp_path):
    _run_closure(tmp_path)
    receipt_path = tmp_path / "governance-closure-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    del receipt["artifact_hashes"]
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    res = _run_closure(tmp_path, mode="--check")

    assert res.returncode == 1
    assert "missing field artifact_hashes" in res.stdout


def test_closure_receipt_is_byte_deterministic(tmp_path):
    first = _run_closure(tmp_path)
    assert first.returncode == 0
    receipt_path = tmp_path / "governance-closure-receipt.json"
    first_bytes = receipt_path.read_bytes()

    second = _run_closure(tmp_path)
    assert second.returncode == 0
    assert receipt_path.read_bytes() == first_bytes


def test_closure_does_not_modify_wiki_sources(tmp_path):
    """Closure script must not modify any wiki source files."""
    before = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout

    _run_closure(tmp_path)

    after = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    assert before == after
