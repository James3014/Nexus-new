"""P-CONTAM-01 on the canonical research path (#2199).

The contamination guard must run where the canonical research executor accepts research
output: contaminated output and guard errors are BLOCKed, clean output still passes.
These tests go through the registered executor invoker, not the guard alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nexus.services.capability_registry import build_real_executor_invoker


def _run_research(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pack: dict[str, Any], *, task_id: str
) -> dict[str, Any]:
    from nexus.engine.phases.research import ResearchPhaseHandler

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        ResearchPhaseHandler, "_run_external_research", lambda self, query: dict(pack)
    )
    monkeypatch.setattr(ResearchPhaseHandler, "_get_lancedb", lambda self: None)
    invoker = build_real_executor_invoker("research")
    assert invoker is not None
    return invoker({
        "task_id": task_id,
        "task_statement": "How does compute_total apply the discount?",
    })


def _outcome(result: dict[str, Any]) -> dict[str, Any]:
    return result["response"]["outcome"]


def _success(**extra: Any) -> dict[str, Any]:
    return {"source": "test", "status": "SUCCESS", "tokens_used": 1, **extra}


def test_canonical_research_blocks_design_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total applies the discount; recommend a patch plan to fix it"]),
        task_id="contam-lang",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert outcome["policy_id"] == "P-CONTAM-01"
    assert "recommend" in outcome["detected_terms"]
    # the contaminated research output is not handed downstream in the receipt
    assert "result" not in outcome


def test_canonical_research_blocks_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], patch_plan="candidate_001"),
        task_id="contam-field",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["error"] == "RESEARCH_CONTAMINATION_DETECTED"
    assert outcome["detected_terms"] == ["design_field"]


def test_canonical_research_blocks_nested_design_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies by 0.9"], raw={"winner": "candidate_b"}),
        task_id="contam-raw",
    )
    assert result["gate_passed"] is False
    assert _outcome(result)["detected_terms"] == ["design_field"]


def test_canonical_research_clean_output_passes_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    findings = ["compute_total multiplies the subtotal by 0.9 when the discount flag is set"]
    result = _run_research(
        tmp_path, monkeypatch, _success(findings=findings), task_id="contam-clean"
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is True
    assert outcome["semantic_status"] == "SUCCEEDED"
    assert outcome["action"] == "run"
    assert outcome["result"]["findings"] == findings
    assert "error" not in outcome


def test_canonical_research_guard_error_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus.research import contamination_guard

    def broken(payload: dict[str, Any]) -> Any:
        raise RuntimeError("guard exploded")

    monkeypatch.setattr(contamination_guard, "evaluate_research_contamination", broken)
    result = _run_research(
        tmp_path,
        monkeypatch,
        _success(findings=["compute_total multiplies the subtotal by 0.9"]),
        task_id="contam-err",
    )
    outcome = _outcome(result)
    assert result["gate_passed"] is False
    assert outcome["semantic_status"] == "BLOCKED"
    assert outcome["error"] == "RESEARCH_CONTAMINATION_GUARD_ERROR"
    assert "result" not in outcome
