from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _import_check(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import importlib.util; s=importlib.util.spec_from_file_location('m','{REPO_ROOT / script}'); m=importlib.util.module_from_spec(s)"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0 or "ModuleNotFoundError" in result.stderr, f"import failed for {script}: {result.stderr}"


def test_observation_cycle_01_no_default_docs_reports():
    c = (REPO_ROOT / "scripts/bench/run_observation_cycle_01.py").read_text()
    assert "/Users/jameschen/Workspace/nexus/docs/reports" not in c
    assert "limited_mount_observation_cycle_01.md" not in c


def test_observation_cycle_02_no_default_docs_reports():
    c = (REPO_ROOT / "scripts/bench/run_observation_cycle_02.py").read_text()
    assert "/Users/jameschen/Workspace/nexus/docs/reports" not in c
    assert "limited_mount_observation_cycle_02.md" not in c


def test_observation_cycle_03_no_default_docs_reports():
    c = (REPO_ROOT / "scripts/bench/run_observation_cycle_03.py").read_text()
    assert "/Users/jameschen/Workspace/nexus/docs/reports" not in c
    assert "limited_mount_observation_cycle_03.md" not in c


def test_local_problem_diff_no_default_docs_reports():
    c = (REPO_ROOT / "scripts/bench/run_local_problem_diff_eval.py").read_text()
    assert "/Users/jameschen/Workspace/nexus/docs/reports" not in c


def test_s2t_failure_taxonomy_no_default_docs_reports():
    c = (REPO_ROOT / "scripts/bench/s2t_failure_taxonomy.py").read_text()
    assert 'docs/reports' not in c


def test_t1_5_no_report_dir():
    c = (REPO_ROOT / "scripts/bench/t1_5_semantic_retry_astropy_13236.py").read_text()
    assert '"docs/reports"' not in c


def test_t1_8_no_report_dir():
    c = (REPO_ROOT / "scripts/bench/t1_8_rerun_astropy_12907.py").read_text()
    assert '"docs/reports"' not in c


def test_no_absolute_developer_path():
    for script in [
        "scripts/bench/run_observation_cycle_01.py",
        "scripts/bench/run_observation_cycle_02.py",
        "scripts/bench/run_observation_cycle_03.py",
        "scripts/bench/run_local_problem_diff_eval.py",
    ]:
        c = (REPO_ROOT / script).read_text()
        assert "/Users/jameschen/" not in c, f"{script} still has absolute dev path"
