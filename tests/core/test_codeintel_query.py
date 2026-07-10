from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from nexus.core.capability_selector import CapabilitySelector
from nexus.core.capability_signal_set import CapabilitySignalSet
from nexus.core.capability_constraints import CapabilityConstraints


def _mk_signal(tmp_path: Path, codeintel_available: bool = True) -> CapabilitySignalSet:
    return CapabilitySignalSet(
        task_id="t001",
        task_desc="fix bug in parser",
        risk_level="NORMAL",
        impact_complexity=2.0,
        belief_confidence=0.8,
        skills_triggered=["repair_loop"],
        tenant_id="default",
        codeintel_query_available=codeintel_available,
        codeintel_evidence={},
    )


def _mk_constraints() -> CapabilityConstraints:
    return CapabilityConstraints(project_root="/tmp")


def test_codeintel_query_when_available(tmp_path: Path):
    sel = CapabilitySelector(project_root=str(tmp_path))
    sig = _mk_signal(tmp_path, codeintel_available=True)
    cons = _mk_constraints()
    with patch.object(sel, "_codeintel_query", wraps=sel._codeintel_query) as spy:
        plan = sel.select_capabilities(sig, cons)
        spy.assert_called_once()
        assert plan is not None


def test_codeintel_query_skipped_when_unavailable(tmp_path: Path):
    sel = CapabilitySelector(project_root=str(tmp_path))
    sig = _mk_signal(tmp_path, codeintel_available=False)
    cons = _mk_constraints()
    with patch.object(sel, "_codeintel_query", wraps=sel._codeintel_query) as spy:
        plan = sel.select_capabilities(sig, cons)
        spy.assert_not_called()
        assert plan is not None


def test_codeintel_query_failure_does_not_block(tmp_path: Path):
    sel = CapabilitySelector(project_root=str(tmp_path))
    sig = _mk_signal(tmp_path, codeintel_available=True)
    cons = _mk_constraints()
    with patch.object(sel, "_codeintel_query", side_effect=RuntimeError("boom")):
        plan = sel.select_capabilities(sig, cons)
        assert plan is not None


def test_codeintel_evidence_in_signal_snapshot(tmp_path: Path):
    sel = CapabilitySelector(project_root=str(tmp_path))
    sig = _mk_signal(tmp_path, codeintel_available=True)
    cons = _mk_constraints()
    sel.select_capabilities(sig, cons)
    assert sig.codeintel_evidence.get("status") == "PASS"


def test_codeintel_existing_signal_unchanged(tmp_path: Path):
    sel = CapabilitySelector(project_root=str(tmp_path))
    sig = _mk_signal(tmp_path, codeintel_available=True)
    cons = _mk_constraints()
    orig_id = sig.task_id
    orig_desc = sig.task_desc
    sel.select_capabilities(sig, cons)
    assert sig.task_id == orig_id
    assert sig.task_desc == orig_desc
