from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ops/night_summary.py"


def _run(*args: str) -> tuple[int, str, str]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode, r.stdout, r.stderr


def _make_csv(tmp: Path, rows: list[dict]) -> Path:
    p = tmp / "input.csv"
    with open(p, "w", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    return p


import csv


def test_no_output_writes_nothing(tmp_path):
    csv_path = _make_csv(tmp_path, [{"task_id": "T1", "status": "PASS", "learning_velocity": "1.5", "policy_hit": "yes", "phase_path": "p"}])
    rc, out, _ = _run("--input", str(csv_path))
    assert rc == 0
    assert "docs/reports" not in out
    assert len(list(tmp_path.rglob("*.md"))) == 0


def test_explicit_output_writes_exact_path(tmp_path):
    csv_path = _make_csv(tmp_path, [{"task_id": "T1", "status": "PASS", "learning_velocity": "1.0", "policy_hit": "", "phase_path": "p"}])
    out_path = tmp_path / "my_report.md"
    rc, out, _ = _run("--input", str(csv_path), "--output", str(out_path))
    assert rc == 0
    assert out_path.exists()
    assert "Night Shift Report" in out_path.read_text()


def test_no_dated_docs_reports_default(tmp_path):
    csv_path = _make_csv(tmp_path, [{"task_id": "T1", "status": "PASS", "learning_velocity": "1.0", "policy_hit": "", "phase_path": "p"}])
    rc, out, _ = _run("--input", str(csv_path))
    assert "night_shift_" not in out
    assert "docs/reports" not in out


def test_empty_csv_exits_nonzero(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("task_id,status\n", encoding="utf-8")
    rc, out, _ = _run("--input", str(csv_path))
    assert rc == 1 or "EMPTY" in out


def test_missing_csv_fails(tmp_path):
    rc, _, err = _run("--input", str(tmp_path / "nonexistent.csv"))
    assert rc != 0
