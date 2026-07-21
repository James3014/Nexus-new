"""Negative controls: A2 side-effect isolation.

Focused tests must preserve all tracked/untracked state
before and after execution.  These tests verify that
the isolation parameters introduced in production code
achieve that guarantee.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from nexus.core.capability_executor_registry import get_executor
from nexus.core.belief_contracts import CapabilityExecutionPlan
from nexus.research.learn_mode import LearnModeService
from nexus.services.xray_service import XRayService


TRACKED_LEARN_FILES = (
    ".nexus/reports/learn/phase_slo_summary.json",
    ".nexus/reports/learn/phase_writeback.jsonl",
)


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_plan(task_id: str, **constraints: object) -> CapabilityExecutionPlan:
    return CapabilityExecutionPlan(
        plan_id=f"plan-{task_id}",
        task_id=task_id,
        constraints=dict(constraints),
    )


# ── X-Ray isolation ──────────────────────────────────────────────


def test_xray_isolated_report_path(tmp_path: Path) -> None:
    isolated = tmp_path / "report.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    result = service.run(targets=["nexus/core"])
    assert Path(result) == isolated
    assert isolated.exists()
    assert isolated.read_text().startswith("# v23 X-Ray Full Analysis Report")


def test_xray_no_side_effect_on_repo_root(tmp_path: Path) -> None:
    sentinel = tmp_path / "xray_report_full.md"
    sentinel.write_text("SENTINEL")
    sentinel_before = _file_hash(sentinel)
    isolated = tmp_path / "isolated" / "report.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    service.run(targets=["nexus/core"])
    assert _file_hash(sentinel) == sentinel_before


# ── Learn-mode isolation ─────────────────────────────────────────


def test_learn_isolated_run_root_writes_to_tmp(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    service = LearnModeService(project_root=tmp_path, run_root=run_root)
    service._slo_svc.build_phase_slo_report(window=10)
    assert (run_root / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").exists()


def test_learn_tracked_state_unchanged(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    before = {p: _file_hash(repo_root / p) for p in TRACKED_LEARN_FILES}
    service = LearnModeService(project_root=tmp_path, run_root=tmp_path)
    service._slo_svc.build_phase_slo_report(window=10)
    after = {p: _file_hash(repo_root / p) for p in TRACKED_LEARN_FILES}
    assert before == after


def test_learn_run_id_separation(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    ra_dir = runtime_root / "run_a"
    rb_dir = runtime_root / "run_b"

    service_a = LearnModeService(project_root=tmp_path, run_root=ra_dir)
    service_a._slo_svc.build_phase_slo_report(window=10)
    a_hashes = {}
    for p in ra_dir.rglob("*"):
        if p.is_file():
            a_hashes[str(p.relative_to(ra_dir))] = _file_hash(p)

    service_b = LearnModeService(project_root=tmp_path, run_root=rb_dir)
    service_b._slo_svc.build_phase_slo_report(window=10)
    b_hashes = {}
    for p in rb_dir.rglob("*"):
        if p.is_file():
            b_hashes[str(p.relative_to(rb_dir))] = _file_hash(p)

    for rel in a_hashes:
        assert (ra_dir / rel).exists()
    for rel in b_hashes:
        assert (rb_dir / rel).exists()
    assert ra_dir != rb_dir

    a_hashes_after_b = {
        str(p.relative_to(ra_dir)): _file_hash(p)
        for p in ra_dir.rglob("*") if p.is_file()
    }
    assert a_hashes == a_hashes_after_b


# ── pyc / cache isolation ────────────────────────────────────────


def test_pyc_tracked_unchanged_under_env_guard(tmp_path: Path) -> None:
    tracked_pyc = [
        p for p in Path(__file__).resolve().parents[1].rglob("*.pyc") if not p.is_symlink()
    ]
    before = {str(p): _file_hash(p) for p in tracked_pyc}
    isolated = tmp_path / "report.md"
    service = XRayService(project_root=str(tmp_path), report_path=str(isolated))
    service.run(targets=["nexus/core"])
    after = {str(p): _file_hash(p) for p in tracked_pyc}
    assert before == after


# ── Formal executor negative controls ────────────────────────────


def test_executor_xray_sentinel_unchanged(tmp_path: Path) -> None:
    sentinel = tmp_path / "xray_report_full.md"
    sentinel.write_text("SENTINEL")
    sentinel_before = _file_hash(sentinel)
    plan = _make_plan(
        "t_xray_nc",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "t_xray_nc"),
    )
    executor = get_executor("xray")
    assert executor is not None
    receipt = executor(plan, "test")
    assert receipt.gate_passed, receipt.outcome.get("error", "")
    assert _file_hash(sentinel) == sentinel_before


def test_executor_learn_mode_sentinels_unchanged(tmp_path: Path) -> None:
    sentinels = {}
    for p in TRACKED_LEARN_FILES:
        sp = tmp_path / p
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text("SENTINEL")
        sentinels[p] = _file_hash(sp)
    plan = _make_plan(
        "t_learn_nc",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "t_learn_nc"),
    )
    executor = get_executor("learn_mode")
    assert executor is not None
    receipt = executor(plan, "test")
    assert receipt.gate_passed, receipt.outcome.get("error", "")
    for rel, h in sentinels.items():
        assert _file_hash(tmp_path / rel) == h


def test_executor_learn_phase_slo_sentinels_unchanged(tmp_path: Path) -> None:
    sentinels = {}
    for p in TRACKED_LEARN_FILES:
        sp = tmp_path / p
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text("SENTINEL")
        sentinels[p] = _file_hash(sp)
    plan = _make_plan(
        "t_slo_nc",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "t_slo_nc"),
    )
    executor = get_executor("learn_phase_slo")
    assert executor is not None
    receipt = executor(plan, "test")
    assert receipt.gate_passed, receipt.outcome.get("error", "")
    for rel, h in sentinels.items():
        assert _file_hash(tmp_path / rel) == h


def test_executor_receipt_has_runtime_metadata(tmp_path: Path) -> None:
    plan = _make_plan(
        "t_meta",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "t_meta"),
    )
    for cap_name in ("xray", "learn_mode", "learn_phase_slo"):
        executor = get_executor(cap_name)
        assert executor is not None
        receipt = executor(plan, "test")
        assert receipt.gate_passed, f"{cap_name}: {receipt.outcome.get('error', '')}"
        o = receipt.outcome
        assert o.get("run_id") == "t_meta", f"{cap_name} missing run_id"
        assert "resolved_run_root" in o, f"{cap_name} missing resolved_run_root"
        assert "output_paths" in o, f"{cap_name} missing output_paths"
        for op in o["output_paths"]:
            assert op.startswith(str(tmp_path)), f"{cap_name} output_path traversal: {op}"


def test_two_task_ids_do_not_overwrite(tmp_path: Path) -> None:
    plan_a = _make_plan(
        "task_a",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "task_a"),
    )
    plan_b = _make_plan(
        "task_b",
        project_root=str(tmp_path),
        run_root=str(tmp_path / "runtime" / "task_b"),
    )
    executor = get_executor("xray")
    assert executor is not None
    receipt_a = executor(plan_a, "test a")
    receipt_b = executor(plan_b, "test b")
    assert receipt_a.gate_passed
    assert receipt_b.gate_passed
    op_a = receipt_a.outcome.get("output_paths", [])
    op_b = receipt_b.outcome.get("output_paths", [])
    if op_a and op_b:
        for pa in op_a:
            for pb in op_b:
                assert pa != pb, f"task_a and task_b collided on {pa}"
