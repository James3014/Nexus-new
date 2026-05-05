from __future__ import annotations

from pathlib import Path

import pytest

from nexus.core.state_contracts import NexusState
from nexus.engine.phases.audit import AuditPhaseHandler


def test_audit_phase_fails_closed_when_hallucination_gate_rejects(tmp_path: Path):
    handler = AuditPhaseHandler(tmp_path, tmp_path, name="A", priority=40)
    state = NexusState(task_id="audit-1")

    result = handler.run(
        state,
        {
            "summary": "This fix is verified.",
            "evidence_bundle": {"code_artifacts": [], "test_artifacts": []},
        },
    )

    assert result["fail"] is True
    assert result["reason"] == "hallucination_gate_rejected"
    assert result["hallucination_gate"]["status"] == "REJECTED"


def test_audit_phase_fails_closed_when_hallucination_guard_crashes(tmp_path: Path, monkeypatch):
    class BrokenGuard:
        def __init__(self):
            raise FileNotFoundError("schema missing")

    monkeypatch.setattr("nexus.core.hallucination_guard.HallucinationGuard", BrokenGuard)
    handler = AuditPhaseHandler(tmp_path, tmp_path, name="A", priority=40)

    result = handler.run(NexusState(task_id="audit-2"), {"summary": "clean"})

    assert result["fail"] is True
    assert result["reason"] == "hallucination_gate_error:FileNotFoundError"
    assert "schema missing" in result["error"]
