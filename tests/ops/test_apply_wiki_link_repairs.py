#!/usr/bin/env python3
"""Tests for frozen link repair application."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "apply_wiki_link_repairs.py"
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"


def _run_repair(
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
        timeout=120,
    )


def test_check_mode_passes_when_no_pending_repairs(tmp_path):
    """Check mode passes when inventory has 0 repair batches."""
    res = _run_repair(tmp_path, mode="--check")
    assert res.returncode == 0, res.stderr
    assert "CHECK PASSED" in res.stdout


def test_write_mode_with_zero_batches(tmp_path):
    """Write mode with 0 repairable entries produces receipt with 0 edits."""
    res = _run_repair(tmp_path)
    assert res.returncode == 0, res.stderr
    receipt = json.loads((tmp_path / "link-repair-receipt.json").read_text())
    assert receipt["total_edits_applied"] == 0
    assert receipt["batches_applied"] == 0


def test_repair_receipt_is_deterministic(tmp_path):
    """Running write twice produces identical receipts."""
    res1 = _run_repair(tmp_path)
    assert res1.returncode == 0
    receipt1 = json.loads((tmp_path / "link-repair-receipt.json").read_text())

    res2 = _run_repair(tmp_path)
    assert res2.returncode == 0
    receipt2 = json.loads((tmp_path / "link-repair-receipt.json").read_text())

    assert receipt1["total_edits_applied"] == receipt2["total_edits_applied"]
    assert receipt1["batch_results"] == receipt2["batch_results"]


def test_repair_does_not_modify_wiki_sources(tmp_path):
    """Repair script must not modify any wiki source files."""
    before = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout

    _run_repair(tmp_path)

    after = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    assert before == after


def test_repair_receipt_schema(tmp_path):
    """Receipt must have correct schema."""
    _run_repair(tmp_path)
    receipt = json.loads((tmp_path / "link-repair-receipt.json").read_text())
    assert receipt["schema"] == "nexus.wiki.link-repair-receipt.v1"


def test_repair_receipt_has_no_absolute_paths(tmp_path):
    """Receipt must not contain absolute paths."""
    _run_repair(tmp_path)
    receipt = json.loads((tmp_path / "link-repair-receipt.json").read_text())
    receipt_str = json.dumps(receipt)
    assert "/Users/" not in receipt_str
    assert "/home/" not in receipt_str


def test_max_batches_flag(tmp_path):
    """--max-batches limits number of batches applied."""
    _run_repair(tmp_path, **{"max-batches": 1})
    receipt = json.loads((tmp_path / "link-repair-receipt.json").read_text())
    assert receipt["batches_applied"] <= 1


def test_check_mode_is_read_only(tmp_path):
    """Check mode must not modify any files."""
    _run_repair(tmp_path)
    before = (tmp_path / "link-repair-receipt.json").read_text()

    res = _run_repair(tmp_path, mode="--check")
    assert res.returncode == 0

    after = (tmp_path / "link-repair-receipt.json").read_text()
    assert before == after
