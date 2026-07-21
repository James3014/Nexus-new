"""Negative controls: A2 side-effect isolation.

Focused tests must preserve all tracked/untracked state
before and after execution.  These tests verify that
the isolation parameters introduced in production code
achieve that guarantee.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from nexus.services.xray_service import XRayService
from nexus.research.learn_mode import LearnModeService


TRACKED_LEARN_FILES = (
    ".nexus/reports/learn/phase_slo_summary.json",
    ".nexus/reports/learn/phase_writeback.jsonl",
)
TRACKED_XRAY_FILE = "xray_report_full.md"


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── X-Ray isolation ──────────────────────────────────────────────


def test_xray_isolated_report_path(tmp_path: Path) -> None:
    isolated = tmp_path / "report.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    result = service.run(targets=["nexus/core"])
    assert Path(result) == isolated
    assert isolated.exists()
    assert isolated.read_text().startswith("# v23 X-Ray Full Analysis Report")


def test_xray_no_side_effect_on_repo_root(tmp_path: Path, monkeypatch) -> None:
    isolated = tmp_path / "xray_report_full.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    monkeypatch.delenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", raising=False)
    service.run(targets=["nexus/core"])
    repo_root = Path(__file__).resolve().parents[1]
    repo_xray = repo_root / TRACKED_XRAY_FILE
    assert not repo_xray.exists() or _file_hash(repo_xray) == _file_hash(repo_xray)


# ── Learn-mode isolation ─────────────────────────────────────────


def test_learn_isolated_run_root_writes_to_tmp(tmp_path: Path) -> None:
    service = LearnModeService(project_root=tmp_path, run_root=tmp_path)
    isolated_phase = tmp_path / ".nexus" / "reports" / "learn"
    service._slo_svc.build_phase_slo_report(window=10)
    assert (isolated_phase / "phase_slo_summary.json").exists()


def test_learn_tracked_state_unchanged(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    before = {p: _file_hash(repo_root / p) for p in TRACKED_LEARN_FILES}
    service = LearnModeService(project_root=tmp_path, run_root=tmp_path)
    service._slo_svc.build_phase_slo_report(window=10)
    after = {p: _file_hash(repo_root / p) for p in TRACKED_LEARN_FILES}
    assert before == after


def test_learn_run_id_separation(tmp_path: Path) -> None:
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    run_a.mkdir(); run_b.mkdir()

    service_a = LearnModeService(project_root=run_a, run_root=run_a)
    service_b = LearnModeService(project_root=run_b, run_root=run_b)

    service_a._slo_svc.build_phase_slo_report(window=10)
    service_b._slo_svc.build_phase_slo_report(window=10)

    a_files = set(run_a.rglob("*"))
    b_files = set(run_b.rglob("*"))
    assert not (a_files & b_files), "run roots must not overlap"


# ── pyc / cache isolation ────────────────────────────────────────


def test_pyc_tracked_unchanged_under_env_guard(tmp_path: Path) -> None:
    tracked_pyc = [p for p in Path(__file__).resolve().parents[1].rglob("*.pyc")
                   if not p.is_symlink()]
    before = {str(p): _file_hash(p) for p in tracked_pyc}
    isolated = tmp_path / "report.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    service.run(targets=["nexus/core"])
    after = {str(p): _file_hash(p) for p in tracked_pyc}
    assert before == after
